"""One bounded request between a local agent and the explicitly paired inbox."""
import sqlite3
from threading import Condition
from time import monotonic
from uuid import uuid4


class Bridge:
    def __init__(self):
        self.changed = Condition()
        self.pair = None
        self.title = ''
        self.seen = 0
        self.pending = None

    def status(self):
        with self.changed:
            live = self.pair is not None and monotonic() - self.seen < 18
            return {'connected': live, 'source': self.title if live else None}

    def next(self, pair, title):
        if not isinstance(pair, str) or len(pair) != 36 or not isinstance(title, str):
            raise ValueError('Invalid browser connection.')
        with self.changed:
            self.pair, self.title, self.seen = pair, title[:2048], monotonic()
            self.changed.notify_all()
            def available():
                job = self.pending
                return job and job['pair'] == pair and not job['claimed']
            if not self.changed.wait_for(available, timeout=6):
                return {}
            self.pending['claimed'] = True
            return {k: self.pending[k] for k in ('id', 'kind', 'pair', 'selector')}

    def capture(self, kind, selector=None, timeout=22):
        if kind not in ('text', 'png'):
            raise ValueError('Choose text or png.')
        if selector is not None and (kind != 'text' or not isinstance(selector, str) or not 0 < len(selector) <= 1000):
            raise ValueError('A selector must be 1–1000 characters and applies only to text.')
        with self.changed:
            if not self.status()['connected']:
                raise ValueError('Open the Blinders inbox, connect a research tab, then check the connection.')
            if self.pending:
                raise ValueError('Another capture is running. Wait for its receipt.')
            job = {'id': str(uuid4()), 'kind': kind, 'pair': self.pair, 'selector': selector, 'claimed': False}
            self.pending = job
            self.changed.notify_all()
            try:
                if not self.changed.wait_for(lambda: 'result' in job, timeout):
                    raise ValueError('The connected inbox did not answer in time. Bring it to the front and retry.')
                if job.get('error'):
                    raise ValueError(job['error'])
                return job['result']
            finally:
                self.pending = None
                self.changed.notify_all()

    def finish(self, reply, captures):
        with self.changed:
            job = self.pending
            if not job or not job['claimed'] or 'result' in job or (reply.get('id'), reply.get('pair')) != (job['id'], job['pair']):
                raise ValueError('This browser request expired or changed.')
            try:
                if reply.get('error'):
                    raise ValueError(str(reply['error'])[:500])
                if reply.get('kind') != job['kind']:
                    raise ValueError('Capture format changed.')
                job['result'] = captures.save(reply)
            except (ValueError, OSError, sqlite3.Error) as error:
                job['error'] = str(error)
                job['result'] = None
            self.changed.notify_all()
            return {'received': True}
