#!/usr/bin/env python3
"""Bundled gateway/bridge activation acceptance test. Labeled local fixtures ONLY.
Never reads real client config or user credentials. Creates/removes one fixture identity.
"""
import json, os, pathlib, select, subprocess, sys, tempfile, time, urllib.request, urllib.error
binary = pathlib.Path(sys.argv[1]).resolve()
fixture = pathlib.Path(__file__).resolve().parent / 'fixture_issues.py'
with tempfile.TemporaryDirectory(prefix='umbod-activation-FIXTURE-') as temporary:
    root = pathlib.Path(temporary).resolve()
    data = root / 'data'
    config = root / 'claude_desktop_config.json'
    original = b'{"theme":"fixture","mcpServers":{"existing":{"command":"untouched"}}}'
    config.write_bytes(original)
    owner = bridge = None
    client = None
    admin = 'labeled-local-fixture-owner-token'
    def start():
        global owner, ready
        owner = subprocess.Popen([str(binary), 'serve', '--data-dir', str(data)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        owner.stdin.write(json.dumps({'admin_token':admin})+'\n'); owner.stdin.flush()
        assert select.select([owner.stdout],[],[],15)[0], 'Owner readiness timeout'
        ready = json.loads(owner.stdout.readline())
    def action(body, allowed_error=False):
        request = urllib.request.Request('http://'+ready['management']+'/manage',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+admin,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=45) as response: return json.load(response)
        except urllib.error.HTTPError as e:
            if allowed_error: return {'rejected':e.code}
            raise
    def rpc(method, params=None):
        global sequence
        sequence += 1
        request={'jsonrpc':'2.0','id':sequence,'method':method}
        if params is not None: request['params']=params
        bridge.stdin.write(json.dumps(request)+'\n');bridge.stdin.flush()
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            assert select.select([bridge.stdout],[],[],15)[0], 'Bridge response timeout'
            line=bridge.stdout.readline();assert line,'Bridge exited'
            response=json.loads(line)
            if response.get('id')==sequence:return response
        raise AssertionError('Response missing')
    try:
        start()
        journey=action({'action':'activation_start','diagnostics':True});client=journey['client'];server=journey['server']
        assert action({'action':'activation_start'})['client']==client
        action({'action':'server_save','server':{'id':server,'name':'GitHub issues LOCAL FIXTURE','transport':'stdio','command':'/usr/bin/python3','args':[str(fixture)]}})
        # Mark this as an isolated fixture in its own stopped configuration, never via production API.
        owner.stdin.close();owner.wait(timeout=10);owner=None
        saved=json.loads((data/'config.json').read_bytes());saved['activation']['fixture']=True
        (data/'config.json').write_text(json.dumps(saved))
        start()
        action({'action':'connect','id':server})
        preview=action({'action':'client_preview','path':str(config),'command':str(binary)})
        assert config.read_bytes()==original
        assert action({'action':'client_apply','preview':preview['id']},True)['rejected']==400
        action({'action':'client_apply','preview':preview['id'],'consent':True})
        entry=json.loads(config.read_bytes())['mcpServers'][preview['entry_name']]
        bridge=subprocess.Popen([entry['command']]+entry['args'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        sequence=0
        assert 'result' in rpc('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'Umbod-labeled-fixture-client-NOT-Claude','version':'1'}})
        bridge.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');bridge.stdin.flush()
        assert rpc('tools/list')['result']['tools']==[]
        assert 'error' in rpc('tools/call',{'name':server+'.search_issues','arguments':{}})
        action({'action':'activation_approve','client':client,'server':server,'tools':['search_issues','issue_read'],'consent':True})
        assert len(rpc('tools/list')['result']['tools'])==2
        assert 'error' in rpc('tools/call',{'name':server+'.create_issue','arguments':{}})
        assert rpc('tools/call',{'name':server+'.search_issues','arguments':{'fail':True}})['result']['isError'] is True
        assert action({'action':'status'})['activation']['activated'] is False
        assert 'result' in rpc('tools/call',{'name':server+'.search_issues','arguments':{'query':'FIXTURE_DO_NOT_RECORD'}})
        state=action({'action':'status'})
        assert state['activation']['activated'] and state['activation']['fixture']
        assert state['diagnostics']['events']['fixture_successful_call']==1
        assert 'downstream_successful_call' not in state['diagnostics']['events']
        assert 'FIXTURE_DO_NOT_RECORD' not in (data/'config.json').read_text()
        action({'action':'grant','client':client,'tool':server+'.search_issues','allow':False})
        assert 'error' in rpc('tools/call',{'name':server+'.search_issues','arguments':{}})
        port=ready['gateway'];owner.stdin.close();owner.wait(timeout=10);owner=None
        start();assert ready['gateway']==port
        action({'action':'connect','id':server})
        assert len(rpc('tools/list')['result']['tools'])==1, 'Live bridge must recover after owner restart'
        bridge.stdin.close();bridge.wait(timeout=10);bridge=None
        state=action({'action':'status'});assert state['activation']['activated'] and state['activation']['fixture']
        assert server+'.search_issues' not in state['allowed_tools']
        changed=config.read_bytes()+b'\n';config.write_bytes(changed)
        assert action({'action':'client_undo','consent':True},True)['rejected']==400
        config.write_bytes(changed[:-1])
        action({'action':'client_undo','consent':True});assert config.read_bytes()==original
        action({'action':'diagnostics_set','enabled':False})
        assert action({'action':'status'})['diagnostics']['events']=={}
        print('PASS: supplied gateway owner → fixture integration → deny → exact grants → consent/backup → generated bridge config → failed/successful downstream activation → revoke → restart/stable endpoint → safe undo → erase diagnostics')
        print('BOUNDARY: labeled local MCP and client fixture; no GitHub/Claude account or real config used')
    finally:
        if bridge and bridge.poll() is None: bridge.terminate();bridge.wait(timeout=10)
        if owner and owner.poll() is None:
            if client:
                action({'action':'client_remove','id':client})
            owner.stdin.close();owner.wait(timeout=10)
