#!/usr/bin/env python3
"""Actual bundled backend + labeled loopback OAuth/HTTP MCP fixture. No provider accounts."""
import base64, hashlib, http.server, json, pathlib, select, subprocess, sys, tempfile, threading, urllib.parse, urllib.request, urllib.error, uuid
state={'refreshes':0,'challenge':'','access':'fixture-access-0'}
class Fixture(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,code,value):
        data=json.dumps(value).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path=='/.well-known/oauth-protected-resource/mcp': self.send(200,{'resource':base+'/mcp','authorization_servers':[base]})
        elif self.path=='/.well-known/oauth-authorization-server':self.send(200,{'issuer':base,'authorization_endpoint':base+'/authorize','token_endpoint':base+'/token','registration_endpoint':base+'/register','code_challenge_methods_supported':['S256']})
        else:self.send(405,{})
    def do_POST(self):
        data=self.rfile.read(int(self.headers.get('Content-Length','0')))
        if self.path=='/register':self.send(200,{'client_id':'labeled-fixture-native-client','token_endpoint_auth_method':'none'});return
        if self.path=='/token':
            p=urllib.parse.parse_qs(data.decode());assert p['resource']==[base+'/mcp']
            if p['grant_type']==['authorization_code']:
                challenge=base64.urlsafe_b64encode(hashlib.sha256(p['code_verifier'][0].encode()).digest()).decode().rstrip('=');assert challenge==state['challenge'];assert p['code']==['fixture-code']
            else:
                assert p['refresh_token']==['fixture-refresh'];state['refreshes']+=1;state['access']='fixture-access-'+str(state['refreshes'])
            self.send(200,{'access_token':state['access'],'refresh_token':'fixture-refresh','token_type':'Bearer','expires_in':3600});return
        if self.path!='/mcp':self.send(404,{});return
        if self.headers.get('Authorization')!='Bearer '+state['access']:self.send(401,{});return
        p=json.loads(data)
        if 'id' not in p:self.send(202,{});return
        if p['method']=='initialize':result={'protocolVersion':p['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':'Labeled-local-OAuth-MCP-fixture','version':'1'}}
        elif p['method']=='tools/list':result={'tools':[{'name':'search_issues','description':'Fixture only','inputSchema':{'type':'object'}}]}
        elif p['method']=='tools/call':result={'content':[{'type':'text','text':'Labeled OAuth MCP fixture result'}]}
        else:result={}
        self.send(200,{'jsonrpc':'2.0','id':p['id'],'result':result})
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture);base='http://127.0.0.1:'+str(server.server_port)
threading.Thread(target=server.serve_forever,daemon=True).start()
binary=str(pathlib.Path(sys.argv[1]).resolve());identifier=uuid.uuid4().hex
with tempfile.TemporaryDirectory(prefix='umbod-OAuth-FIXTURE-') as temp:
    owner=subprocess.Popen([binary,'serve','--data-dir',temp],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    owner.stdin.write('{"admin_token":"labeled-fixture-owner-token"}\n');owner.stdin.flush();assert select.select([owner.stdout],[],[],15)[0]
    ready=json.loads(owner.stdout.readline())
    def action(value):
        request=urllib.request.Request('http://'+ready['management']+'/manage',data=json.dumps(value).encode(),headers={'Authorization':'Bearer labeled-fixture-owner-token','Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=45) as response:return json.load(response)
    try:
        action({'action':'server_save','server':{'id':identifier,'name':'Labeled local OAuth fixture','transport':'http','url':base+'/mcp'}})
        auth=action({'action':'oauth_begin','id':identifier})['url'];params=urllib.parse.parse_qs(urllib.parse.urlparse(auth).query)
        state['challenge']=params['code_challenge'][0];assert params['code_challenge_method']==['S256']
        callback=params['redirect_uri'][0]
        try:urllib.request.urlopen(callback+'?'+urllib.parse.urlencode({'state':'wrong-fixture-state','code':'fixture-code'}))
        except urllib.error.HTTPError as error:assert error.code==400
        else:raise AssertionError('Wrong state accepted')
        with urllib.request.urlopen(callback+'?'+urllib.parse.urlencode({'state':params['state'][0],'code':'fixture-code'})) as response:assert response.status==200
        action({'action':'connect','id':identifier});assert action({'action':'status'})['statuses'][identifier]=='Connected'
        action({'action':'oauth_refresh','id':identifier});assert state['refreshes']==1
        assert action({'action':'status'})['statuses'][identifier]=='Connected'
        assert any(t['name']==identifier+'.search_issues' for t in action({'action':'status'})['tools'])
        action({'action':'oauth_logout','id':identifier})
        assert action({'action':'status'})['statuses'][identifier]=='Signed out'
        assert not action({'action':'status'})['servers'][0]['oauth']
        assert not action({'action':'status'})['tools']
        assert 'fixture-access' not in pathlib.Path(temp,'config.json').read_text()
        print('PASS: actual bundled backend → local HTTP MCP/OAuth discovery → PKCE/state/callback → connect → refresh/reconnect with rotated token → rediscovery → logout/persisted signed-out state')
        print('BOUNDARY: labeled loopback provider fixture only; no real-provider validation')
    finally:
        action({'action':'server_remove','id':identifier});owner.stdin.close();owner.wait(timeout=10);server.shutdown();server.server_close()
