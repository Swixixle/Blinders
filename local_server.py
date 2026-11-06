"""Loopback-only inbox for Blinders. Run via the CLI."""
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from urllib.parse import parse_qs, urlsplit
import webbrowser

from bridge import Bridge
from captures import Captures, MAX_REQUEST, Store, data_directory

WEB = Path(__file__).resolve().parent / 'web'
ASSETS = {'/blinders.js': 'text/javascript', '/style.css': 'text/css'}


def port():
    value = int(os.environ.get('BLINDERS_PORT', '8787'))
    if not 0 < value < 65536:
        raise ValueError('BLINDERS_PORT must be in the range 1–65535.')
    return value


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send(self, code, body, mime='application/json'):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Blinders-Store', self.server.store_key)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def dispatch(self, post=False):
        url = urlsplit(self.path)
        host = '127.0.0.1:' + str(self.server.server_port)
        if self.headers.get('Host') != host or self.headers.get('Origin', 'http://' + host) != 'http://' + host:
            return self.send(403, {'error': 'Open Blinders at its printed loopback address.'})
        if url.path.startswith('/api/') and not hmac.compare_digest(
                self.headers.get('X-Stencil-Token', '').encode(), self.server.token.encode()):
            return self.send(403, {'error': 'Reload the Blinders inbox.'})
        captures = self.server.captures
        if post:
            length = int(self.headers.get('Content-Length', 0))
            if self.headers.get_content_type() != 'application/json' or not 0 < length <= MAX_REQUEST:
                raise ValueError('Expected a bounded JSON capture request.')
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError('Expected a JSON object.')
            if url.path == '/api/blinders':
                return self.send(200, captures.save(value))
            if url.path == '/api/agent/capture':
                return self.send(200, self.server.bridge.capture(value.get('kind'), value.get('selector')))
            if url.path == '/api/bridge/next':
                return self.send(200, self.server.bridge.next(value.get('pair'), value.get('title')))
            if url.path == '/api/bridge/finish':
                return self.send(200, self.server.bridge.finish(value, captures))
        else:
            if url.path in ('/', '/blinders'):
                page = (WEB / 'blinders.html').read_text(encoding='utf-8').replace('__TOKEN__', self.server.token)
                return self.send(200, page.encode(), 'text/html; charset=utf-8')
            if url.path in ASSETS:
                return self.send(200, (WEB / url.path[1:]).read_bytes(), ASSETS[url.path])
            if url.path == '/api/blinders':
                return self.send(200, captures.recent(int(parse_qs(url.query).get('offset', [0])[0])))
            if url.path.startswith('/api/blinders/original/'):
                data, mime = captures.original(url.path.rsplit('/', 1)[-1])
                return self.send(200, data, mime)
            if url.path == '/api/agent/status':
                return self.send(200, self.server.bridge.status())
        self.send(404, {'error': 'Unknown Blinders route.'})

    def handle_request(self, post):
        try:
            self.dispatch(post)
        except (ValueError, KeyError) as error:
            self.send(400, {'error': str(error)})
        except sqlite3.Error:
            self.send(500, {'error': 'Could not access the local capture database.'})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)


def make_server(store, listen_port):
    server = ThreadingHTTPServer(('127.0.0.1', listen_port), Handler)
    server.store_key = hashlib.sha256(os.fsencode(store.directory.resolve())).hexdigest()
    server.token = secrets.token_hex(32)
    server.captures = Captures(store)
    server.bridge = Bridge()
    return server


def agent_request(path, value=None):
    conn = http.client.HTTPConnection('127.0.0.1', port(), timeout=28)
    try:
        conn.request('GET', '/blinders')
        page = conn.getresponse()
        token = re.search(rb'<meta name="stencil-token" content="([a-f0-9]{64})">', page.read())
        store_key = hashlib.sha256(os.fsencode(data_directory().resolve())).hexdigest()
        if page.getheader('X-Blinders-Store') != store_key:
            raise ValueError('The local port serves a different inbox. Check BLINDERS_PORT and the records directory.')
        if not token:
            raise ValueError('The configured local port does not serve the Blinders inbox.')
        headers = {'X-Stencil-Token': token[1].decode(), 'Content-Type': 'application/json'}
        conn.request('POST' if value is not None else 'GET', path,
                     body=json.dumps(value) if value is not None else None, headers=headers)
        response = conn.getresponse()
        result = json.loads(response.read())
        if response.status != 200:
            raise ValueError(result.get('error', 'The Blinders inbox rejected the request.'))
        return result
    except ConnectionRefusedError:
        raise ValueError('Start the local inbox with blinders open.') from None
    finally:
        conn.close()


def serve(open_browser=True):
    address = f'http://127.0.0.1:{port()}/blinders'
    try:
        server = make_server(Store(data_directory()), port())
    except OSError:
        # Reuse a running inbox only if its agent endpoint recognizes the protocol.
        agent_request('/api/agent/status')
        print('Using the running Blinders inbox at', address, flush=True)
        if open_browser:
            webbrowser.open(address)
        return
    print('Blinders inbox:', address, flush=True)
    print('Load unpacked Chrome extension:', WEB.parent / 'browser', flush=True)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
