#!/usr/bin/python3
"""Labeled local MCP fixture, NOT GitHub validation. No network requests."""
import sys, json
for line in sys.stdin:
    r = json.loads(line)
    if 'id' not in r: continue
    if r['method'] == 'initialize':
        result = {'protocolVersion':'2025-11-25','capabilities':{'tools':{}},'serverInfo':{'name':'umbod-issues-FIXTURE','version':'1'}}
    elif r['method'] == 'tools/list':
        result = {'tools':[{'name':n,'description':'FIXTURE '+n,'inputSchema':{'type':'object'}} for n in ['issue_read','list_issues','search_issues','create_issue','future_read_tool']]}
    elif r['method'] == 'tools/call':
        result = {'content':[{'type':'text','text':'Labeled fixture result'}], 'isError':r.get('params',{}).get('arguments',{}).get('fail',False)}
    else: result = {}
    print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
