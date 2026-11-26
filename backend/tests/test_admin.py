"""Authorization regression tests. Disposable SQLite; no live credentials/providers."""
import os
import sys
import time
import hashlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import admin, db
from app.config import settings
from app.access import OwnerAccess, OwnerAccessMiddleware, auth_router

PASSWORD = 'test-only-owner-password-1234'

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.setattr(settings, 'db_path', str(tmp_path / 'admin.db'))
    monkeypatch.setattr(db, '_conn', None)
    admin.initialize()
    access = OwnerAccess(managed=True, production=True, password=PASSWORD, secret='test-signing-key-with-over-32-characters', origins=('https://testserver',))
    app = FastAPI()
    app.state.owner_access = access
    app.add_middleware(OwnerAccessMiddleware, access=access)
    app.include_router(auth_router(access))
    app.include_router(admin.router)
    @app.get('/api/projects')
    def projects(): return []
    @app.post('/api/projects')
    def project(): return {'ok': True}
    @app.put('/api/providers')
    def provider(): return {'ok': True}
    with TestClient(app, base_url='https://testserver') as owner:
        assert owner.post('/api/auth/login', json={'password': PASSWORD}).status_code == 200
        yield app, owner, access
    db._conn.close()


def member(app, owner, email='viewer@example.test', role='Viewer'):
    invite = owner.post('/api/admin/users', json={'name': 'A viewer', 'email': email, 'role': role})
    assert invite.status_code == 200, invite.text
    token = invite.json()['invite_token']
    row = db.one('SELECT * FROM admin_users WHERE email=?', (email,))
    assert row['invite_hash'] != token and row['invite_hash'] == hashlib.sha256(token.encode()).hexdigest()
    client = TestClient(app, base_url='https://testserver')
    assert client.post('/api/auth/invite/accept', json={'token': token, 'password': 'test-member-password-1234'}).status_code == 200
    assert client.post('/api/auth/invite/accept', json={'token': token, 'password': 'test-member-password-1234'}).status_code == 400
    assert client.post('/api/auth/login', json={'email': email, 'password': 'test-member-password-1234'}).status_code == 200
    return client, row['id']


def test_invites_and_rbac_enforced_on_existing_apis(setup):
    app, owner, _ = setup
    viewer, uid = member(app, owner)
    assert viewer.get('/api/projects').status_code == 200
    assert viewer.post('/api/projects').status_code == 403
    assert viewer.put('/api/providers').status_code == 403
    assert viewer.post('/api/admin/users', json={'name': 'x','email':'evil@example.test'}).status_code == 403
    assert owner.patch('/api/admin/users/' + uid, json={'role': 'Editor'}).status_code == 200
    assert viewer.get('/api/projects').status_code == 401  # old sessions revoked
    assert viewer.post('/api/auth/login', json={'email': 'viewer@example.test', 'password': 'test-member-password-1234'}).status_code == 200
    assert viewer.post('/api/projects').status_code == 200
    assert owner.delete('/api/admin/users/' + uid).status_code == 200
    assert viewer.get('/api/projects').status_code == 401


def test_api_key_once_scoped_rotated_revoked(setup):
    app, owner, _ = setup
    result = owner.post('/api/admin/keys', json={'name': 'read only', 'role': 'Viewer'})
    token = result.json()['token']
    keys = owner.get('/api/admin/keys').json()
    assert token not in str(keys) and 'token_hash' not in str(keys)
    key = keys[0]['id']
    client = TestClient(app, base_url='https://testserver', headers={'Authorization':'Bearer '+token})
    assert client.get('/api/projects').status_code == 200
    assert client.post('/api/projects').status_code == 403
    assert client.put('/api/admin/me', json={'name':'evil'}).status_code == 403
    replacement = owner.post('/api/admin/keys/' + key + '/regenerate').json()['token']
    assert replacement != token
    assert client.get('/api/projects').status_code == 401
    client.headers['Authorization'] = 'Bearer ' + replacement
    assert client.get('/api/projects').status_code == 200
    assert owner.delete('/api/admin/keys/' + key).status_code == 200
    assert client.get('/api/projects').status_code == 401


def test_owner_protection_password_change_and_profile(setup):
    app, owner, _ = setup
    assert owner.delete('/api/admin/users/owner').status_code == 409
    assert owner.patch('/api/admin/users/owner', json={'role':'Viewer'}).status_code == 409
    assert owner.put('/api/admin/me', json={'name':'Owner new name','email':'owner@example.test'}).status_code == 200
    assert owner.get('/api/admin/me').json()['name'] == 'Owner new name'
    assert owner.post('/api/admin/me/password', json={'current_password':'bad','new_password':'a-new-test-password-1234'}).status_code == 400
    assert owner.post('/api/admin/me/password', json={'current_password':PASSWORD,'new_password':'a-new-test-password-1234'}).status_code == 200
    assert owner.get('/api/projects').status_code == 401
    assert owner.post('/api/auth/login', json={'password':PASSWORD}).status_code == 401
    assert owner.post('/api/auth/login', json={'password':'a-new-test-password-1234'}).status_code == 200
    assert 'a-new-test-password-1234' not in str(dict(admin.user('owner')))


def test_roles_persist_and_update_live_policy(setup):
    app, owner, _ = setup
    viewer, uid = member(app, owner)
    roles = owner.get('/api/admin/roles').json()
    policy = next(r['permissions'] for r in roles if r['id']=='Viewer')
    policy['projects']['write'] = True
    assert owner.put('/api/admin/roles/Viewer',json={'permissions':policy}).status_code == 200
    assert viewer.post('/api/projects').status_code == 200
    policy['projects']['write'] = False
    assert owner.put('/api/admin/roles/Viewer',json={'permissions':policy}).status_code == 200
    assert viewer.post('/api/projects').status_code == 403
    assert owner.put('/api/admin/roles/Owner',json={'permissions':policy}).status_code == 404


def test_expired_invite_csrf_and_validation(setup):
    app, owner, _ = setup
    result=owner.post('/api/admin/users',json={'name':'Expired','email':'expired@example.test'}).json()
    db.execute('UPDATE admin_users SET invite_expires=? WHERE email=?',(time.time()-1,'expired@example.test'))
    client=TestClient(app,base_url='https://testserver')
    assert client.post('/api/auth/invite/accept',json={'token':result['invite_token'],'password':'test-member-password-1234'}).status_code==400
    assert owner.post('/api/admin/keys',headers={'Origin':'https://evil.example'},json={'name':'evil'}).status_code==403
    assert owner.post('/api/admin/users',json={'name':'Bad','email':'invalid'}).status_code==422
    assert client.post('/api/auth/invite/accept',json={'token':'short','password':'short'}).status_code==422
    assert client.get('/api/admin/users').status_code==401
    assert owner.get('/api/admin/diagnostics').status_code==200


def test_schema_initialization_preserves_existing_data(setup):
    app, owner, _ = setup
    profile = owner.put('/api/admin/me', json={'name': 'Do not reset', 'email':'keep@example.test'}).json()
    role = owner.get('/api/admin/roles').json()[0]
    original = owner.post('/api/admin/keys', json={'name':'persist'}).json()['token']
    admin.initialize()
    assert admin.user('owner')['name'] == profile['name']
    assert db.one('SELECT permissions FROM admin_roles WHERE id=?', (role['id'],))['permissions'] == db.jdump(role['permissions'])
    assert admin.key_identity(original)['name'] == 'persist'


def test_delegated_administrator_cannot_escalate_via_roles(setup):
    app, owner, _ = setup
    viewer, uid = member(app, owner)
    policy = next(r['permissions'] for r in owner.get('/api/admin/roles').json() if r['id']=='Viewer')
    policy['users']['write'] = policy['access']['write'] = True
    assert owner.put('/api/admin/roles/Viewer', json={'permissions':policy}).status_code == 200
    assert viewer.post('/api/admin/keys',json={'name':'privilege escalation','role':'Admin'}).status_code == 403
    assert viewer.post('/api/admin/users',json={'name':'Escalation','email':'escalate@example.test','role':'Admin'}).status_code == 403
    assert viewer.patch('/api/admin/users/'+uid,json={'role':'Admin'}).status_code == 403
    assert viewer.post('/api/admin/keys',json={'name':'safe delegation','role':'Viewer'}).status_code == 200


def test_vault_encrypts_existing_and_new_credentials(setup, monkeypatch):
    from app import vault
    monkeypatch.setenv('SESSION_SECRET','stable-secret-for-vault-tests-only')
    db.execute('INSERT INTO settings_kv(key,value) VALUES(?,?)',('token_openrouter','legacy-test-credential'))
    vault.migrate()
    raw=db.one("SELECT value FROM settings_kv WHERE key='token_openrouter'")['value']
    assert raw.startswith('enc:v1:') and 'legacy-test-credential' not in raw
    assert db.kv_get('token_openrouter')=='legacy-test-credential'
    db.kv_set('token_openrouter','replacement-test-credential')
    assert db.kv_get('token_openrouter')=='replacement-test-credential'
    vault.migrate()
    assert db.kv_get('token_openrouter')=='replacement-test-credential'
    monkeypatch.setenv('SESSION_SECRET','wrong-secret')
    with pytest.raises(RuntimeError):db.kv_get('token_openrouter')


def test_totp_recovery_codes_and_server_session_revocation(setup):
    from app.account_security import router, code
    app,owner,access=setup
    app.include_router(router)
    second=TestClient(app,base_url='https://testserver')
    assert second.post('/api/auth/login',json={'password':PASSWORD}).status_code==200
    result=owner.post('/api/admin/me/totp/setup',json={'password':PASSWORD})
    assert result.status_code==200,result.text
    secret=result.json()['secret']
    assert secret not in db.one("SELECT secret FROM account_security WHERE uid='owner'")['secret']
    enable=owner.post('/api/admin/me/totp/enable',json={'otp':code(secret,int(time.time())//30)})
    assert enable.status_code==200,enable.text
    backups=enable.json()['backup_codes']
    assert len(backups)==8
    assert second.get('/api/projects').status_code==401
    assert second.post('/api/auth/login',json={'password':PASSWORD}).status_code==401
    assert second.post('/api/auth/login',json={'password':PASSWORD,'otp':backups[0]}).status_code==200
    assert second.post('/api/auth/login',json={'password':PASSWORD,'otp':backups[0]}).status_code==401
    assert owner.get('/api/admin/me/security').json()['recovery_codes_remaining']==7
    assert owner.post('/api/admin/me/sessions/sign-out-others').status_code==200
    assert second.get('/api/projects').status_code==401
    assert owner.get('/api/projects').status_code==200
    assert owner.post('/api/admin/me/totp/disable',json={'password':PASSWORD,'otp':backups[1]}).status_code==200
    assert second.post('/api/auth/login',json={'password':PASSWORD}).status_code==200
    cookie=second.cookies.get('ao_session')
    assert second.post('/api/auth/logout').status_code==204
    second.cookies.set('ao_session',cookie)
    assert second.get('/api/projects').status_code==401


def test_persistent_rate_limit_and_json_guards(setup):
    from app import guardrails
    app,owner,access=setup
    guardrails.initialize()
    assert guardrails.consume('actor',2)
    assert guardrails.consume('actor',2)
    assert not guardrails.consume('actor',2)
    for value in [{'a':'\x00'}, {'a':float('nan')}]:
        if 'a' in value and isinstance(value['a'],str):
            with pytest.raises(ValueError):guardrails.shape(value)
    wrapped=FastAPI()
    wrapped.add_middleware(guardrails.RequestGuard)
    @wrapped.post('/api/echo')
    async def echo(request:__import__('starlette.requests',fromlist=['Request']).Request):return await request.json()
    client=TestClient(wrapped)
    assert client.post('/api/echo',content='{bad',headers={'Content-Type':'application/json'}).status_code==422
    assert client.post('/api/echo',json={'v':'\x00'}).status_code==422
    assert client.post('/api/echo',content='x'*2000001,headers={'Content-Type':'application/json'}).status_code==413
    assert client.post('/api/echo',json={'ok':True}).json()=={'ok':True}


def test_extended_admin_crud_and_policy(setup):
    from app.admin_extended import router
    from app import guardrails
    app,owner,access=setup
    guardrails.initialize()
    app.include_router(router)
    assert owner.post('/api/admin/roles',json={'name':'Custom team','copy_from':'Viewer'}).status_code==200
    assert owner.delete('/api/admin/roles/Admin').status_code==409
    assert owner.delete('/api/admin/roles/Custom%20team').status_code==200
    assert owner.put('/api/admin/policy',json={'session_minutes':5,'allowed_ips':['invalid']}).status_code==422
    assert owner.put('/api/admin/policy',json={'session_minutes':5,'allowed_ips':[]}).status_code==200
    token=access.issue('session',99999)
    import base64,json
    data=json.loads(base64.urlsafe_b64decode(token.split('.')[0]+'=='))
    assert data['exp']<time.time()+301
    assert owner.put('/api/admin/configuration',json={'name':'Do not reset','timezone':'Africa/Tunis','language':'en','retention_days':15}).status_code==200
    assert owner.get('/api/admin/configuration').json()['name']=='Do not reset'
    assert owner.get('/api/admin/storage').status_code==200
    assert owner.post('/api/admin/storage/purge-logs',json={'confirmation':'bad'}).status_code==422
    assert owner.post('/api/admin/storage/purge-logs',json={'confirmation':'PURGE LOGS'}).status_code==200


def test_edited_discovery_cannot_exfiltrate_saved_credentials(setup,monkeypatch):
    from app.routers.api import provider_models
    from app.config import settings
    from app import ai_hub
    from unittest.mock import AsyncMock
    app,owner,access=setup
    app.post('/api/providers/{key}/models')(provider_models)
    viewer,_=member(app,owner)
    monkeypatch.setattr(settings,'provider_creds',{'openrouter':{'token':'server-only-secret','base_url':'https://openrouter.ai/api/v1'}})
    fetch=AsyncMock(return_value={'valid':True,'models':[{'id':'test:free','free':True}]})
    monkeypatch.setattr('app.provider.fetch_models',fetch)
    monkeypatch.setattr(ai_hub,'validate_endpoint',lambda *a,**k:None)
    assert viewer.post('/api/providers/openrouter/models',json={'base_url':'https://attacker.example/v1'}).status_code==403
    fetch.assert_not_called()
    assert viewer.post('/api/providers/openrouter/models',json={}).status_code==200
    assert 'server-only-secret' not in viewer.get('/api/admin/me').text


def test_model_hub_global_selection_benchmark_and_fallback(setup,monkeypatch):
    from app import ai_hub
    from app.config import settings
    from unittest.mock import AsyncMock
    app,owner,access=setup
    app.include_router(ai_hub.router)
    monkeypatch.setattr(settings,'active_provider','openrouter')
    monkeypatch.setattr(settings,'text_model','old:free')
    monkeypatch.setattr(settings,'provider_creds',{'openrouter':{'token':'server-secret','model':'old:free','base_url':'https://openrouter.ai/api/v1'},'ollama':{'token':'','model':'local-code','base_url':'http://localhost:11434/v1'}})
    db.kv_set('catalog_ollama',__import__('json').dumps({'valid':True,'models':[{'id':'local-code','free':True,'tags':['Local','Code']}],'checked_at':time.time()}))
    result=owner.put('/api/models/selection',json={'provider':'ollama','model':'local-code','image_model':'pollinations-free'})
    assert result.status_code==200,result.text
    assert result.json()['model']=='local-code'
    from app import sitebuilder
    assert sitebuilder.settings()['model']=='local-code'
    mocked=AsyncMock(return_value='{"answer":"valid output"}')
    monkeypatch.setattr(ai_hub,'complete',mocked)
    probe=owner.post('/api/models/benchmark',json={'role':'Developer','candidates':[{'provider':'ollama','model':'local-code'}]})
    assert probe.status_code==200,probe.text
    assert probe.json()['recommended']['json'] is True
    assert probe.json()['applied'] is False
    assert 'server-secret' not in probe.text
    # A removed/disconnected catalog cannot be selected from stale client state.
    assert owner.put('/api/providers/ollama/connection',json={'disconnected':True}).status_code==200
    assert owner.put('/api/models/selection',json={'provider':'ollama','model':'local-code'}).status_code==409
    db.kv_set('catalog_openrouter',__import__('json').dumps({'valid':True,'models':[{'id':'next:free','free':True}],'checked_at':time.time()}))
    fallback=owner.post('/api/models/fallback',json={'provider':'ollama','model':'local-code'})
    assert fallback.json()['changed'] is True
    assert fallback.json()['selection']['model']=='next:free'


def test_hosted_endpoint_validation_blocks_metadata_private_and_credentials(monkeypatch):
    from app.ai_hub import validate_endpoint
    from fastapi import HTTPException
    monkeypatch.setenv('VERCEL','1')
    for endpoint in ['http://localhost:11434','https://127.0.0.1/v1','https://169.254.169.254/latest','https://user:password@example.com','https://metadata.google.internal','file:///etc/passwd','https://example.com/?token=secret']:
        with pytest.raises(HTTPException): validate_endpoint(endpoint,local=True)
    assert validate_endpoint('https://openrouter.ai/api/v1')=='https://openrouter.ai/api/v1'


def test_delegated_role_admin_cannot_escalate_by_copy_or_edit(setup):
    from app.admin_extended import router
    app, owner, _ = setup
    app.include_router(router)
    policy={r:{'read':True,'write':False} for r in admin.RESOURCES}
    policy['roles']={'read':True,'write':True}
    db.execute('INSERT INTO admin_roles(id,permissions) VALUES(?,?)',('Delegated',db.jdump(policy)))
    delegated,_=member(app,owner,email='delegated@example.test',role='Delegated')
    assert delegated.post('/api/admin/roles',json={'name':'Escalated','copy_from':'Admin'}).status_code==403
    assert delegated.post('/api/admin/roles',json={'name':'Limited','copy_from':'Viewer'}).status_code==200
    assert delegated.put('/api/admin/roles/Limited',json={'permissions':{r:{'read':True,'write':True} for r in admin.RESOURCES}}).status_code==403
    assert delegated.put('/api/admin/roles/Limited',json={'permissions':policy}).status_code==200


def test_account_preferences_are_private_validated_and_signout_all(setup):
    from app.account_security import router
    app,owner,_=setup
    app.include_router(router)
    viewer,_=member(app,owner)
    assert owner.get('/api/admin/me/preferences').json()['language']=='en'
    prefs={'language':'fr','activity_notifications':False,'sound':False,'avatar':''}
    assert viewer.put('/api/admin/me/preferences',json=prefs).status_code==200
    assert viewer.get('/api/admin/me/preferences').json()==prefs
    assert owner.get('/api/admin/me/preferences').json()['language']=='en'
    for bad in ({'language':'invalid'},{'avatar':'data:image/svg+xml;base64,xxx'},{'avatar':'data:image/png;base64,YmFk'}):
        assert viewer.put('/api/admin/me/preferences',json=bad).status_code==422
    assert viewer.post('/api/admin/me/sessions/sign-out-all',json={'confirmation':'bad'}).status_code==422
    assert viewer.post('/api/admin/me/sessions/sign-out-all',json={'confirmation':'SIGN OUT'}).status_code==200
    assert viewer.get('/api/admin/me/preferences').status_code==401
    assert owner.get('/api/admin/me/preferences').status_code==200
