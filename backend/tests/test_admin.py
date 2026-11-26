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
