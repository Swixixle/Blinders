"""Verbatim research captures. Originals are local and separate from model context."""
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3
import sys
import binascii
import hashlib
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

MAX_BYTES = 12 * 1024 * 1024
MAX_REQUEST = 6 * MAX_BYTES + 32768  # UTF-8 text may be escaped in JSON.
COLUMNS = 'id, kind, title, source, saved_at, sha256, bytes'


def data_directory():
    configured = os.environ.get('BLINDERS_DATA_DIR') or os.environ.get('STENCIL_DATA_DIR')
    if configured:
        return Path(configured).expanduser()
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/Stencil'
    return Path.home() / '.local/share/stencil'


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / 'stencil.sqlite3'
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=8)
        try:
            with db:
                yield db
        finally:
            db.close()


class Captures:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS blinders_captures (
                id TEXT PRIMARY KEY, kind TEXT, title TEXT, source TEXT, saved_at TEXT,
                sha256 TEXT, bytes INTEGER, original BLOB NOT NULL)''')

    def save(self, value):
        ident = value.get('id', '')
        try:
            if not isinstance(ident, str) or str(UUID(ident)) != ident:
                raise ValueError
        except ValueError:
            raise ValueError('Supply a canonical capture UUID.') from None
        source = value.get('source')
        title = value.get('title')
        if not isinstance(source, str) or len(source) > 8192 or not isinstance(title, str) or len(title) > 2048:
            raise ValueError('Invalid source address or page title.')
        url = urlsplit(source)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username is not None or url.password is not None:
            raise ValueError('Choose an HTTP or HTTPS source without credentials in its address.')
        source = urlunsplit((url.scheme, url.netloc, url.path, '', ''))
        kind, content = value.get('kind'), value.get('content')
        if not isinstance(content, str):
            raise ValueError('Capture content is missing.')
        if kind == 'text':
            data = content.encode('utf-8')
        elif kind == 'png':
            try:
                data = base64.b64decode(content, validate=True)
            except (ValueError, binascii.Error):
                raise ValueError('Invalid screenshot encoding.') from None
            if (not data.startswith(b'\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR')
                    or not data.endswith(b'\x00\x00\x00\x00IEND\xaeB`\x82')):
                raise ValueError('Expected a PNG screenshot.')
        else:
            raise ValueError('Choose text or PNG.')
        if not data or len(data) > MAX_BYTES:
            raise ValueError('A capture must contain 1 byte through 12 MiB. Capture a smaller passage or viewport.')
        digest = hashlib.sha256(data).hexdigest()
        values = (ident, kind, title, source, datetime.now(timezone.utc).isoformat(), digest, len(data))
        with self.store.connect() as db:
            db.execute(f'INSERT OR IGNORE INTO blinders_captures ({COLUMNS}, original) VALUES (?,?,?,?,?,?,?,?)',
                       (*values, data))
            row = db.execute(f'SELECT {COLUMNS} FROM blinders_captures WHERE id=?', (ident,)).fetchone()
            if row[1:4] != values[1:4] or row[5:] != values[5:]:
                raise ValueError('This capture ID already belongs to a different original.')
        return dict(zip(COLUMNS.split(', '), row))

    def recent(self, offset=0):
        if offset < 0:
            raise ValueError('Invalid capture offset.')
        with self.store.connect() as db:
            rows = db.execute(f'SELECT {COLUMNS} FROM blinders_captures ORDER BY rowid DESC LIMIT 51 OFFSET ?',
                              (offset,)).fetchall()
        return {'items': [dict(zip(COLUMNS.split(', '), row)) for row in rows[:50]], 'more': len(rows) > 50}

    def original(self, ident):
        with self.store.connect() as db:
            row = db.execute('SELECT kind, original, sha256 FROM blinders_captures WHERE id=?', (ident,)).fetchone()
        if not row:
            raise KeyError('Unknown research capture.')
        kind, data, digest = row
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Stored bytes do not match the capture receipt.')
        return data, 'text/plain; charset=utf-8' if kind == 'text' else 'image/png'
