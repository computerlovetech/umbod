#!/usr/bin/python3
"""Test-only MCP fixture. Never packaged into the app."""
import sys, json, os
if "--require-env" in sys.argv and not os.environ.get("UMBOD_FIXTURE_SECRET"):
    sys.exit(2)
if "--pid-file" in sys.argv:
    with open(sys.argv[sys.argv.index("--pid-file") + 1], "w") as handle:
        handle.write(str(os.getpid()))
for line in sys.stdin:
    try:
        r = json.loads(line)
        if 'id' not in r: continue
        method = r.get('method')
        if method == 'initialize':
            result = {'protocolVersion': '2025-11-25', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'umbod-test-fixture', 'version': '1'}}
        elif method == 'tools/list':
            # Two pages exercise SDK pagination.
            if r.get('params', {}).get('cursor') == 'second':
                result = {'tools': [{'name': 'new', 'description': 'Unapproved tool', 'inputSchema': {'type': 'object'}}]}
            else:
                result = {'tools': [{'name': 'echo', 'description': 'Fixture echo', 'inputSchema': {'type': 'object', 'properties': {'text': {'type':'string'}}, 'required':['text'], 'additionalProperties': False}}], 'nextCursor': 'second'}
        elif method == 'tools/call':
            result = {'content': [{'type': 'text', 'text': r['params']['arguments']['text']}]}
        elif method == 'ping': result = {}
        else:
            print(json.dumps({'jsonrpc':'2.0', 'id':r['id'], 'error':{'code':-32601, 'message':'Unsupported'}}), flush=True)
            continue
        print(json.dumps({'jsonrpc':'2.0', 'id':r['id'], 'result':result}), flush=True)
    except (ValueError, KeyError): pass
