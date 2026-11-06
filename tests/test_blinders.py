import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from uuid import uuid4

from captures import Captures, Store
from local_server import make_server

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ySFsAAAAASUVORK5CYII=')
TEXT = '\ufeff  “source”\tA  B\r\n\nβ <em>literal</em>  \n'


def sample(kind='text'):
    return dict(id=str(uuid4()), kind=kind, content=TEXT if kind == 'text' else base64.b64encode(PNG).decode(),
                source='https://research.example/paper?a=private#fragment', title='An unrelated research topic')


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.captures = Captures(self.store)

    def test_retries_concurrent_writes_and_reopen(self):
        value = sample()
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(self.captures.save, [value] * 8))
        self.assertTrue(all(row == receipts[0] for row in receipts))
        receipt = receipts[0]
        self.assertEqual(receipt['source'], 'https://research.example/paper')
        self.assertEqual(receipt['sha256'], hashlib.sha256(TEXT.encode()).hexdigest())
        reopened = Captures(Store(self.temp.name))
        self.assertEqual(reopened.recent(), {'items': [receipt], 'more': False})
        self.assertEqual(reopened.original(value['id'])[0], TEXT.encode())


    def test_conflicting_id_and_integrity(self):
        value = sample()
        self.captures.save(value)
        with self.assertRaises(ValueError):
            self.captures.save({**value, 'content': 'different'})
        with self.store.connect() as db:
            db.execute('UPDATE blinders_captures SET original=?', (b'changed',))
        with self.assertRaisesRegex(ValueError, 'receipt'):
            self.captures.original(value['id'])

    def test_invalid_input_leaves_no_capture(self):
        for change in [{'kind': 'html'}, {'kind': 'png', 'content': '%'},
                       {'kind': 'png', 'content': 'YQ=='}, {'kind': 'png', 'content': 'iVBORw0KGgo='}, {'content': ''},
                       {'source': 'file:///private'}, {'source': 'https://name:secret@example.org/path'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.captures.save({**sample(), **change})
        self.assertEqual(self.captures.recent()['items'], [])

    def test_command_line_original_bytes(self):
        for kind, original in [('text', TEXT.encode()), ('png', PNG)]:
            with self.subTest(kind=kind):
                completed = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'bin/blinders'),
                    kind, '--source', 'https://example.org/research', '--title', 'CLI'],
                    input=original, capture_output=True, check=True,
                    env={**os.environ, 'STENCIL_DATA_DIR': self.temp.name})
                receipt = json.loads(completed.stdout)
                self.assertEqual(self.captures.original(receipt['id'])[0], original)

    def test_authenticated_page_save_and_download(self):
        server = make_server(self.store, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(path, payload=None, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            try:
                conn.request('POST' if payload else 'GET', path, body=json.dumps(payload) if payload else None,
                             headers=headers or {})
                response = conn.getresponse()
                return response.status, response.getheader('Content-Type'), response.read()
            finally:
                conn.close()
        try:
            self.assertIn(b'Blinders', request('/')[2])
            self.assertIn(server.token.encode(), request('/blinders')[2])
            self.assertEqual(request('/blinders.js')[0], 200)
            headers = {'X-Stencil-Token': server.token, 'Content-Type': 'application/json'}
            self.assertEqual(request('/api/blinders', sample())[0], 403)
            self.assertEqual(request('http://127.0.0.1:' + str(server.server_port) + '/api/blinders')[0], 403)
            self.assertEqual(request('/api/blinders', sample(), {**headers, 'Origin': 'https://elsewhere.test'})[0], 403)
            for kind, data in [('text', TEXT.encode()), ('png', PNG)]:
                value = sample(kind)
                status, _, body = request('/api/blinders', value, headers)
                self.assertEqual(status, 200, body)
                receipt = json.loads(body)
                path = '/api/blinders/original/' + receipt['id']
                self.assertEqual(request(path)[0], 403)
                self.assertEqual(request(path, headers=headers)[2], data)
            self.assertEqual(len(json.loads(request('/api/blinders', headers=headers)[2])['items']), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)


class BridgeTests(unittest.TestCase):
    def test_timeout_and_late_reply(self):
        from bridge import Bridge
        from time import monotonic
        bridge = Bridge()
        with self.assertRaisesRegex(ValueError, 'connect'):
            bridge.capture('png')
        bridge.pair, bridge.seen = str(uuid4()), monotonic()
        with self.assertRaisesRegex(ValueError, 'time'):
            bridge.capture('text', timeout=0.01)
        with self.assertRaisesRegex(ValueError, 'expired'):
            bridge.finish({'id': 'late'}, None)

    def test_mcp_capture_reads_from_same_store(self):
        from unittest.mock import patch
        from agent_mcp import answer
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'BLINDERS_DATA_DIR': tmp}):
            receipt = Captures(Store(tmp)).save(sample())
            def call(name, args):
                return answer({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                               'params': {'name': name, 'arguments': args}})['result']
            excerpt = call('blinders_read_text', {'id': receipt['id'], 'limit': 4})
            self.assertEqual(json.loads(excerpt['content'][0]['text'])['text'], TEXT[:4])
            self.assertTrue(call('blinders_read_text', {'id': receipt['id'], 'limit': -1})['isError'])
