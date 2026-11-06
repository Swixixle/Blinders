"""Local command-line interface to the research inbox."""
import argparse
import base64
import json
import os
import sqlite3
import sys
from uuid import uuid4

from captures import Captures, MAX_BYTES, Store, data_directory
from local_server import agent_request, serve


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(prog='blinders', description=__doc__)
    commands = parser.add_subparsers(dest='op', required=True)
    launch = commands.add_parser('open', help='Open the local research inbox')
    launch.add_argument('--no-browser', action='store_true')
    commands.add_parser('status', help='Show the paired browser source')
    commands.add_parser('mcp', help='Serve Codex and Claude Code via stdio')
    capture = commands.add_parser('capture', help='Ask the paired browser for its selection or viewport')
    capture.add_argument('kind', choices=('text', 'png'))
    capture.add_argument('--selector', help='Capture rendered text of one matching visible element')
    for kind in ('text', 'png'):
        save = commands.add_parser(kind, help='Save original bytes from standard input')
        save.add_argument('--source', required=True)
        save.add_argument('--title', default='')
        save.add_argument('--id')
    recent = commands.add_parser('list', help='List local capture receipts')
    recent.add_argument('--offset', type=int, default=0)
    export = commands.add_parser('export', help='Write verified original bytes to standard output')
    export.add_argument('id')
    args = parser.parse_args()
    try:
        if args.op == 'open':
            return serve(not args.no_browser)
        if args.op == 'mcp':
            from agent_mcp import run
            return run()
        if args.op == 'status':
            result = agent_request('/api/agent/status')
        elif args.op == 'capture':
            result = agent_request('/api/agent/capture', {'kind': args.kind, 'selector': args.selector})
        else:
            captures = Captures(Store(data_directory()))
            if args.op == 'export':
                sys.stdout.buffer.write(captures.original(args.id)[0])
                return
            if args.op == 'list':
                result = captures.recent(args.offset)
            else:
                raw = sys.stdin.buffer.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError('Capture exceeds 12 MiB.')
                content = raw.decode('utf-8') if args.op == 'text' else base64.b64encode(raw).decode('ascii')
                result = captures.save({'id': args.id or str(uuid4()), 'kind': args.op,
                                        'source': args.source, 'title': args.title, 'content': content})
        print(json.dumps(result))
    except (ValueError, KeyError, OSError, sqlite3.Error) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
