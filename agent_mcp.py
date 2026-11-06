"""Small, local stdio MCP server. Tool results contain receipts by default."""
import json
import sqlite3
import sys

from captures import Captures, Store, data_directory
from local_server import agent_request

VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')


def tool(name, description, props=None, required=()):
    schema = {'type': 'object', 'properties': props or {}, 'additionalProperties': False}
    if required:
        schema['required'] = list(required)
    return {'name': name, 'description': description, 'inputSchema': schema}


TOOLS = [
    tool('blinders_status', 'Check whether the local browser inbox is paired and identify the source tab.'),
    tool('blinders_capture_text', 'Save the current browser selection, or rendered text of one visible element matching selector. Return its local receipt.',
         {'selector': {'type': 'string', 'minLength': 1, 'maxLength': 1000}}),
    tool('blinders_capture_viewport', 'Save the visible viewport of the paired research tab as a PNG. Return its local receipt.'),
    tool('blinders_list', 'List recent local capture receipts (50 per page).',
         {'offset': {'type': 'integer', 'minimum': 0}}),
    tool('blinders_read_text', 'Read a specified excerpt from a saved text capture into this assistant session.',
         {'id': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0},
          'limit': {'type': 'integer', 'minimum': 1, 'maximum': 8000}}, ('id',))
]


def call(name, args):
    spec = next((item for item in TOOLS if item['name'] == name), None)
    if not spec or not isinstance(args, dict):
        raise ValueError('Unknown tool or invalid arguments.')
    schema = spec['inputSchema']
    if set(args) - set(schema['properties']) or set(schema.get('required', [])) - set(args):
        raise ValueError('Unexpected or missing tool arguments.')
    for key, value in args.items():
        field = schema['properties'][key]
        if field['type'] == 'string' and (not isinstance(value, str) or
                not field.get('minLength', 0) <= len(value) <= field.get('maxLength', sys.maxsize)):
            raise ValueError('Invalid ' + key)
        if field['type'] == 'integer' and (type(value) is not int or
                not field.get('minimum', 0) <= value <= field.get('maximum', sys.maxsize)):
            raise ValueError('Invalid ' + key)
    if name == 'blinders_status':
        return agent_request('/api/agent/status')
    if name in ('blinders_capture_text', 'blinders_capture_viewport'):
        kind = 'text' if name == 'blinders_capture_text' else 'png'
        return agent_request('/api/agent/capture', {'kind': kind, **args})
    captures = Captures(Store(data_directory()))
    if name == 'blinders_list':
        return captures.recent(args.get('offset', 0))
    raw, mime = captures.original(args['id'])
    if not mime.startswith('text/'):
        raise ValueError('This capture is a PNG.')
    original = raw.decode('utf-8')
    start, limit = args.get('offset', 0), args.get('limit', 4000)
    return {'text': original[start:start + limit], 'offset': start, 'total_chars': len(original)}


def answer(request):
    if not isinstance(request, dict) or request.get('jsonrpc') != '2.0':
        return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request'}}
    if 'id' not in request:
        return None
    result = {'jsonrpc': '2.0', 'id': request['id']}
    method = request.get('method')
    params = request.get('params', {})
    if not isinstance(params, dict):
        return {**result, 'error': {'code': -32602, 'message': 'Expected object parameters'}}
    if method == 'initialize':
        version = params.get('protocolVersion')
        payload = {'protocolVersion': version if version in VERSIONS else VERSIONS[0],
                   'serverInfo': {'name': 'blinders', 'version': '0.1.0'}, 'capabilities': {'tools': {}}}
    elif method == 'ping':
        payload = {}
    elif method == 'tools/list':
        payload = {'tools': TOOLS}
    elif method == 'tools/call':
        try:
            value = call(params.get('name'), params.get('arguments', {}))
            payload = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}]}
        except (ValueError, KeyError, OSError, sqlite3.Error) as error:
            payload = {'content': [{'type': 'text', 'text': str(error)}], 'isError': True}
    else:
        return {**result, 'error': {'code': -32601, 'message': 'Unknown method'}}
    return {**result, 'result': payload}


def run():
    for line in sys.stdin.buffer:
        try:
            response = answer(json.loads(line))
        except (ValueError, UnicodeError):
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Invalid JSON'}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=True), flush=True)
