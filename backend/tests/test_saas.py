"""Tenant security tests on disposable data. No live providers or keys."""
import asyncio
import concurrent.futures
import json
import time
import pytest
from fastapi.testclient import TestClient
from app import db,saas,vault
from app.provider import ChatResult,Usage
from tests.test_admin import setup, PASSWORD

@pytest.fixture
def env(setup,monkeypatch):
    app,owner,access=setup
    app.include_router(saas.router);app.include_router(saas.ai_router)
    monkeypatch.setenv('SAAS_ENFORCE_MFA','true')
    monkeypatch.setenv('SAAS_MODE','true')
    db.execute('INSERT INTO account_security(uid,secret,enabled) VALUES(?,?,1)',('owner',vault.encrypt('TESTONLY')))
    clients=[]
    def agency(name,plan='Starter'):
        response=owner.post('/api/saas/platform/agencies',json={'name':name,'owner_name':name+' Owner','email':name.lower()+'@example.test','plan':plan,'days':30})
        assert response.status_code==200,response.text
        data=response.json();client=TestClient(app,base_url='https://testserver');clients.append(client)
        assert client.post('/api/auth/invite/accept',json={'token':data['invite_token'],'password':PASSWORD}).status_code==200
        assert client.post('/api/auth/login',json={'email':name.lower()+'@example.test','password':PASSWORD}).status_code==200
        return client,data['tenant_id']
    yield app,owner,agency
    for c in clients:c.close()


def test_isolation_url_body_and_legacy_surface(env):
    app,owner,agency=env;a,ta=agency('Alpha');b,tb=agency('Beta')
    project=a.post('/api/saas/projects',json={'name':'Private Alpha','brief':'Confidential brand strategy'}).json()['id']
    assert b.get('/api/saas/projects/'+project).status_code==404
    assert b.post('/api/saas/projects/'+project+'/advance').status_code==404
    assert b.get('/api/saas/projects',headers={'X-Tenant-ID':ta}).json()==[]
    assert b.post('/api/saas/projects',json={'name':'Attack','brief':'test','tenant_id':ta}).status_code==422
    for path in ['/api/projects','/api/providers','/api/settings','/api/models','/api/admin/users','/api/admin/roles','/api/sitebuilder/projects','/media/secret.png','/api/cloud/events']:
        assert b.get(path).status_code==403,path
    for path in ['/api/saas/platform/agencies','/api/saas/platform/usage','/api/saas/platform/catalog','/api/saas/platform/agencies/'+ta+'/export']:
        assert b.get(path).status_code==403
    assert b.get('/api/saas/me').json()['user']['tenant_id']==tb
    assert 'Confidential' not in b.get('/api/saas/projects').text


def test_expiry_suspension_and_read_only(env):
    _,owner,agency=env;a,tid=agency('Expired')
    db.execute('UPDATE saas_licenses SET expires=? WHERE tenant_id=?',(time.time()-10,tid))
    assert a.get('/api/saas/projects').status_code==200
    assert a.post('/api/saas/projects',json={'name':'Nope','brief':'No writes'}).status_code==402
    assert a.post('/api/ai',json={'request_id':'expired-1','prompt':'hello'}).status_code==402
    assert a.get('/api/saas/me').json()['read_only']
    assert owner.put('/api/saas/platform/agencies/'+tid+'/license',json={'plan':'Starter','status':'trial','days':5}).status_code==200
    assert a.post('/api/saas/projects',json={'name':'Yes','brief':'Renewed'}).status_code==200
    owner.patch('/api/saas/platform/agencies/'+tid,json={'name':'Expired','status':'suspended'})
    assert a.get('/api/saas/projects').status_code==403


def test_agent_limit_history_and_other_tenant_ids(env):
    _,owner,agency=env;a,tid=agency('Agents');b,_=agency('Other')
    db.execute('UPDATE saas_licenses SET overrides=? WHERE tenant_id=?',(json.dumps({'max_agents':1}),tid))
    payload={'template_id':'catalog_0','name':'Our Manager'}
    aid=a.post('/api/saas/agents',json=payload).json()['id']
    assert a.post('/api/saas/agents',json=payload).status_code==409
    assert b.delete('/api/saas/agents/'+aid).status_code==404
    now=time.time();db.execute("INSERT INTO saas_tasks(id,tenant_id,project_id,agent_id,title,status,created,updated) VALUES('history',?, 'project',?,'Kept','done',?,?)",(tid,aid,now,now))
    assert a.delete('/api/saas/agents/'+aid).status_code==200
    assert db.one('SELECT * FROM saas_tasks WHERE id=?',('history',))['agent_id']==aid
    assert a.post('/api/saas/agents',json=payload).status_code==200


def test_mfa_gate_and_impersonation_audit(env):
    _,owner,agency=env;a,tid=agency('Support')
    assert owner.post('/api/saas/platform/agencies/'+tid+'/impersonate',json={'reason':'Support investigation'}).status_code==200
    assert owner.get('/api/saas/me').json()['user']['impersonating']
    assert owner.get('/api/saas/platform/agencies').status_code==403
    assert owner.get('/api/providers').status_code==403
    assert owner.get('/api/saas/projects').status_code==200
    assert owner.delete('/api/saas/impersonation').status_code==200
    rows=owner.get('/api/saas/platform/audit').json()
    assert any(r['action']=='impersonation.start' and r['tenant_id']==tid and r['user_id']=='owner' and r['ip'] for r in rows)
    db.execute("UPDATE account_security SET enabled=0 WHERE uid='owner'")
    assert owner.get('/api/saas/platform/agencies').status_code==428
    assert owner.get('/api/projects').status_code==428
    assert owner.get('/api/saas/me').json()['mfa_required']
    assert owner.get('/api/admin/me/security').status_code==404 # router absent, not blocked


def allow_ai(tid,monkeypatch,requests=10,tokens=1000000):
    from app.config import settings
    db.kv_set('catalog_openai',json.dumps({'valid':True,'models':[{'id':'test-model','free':False}]}))
    db.kv_set('token_openai','test-server-only-secret')
    db.execute('UPDATE saas_licenses SET overrides=? WHERE tenant_id=?',(json.dumps({'models':['openai/test-model'],'premium':True,'monthly_requests':requests,'monthly_tokens':tokens}),tid))
    async def chat(self,messages,**kwargs):return ChatResult('Real fixture output',Usage(tokens_in=100,tokens_out=50,model='test-model'))
    monkeypatch.setattr('app.provider.OpenAIProvider.chat',chat)


def test_gateway_idempotency_quota_cost_secrecy_and_model_denial(env,monkeypatch):
    _,owner,agency=env;a,tid=agency('Usage');allow_ai(tid,monkeypatch,requests=1)
    body={'request_id':'unique-request','prompt':'Create a caption'}
    assert a.post('/api/ai',json={**body,'model':'openai/not-allowed'}).status_code==403
    first=a.post('/api/ai',json=body);assert first.status_code==200,first.text
    again=a.post('/api/ai',json=body);assert again.status_code==200 and again.json()['cached']
    assert a.post('/api/ai',json={**body,'prompt':'Different'}).status_code==409
    assert a.post('/api/ai',json={**body,'request_id':'second-request'}).status_code==429
    usage=a.get('/api/saas/usage');assert usage.json()['totals']['requests']==1
    assert 'estimated_cost' not in usage.text and 'test-server-only-secret' not in usage.text
    assert 'test-server-only-secret' not in a.get('/api/saas/connections').text
    assert db.one('SELECT value FROM settings_kv WHERE key=?',('token_openai',))['value'].startswith('enc:v1:')


def test_concurrent_requests_cannot_exceed_quota(env,monkeypatch):
    _,_,agency=env;a,tid=agency('Concurrent');allow_ai(tid,monkeypatch,requests=1)
    async def slow(self,messages,**kwargs):
        await asyncio.sleep(.05)
        return ChatResult('ok',Usage(tokens_in=20,tokens_out=10))
    monkeypatch.setattr('app.provider.OpenAIProvider.chat',slow)
    def call(i):return a.post('/api/ai',json={'request_id':'concurrent-'+str(i),'prompt':'Caption'}).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:results=list(executor.map(call,range(6)))
    assert results.count(200)==1,results
    assert results.count(429)==5,results
    assert db.one('SELECT count(*) AS n FROM saas_usage WHERE tenant_id=?',(tid,))['n']==1


def test_real_delegation_persists_assignments_outputs_and_review(env,monkeypatch):
    _,_,agency=env;a,tid=agency('Delegation');allow_ai(tid,monkeypatch)
    manager=a.post('/api/saas/agents',json={'template_id':'catalog_0','name':'Director'}).json()['id']
    writer=a.post('/api/saas/agents',json={'template_id':'catalog_4','name':'Writer'}).json()['id']
    pid=a.post('/api/saas/projects',json={'name':'Campaign','brief':'A fact-based campaign'}).json()['id']
    async def chat(self,messages,**kwargs):
        prompt=messages[-1]['content']
        text=json.dumps({'tasks':[{'agent_id':writer,'title':'Write three campaign captions'}]}) if 'Create an execution plan' in prompt else 'Three useful captions.' if 'As Manager' not in prompt else 'Reviewed final campaign with limitations.'
        return ChatResult(text,Usage(tokens_in=20,tokens_out=30))
    monkeypatch.setattr('app.provider.OpenAIProvider.chat',chat)
    response=a.post('/api/saas/projects/'+pid+'/delegate',json={'request_id':'campaign-unique','prompt':'Create a campaign'})
    assert response.status_code==200,response.text
    assert len(response.json()['tasks'])==2
    assert a.post('/api/saas/projects/'+pid+'/advance').status_code==200
    final=a.post('/api/saas/projects/'+pid+'/advance');assert final.status_code==200,final.text
    assert all(t['status']=='done' for t in final.json()['tasks'])
    assert len(final.json()['messages'])==3
    assert a.delete('/api/saas/agents/'+writer).status_code==200
    assert len(a.get('/api/saas/projects/'+pid).json()['messages'])==3


def test_member_permissions_and_support_private_notes(env):
    app,owner,agency=env;a,tid=agency('Team')
    invitation=a.post('/api/saas/team',json={'name':'Member','email':'member@example.test','role':'member'}).json()
    member=TestClient(app,base_url='https://testserver')
    assert member.post('/api/auth/invite/accept',json={'token':invitation['invite_token'],'password':PASSWORD}).status_code==200
    assert member.post('/api/auth/login',json={'email':'member@example.test','password':PASSWORD}).status_code==200
    assert member.post('/api/saas/projects',json={'name':'No','brief':'Denied'}).status_code==403
    assert member.post('/api/saas/team',json={'name':'Escalate','email':'evil@example.test','role':'tenant_admin'}).status_code==403
    ticket=member.post('/api/saas/tickets',json={'subject':'Help','message':'Please help me'}).json()['id']
    owner.patch('/api/saas/platform/tickets/'+ticket,json={'status':'in_progress','internal_note':'PRIVATE INTERNAL NOTE'})
    assert 'PRIVATE INTERNAL NOTE' not in member.get('/api/saas/tickets').text
    assert a.delete('/api/saas/team/'+a.get('/api/saas/me').json()['user']['id']).status_code==409
    member.close()


def test_tenant_builder_scopes_files_versions_exports_and_generation(env,monkeypatch):
    from app import tenant_builder,sitebuilder
    app,owner,agency=env;app.include_router(tenant_builder.router)
    a,tid=agency('Builder');b,_=agency('BuilderOther');allow_ai(tid,monkeypatch)
    files=sitebuilder.render_site({'business':'Private Brand','headline':'Private Brand','services':[],'faq':[]})
    async def chat(self,messages,**kwargs):return ChatResult(json.dumps({'files':files}),Usage(tokens_in=50,tokens_out=500))
    monkeypatch.setattr('app.provider.OpenAIProvider.chat',chat)
    response=a.post('/api/saas/builder/projects',json={'name':'Secret website','brief':'Brand brief'})
    assert response.status_code==200,response.text
    pid=response.json()['id']
    assert b.get('/api/saas/builder/projects/'+pid).status_code==404
    assert b.get('/api/saas/builder/projects/'+pid+'/export').status_code==404
    generated=a.post('/api/saas/builder/projects/'+pid+'/generate',json={'prompt':'Build our website','mode':'build'})
    assert '"type": "done"' in generated.text,generated.text
    versions=a.get('/api/saas/builder/projects/'+pid+'/versions').json()
    assert len(versions)==2
    vid=versions[0]['id']
    assert b.get('/api/saas/builder/projects/'+pid+'/versions/'+vid).status_code==404
    assert a.post('/api/saas/builder/projects/'+pid+'/versions/'+vid+'/restore').status_code==200
    assert a.get('/api/saas/builder/projects/'+pid+'/export').content.startswith(b'PK')
    assert len(a.get('/api/saas/usage').json()['rows'])==1


def test_fallback_attempts_are_metered_and_errors_do_not_leak_keys(env,monkeypatch):
    _,owner,agency=env;a,tid=agency('Fallback');allow_ai(tid,monkeypatch)
    db.kv_set('catalog_openai',json.dumps({'valid':True,'models':[{'id':'failed','free':False},{'id':'healthy','free':False}]}))
    db.execute('UPDATE saas_licenses SET overrides=? WHERE tenant_id=?',(json.dumps({'models':['openai/failed','openai/healthy'],'premium':True}),tid))
    async def chat(self,messages,**kwargs):
        if self.cfg.model=='failed':raise RuntimeError('UPSTREAM test-server-only-secret')
        return ChatResult('Successful fallback',Usage(tokens_in=10,tokens_out=10))
    monkeypatch.setattr('app.provider.OpenAIProvider.chat',chat)
    result=a.post('/api/ai',json={'request_id':'fallback-unique','prompt':'Caption'})
    assert result.status_code==200 and result.json()['model']=='healthy'
    assert 'test-server-only-secret' not in result.text
    attempts=db.query('SELECT * FROM saas_ai_attempts WHERE tenant_id=?',(tid,))
    assert len(attempts)==2 and {r['status'] for r in attempts}=={'error','done'}


def test_image_gateway_idempotency_feature_quota_and_isolation(env,monkeypatch):
    from fastapi.responses import Response
    _,owner,agency=env;a,tid=agency('Images');b,tb=agency('OtherImages')
    body={'request_id':'image-unique','prompt':'A truthful brand illustration'}
    assert a.post('/api/ai/image',json=body).status_code==403
    db.execute('UPDATE saas_licenses SET overrides=? WHERE tenant_id=?',(json.dumps({'features':['ai','image'],'monthly_requests':1}),tid))
    async def image(request):return Response(b'\x89PNG\r\n\x1a\nfixture',media_type='image/png')
    monkeypatch.setattr('app.ai_hub.image',image)
    assert a.post('/api/ai/image',json=body).status_code==200
    assert a.post('/api/ai/image',json=body).content.startswith(b'\x89PNG')
    assert a.post('/api/ai/image',json={**body,'request_id':'image-second'}).status_code==429
    assert a.get('/api/saas/usage').json()['totals']['requests']==1
    assert b.post('/api/ai/image',json=body).status_code==403


def test_auth_session_reads_do_not_exhaust_signin_rate_bucket(setup):
    from app import guardrails
    from fastapi import FastAPI
    guardrails.initialize()
    app=FastAPI();app.add_middleware(guardrails.RequestGuard)
    @app.get('/api/auth/session')
    def session():return {'required':True}
    @app.post('/api/auth/login')
    def login():return {'ok':True}
    client=TestClient(app)
    for _ in range(20):assert client.get('/api/auth/session').status_code==200
    for _ in range(12):assert client.post('/api/auth/login',json={}).status_code==200
    assert client.post('/api/auth/login',json={}).status_code==429


def test_legacy_admin_is_not_a_second_platform_owner(env):
    app,owner,agency=env;a,tid=agency('Assigned')
    invitation=owner.post('/api/admin/users',json={'name':'Legacy Admin','email':'legacy@example.test','role':'Admin'}).json()
    c=TestClient(app,base_url='https://testserver')
    assert c.post('/api/auth/invite/accept',json={'token':invitation['invite_token'],'password':PASSWORD}).status_code==200
    assert c.post('/api/auth/login',json={'email':'legacy@example.test','password':PASSWORD}).status_code==200
    assert c.get('/api/providers').status_code==403
    assert c.get('/api/saas/platform/agencies').status_code==403
    uid=invitation['user']['id']
    assert owner.post('/api/saas/platform/agencies/'+tid+'/assign/'+uid,json={'role':'member'}).status_code==200
    assert c.get('/api/saas/me').status_code==401
    assert c.post('/api/auth/login',json={'email':'legacy@example.test','password':PASSWORD}).status_code==200
    assert c.get('/api/saas/me').json()['user']['tenant_id']==tid
    assert c.put('/api/providers',json={'provider':'openai','token':'attempt'}).status_code==403
    c.close()


def test_csrf_cross_site_and_boss_mfa_cannot_be_disabled(env):
    from app.account_security import router
    app,owner,_=env;app.include_router(router)
    assert owner.post('/api/admin/me/totp/disable',json={'password':PASSWORD,'otp':'000000'}).status_code==409
    assert owner.post('/api/saas/platform/demo-agencies',json={},headers={'Origin':'https://evil.example'}).status_code==403
    assert owner.post('/api/saas/platform/demo-agencies',json={},headers={'sec-fetch-site':'cross-site'}).status_code==403
