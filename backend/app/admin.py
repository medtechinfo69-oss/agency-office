"""Persistent workspace administration. Owner access remains backwards compatible.
Invitations are single-use links, delivered by the owner (no email service implied).
All administrative mutations are protected by the same resource policy as legacy APIs.
"""
import hashlib
import hmac
import os
import re
import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from . import db

router = APIRouter(prefix='/api/admin', tags=['administration'])
RESOURCES = ['projects', 'agents', 'connections', 'access', 'users', 'roles', 'instance', 'settings', 'logs', 'billing']
STARTED = time.time()
SCHEMA = '''
CREATE TABLE IF NOT EXISTS admin_users (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 role TEXT NOT NULL, status TEXT NOT NULL, password_hash TEXT NOT NULL DEFAULT '',
 session_version INTEGER NOT NULL DEFAULT 0, invite_hash TEXT NOT NULL DEFAULT '',
 invite_expires REAL NOT NULL DEFAULT 0, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_roles (id TEXT PRIMARY KEY, permissions TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admin_keys (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, prefix TEXT NOT NULL, token_hash TEXT NOT NULL,
 role TEXT NOT NULL, created_at REAL NOT NULL, last_used REAL, revoked INTEGER NOT NULL DEFAULT 0
);
'''


def initialize():
    from . import account_security
    account_security.initialize()
    db.get_conn().executescript(SCHEMA)
    db.get_conn().commit()
    for role in ['Admin', 'Manager', 'Editor', 'Viewer']:
        permissions = {r: {'read': True, 'write': role == 'Admin' or (role == 'Editor' and r in ('projects', 'agents'))} for r in RESOURCES}
        db.execute('INSERT INTO admin_roles(id,permissions) VALUES(?,?) ON CONFLICT(id) DO NOTHING', (role, db.jdump(permissions)))
    db.execute("INSERT INTO admin_users(id,name,email,role,status,created_at) VALUES('owner','Workspace owner','','Owner','active',?) ON CONFLICT(id) DO NOTHING", (time.time(),))


def password_hash(value):
    salt = secrets.token_hex(16)
    return salt + ':' + hashlib.pbkdf2_hmac('sha256', value.encode(), bytes.fromhex(salt), 260000).hex()


def password_valid(value, stored):
    try:
        salt, digest = stored.split(':')
        candidate = hashlib.pbkdf2_hmac('sha256', value.encode(), bytes.fromhex(salt), 260000).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError): return False


def user(uid):
    return db.one('SELECT * FROM admin_users WHERE id=?', (uid,))


def public_user(row):
    return {**{k: row[k] for k in ('id', 'name', 'email', 'role', 'status', 'created_at')}, 'last_login': db.kv_get('last_login_'+row['id']), 'avatar': db.jload(db.kv_get('profile_preferences_'+row['id'],'{}'),{}).get('avatar','')}


def version(uid):
    row = user(uid)
    return row['session_version'] if row and row['status'] == 'active' else -1


def login(email, password, fallback):
    row = db.one('SELECT * FROM admin_users WHERE lower(email)=? AND id<>?', (email.strip().lower(), 'owner')) if email.strip() else user('owner')
    if not row or row['status'] != 'active': return None
    valid = password_valid(password, row['password_hash']) if row['password_hash'] else (row['id'] == 'owner' and hmac.compare_digest(hashlib.sha256(password.encode()).digest(), hashlib.sha256(fallback.encode()).digest()))
    return row['id'] if valid else None


def permits(identity, resource, write=False, action=None):
    if identity['role'] == 'Owner': return True
    role = db.one('SELECT permissions FROM admin_roles WHERE id=?', (identity['role'],))
    policy = db.jload(role['permissions'], {}).get(resource, {}) if role else {}
    return bool(policy.get(action, policy.get('write' if write else 'read', False)))


def resource(path):
    path = path.removeprefix('/api/')
    if path.startswith(('sitebuilder/settings','sitebuilder/ollama','sitebuilder/providers')): return 'connections'
    if path.startswith('admin/'):
        group = path.split('/')[1]
        return {'keys': 'access', 'roles': 'roles', 'users': 'users', 'diagnostics': 'instance', 'instance': 'instance', 'configuration': 'instance', 'storage': 'instance', 'health-checks': 'instance', 'policy': 'access', 'audit': 'logs', 'agent-detail': 'agents', 'agent-control': 'agents', 'models': 'connections'}.get(group, 'settings')
    if path.startswith(('providers', 'settings', 'models')): return 'connections'
    if path.startswith(('agents', 'prompts')): return 'agents'
    if path.startswith(('health',)): return 'instance'
    return 'projects'


def key_identity(token):
    if not token.startswith('ao_'): return None
    row = db.one('SELECT * FROM admin_keys WHERE token_hash=? AND revoked=0', (hashlib.sha256(token.encode()).hexdigest(),))
    if not row: return None
    db.execute('UPDATE admin_keys SET last_used=? WHERE id=?', (time.time(), row['id']))
    return {'id': row['id'], 'name': row['name'], 'role': row['role'], 'api_key': True}


def current(request):
    identity = getattr(request.state, 'identity', None)
    if identity and identity.get('api_key'): raise HTTPException(403, 'Use a signed-in browser session for account management.')
    return identity or public_user(user('owner'))


@router.get('/me')
def me(request: Request):
    identity = current(request)
    return {**identity, 'permissions': {r: {a: permits(identity, r, a != 'read', action=a) for a in ('read', 'write', 'create', 'edit', 'delete')} for r in RESOURCES}}


class Profile(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(default='', max_length=254)


def email_valid(value):
    if value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value): raise HTTPException(422, 'Enter a valid email address.')


@router.put('/me')
def profile(body: Profile, request: Request):
    identity = current(request)
    email_valid(body.email)
    if not body.name.strip(): raise HTTPException(422, 'Name is required.')
    if db.one('SELECT id FROM admin_users WHERE lower(email)=? AND id<>?', (body.email.lower(), identity['id'])): raise HTTPException(409, 'Email already in use.')
    db.execute('UPDATE admin_users SET name=?,email=? WHERE id=?', (body.name.strip(), body.email.lower(), identity['id']))
    return public_user(user(identity['id']))


class Password(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(min_length=16, max_length=1024)


@router.post('/me/password')
def change_password(body: Password, request: Request):
    identity = current(request)
    row = user(identity['id'])
    access = request.app.state.owner_access
    valid = password_valid(body.current_password, row['password_hash']) if row['password_hash'] else hmac.compare_digest(hashlib.sha256(body.current_password.encode()).digest(), hashlib.sha256(access.password.encode()).digest())
    if not valid: raise HTTPException(400, 'Current password is incorrect.')
    db.execute('UPDATE admin_users SET password_hash=?,session_version=session_version+1 WHERE id=?', (password_hash(body.new_password), identity['id']))
    return {'ok': True, 'sign_in_again': True}


@router.get('/users')
def users():
    return [public_user(r) for r in db.query('SELECT * FROM admin_users ORDER BY created_at')]


class Invite(Profile):
    role: str = 'Viewer'


def check_grant(request, role):
    """A delegated user/key administrator cannot mint broader privileges."""
    if request is None: return  # internal calls; HTTP routes always inject Request
    identity = getattr(request.state, 'identity', None)
    if not identity or identity['role'] == 'Owner': return
    for resource_name in RESOURCES:
        for action in ('read','write','create','edit','delete'):
            if permits({'role': role}, resource_name, action!='read', action=action) and not permits(identity, resource_name, action!='read', action=action):
                raise HTTPException(403, 'You cannot assign a role with permissions beyond your own.')


@router.post('/users')
def invite(body: Invite, request: Request = None):
    check_grant(request, body.role)
    email_valid(body.email)
    if not body.email: raise HTTPException(422, 'Email is required.')
    if not db.one('SELECT id FROM admin_roles WHERE id=?', (body.role,)): raise HTTPException(422, 'Choose an existing role.')
    if db.one('SELECT id FROM admin_users WHERE lower(email)=?', (body.email.lower(),)): raise HTTPException(409, 'This email is already invited or registered.')
    token = secrets.token_urlsafe(32)
    uid = db.new_id('usr')
    db.execute("INSERT INTO admin_users(id,name,email,role,status,invite_hash,invite_expires,created_at) VALUES(?,?,?,?,'invited',?,?,?)", (uid, body.name, body.email.lower(), body.role, hashlib.sha256(token.encode()).hexdigest(), time.time()+86400, time.time()))
    return {'user': public_user(user(uid)), 'invite_token': token, 'expires_in': 86400, 'delivery': 'Copy the single-use link and share it securely. Email is not sent automatically.'}


class UserUpdate(BaseModel):
    role: str


@router.patch('/users/{uid}')
def update_user(uid: str, body: UserUpdate, request: Request = None):
    check_grant(request, body.role)
    if uid == 'owner': raise HTTPException(409, 'The owner role cannot be changed.')
    if not db.one('SELECT id FROM admin_roles WHERE id=?', (body.role,)): raise HTTPException(422, 'Unknown role.')
    if not user(uid): raise HTTPException(404, 'User not found.')
    db.execute('UPDATE admin_users SET role=?,session_version=session_version+1 WHERE id=?', (body.role, uid))
    return {'ok': True}


@router.delete('/users/{uid}')
def delete_user(uid: str, request: Request):
    if uid in ('owner', current(request)['id']): raise HTTPException(409, 'You cannot remove the owner or your own account.')
    db.execute('DELETE FROM admin_users WHERE id=?', (uid,))
    return {'ok': True}


class Accept(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=16, max_length=1024)


def accept_invite(body):
    row = db.one("UPDATE admin_users SET password_hash=?,status='active',invite_hash='',invite_expires=0 WHERE invite_hash=? AND invite_expires>? AND status='invited' RETURNING id", (password_hash(body.password), hashlib.sha256(body.token.encode()).hexdigest(), time.time()))
    if not row: raise HTTPException(400, 'This invitation has expired or was already used.')
    return {'ok': True}


@router.get('/roles')
def roles():
    return [{'id': r['id'], 'permissions': db.jload(r['permissions'], {}), 'member_count': db.one('SELECT count(*) AS n FROM admin_users WHERE role=?',(r['id'],))['n']} for r in db.query('SELECT * FROM admin_roles ORDER BY id')]


class Role(BaseModel):
    permissions: dict[str, dict[str, bool]]


@router.put('/roles/{rid}')
def save_role(rid: str, body: Role, request: Request = None):
    if not db.one('SELECT id FROM admin_roles WHERE id=?', (rid,)): raise HTTPException(404, 'Unknown role.')
    permissions = {}
    for r in RESOURCES:
        incoming=body.permissions.get(r,{})
        value={a:bool(incoming.get(a,incoming.get('write',False) if a!='read' else False)) for a in ('read','write','create','edit','delete')}
        value['write']=any(value[a] for a in ('create','edit','delete'))
        permissions[r]=value
    for value in permissions.values():
        if value['write']: value['read'] = True
    identity = getattr(request.state, 'identity', None) if request else None
    if identity and identity['role'] != 'Owner':
        for resource_name, grants in permissions.items():
            for action, allowed in grants.items():
                if allowed and not permits(identity, resource_name, action != 'read', action=action):
                    raise HTTPException(403, 'You cannot grant permissions beyond your own.')
    db.execute('UPDATE admin_roles SET permissions=? WHERE id=?', (db.jdump(permissions), rid))
    return {'ok': True}


@router.get('/keys')
def keys():
    return [{k: r[k] for k in ('id', 'name', 'prefix', 'role', 'created_at', 'last_used', 'revoked')} for r in db.query('SELECT * FROM admin_keys ORDER BY created_at DESC')]


class Key(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: str = 'Viewer'


def mint_key(kid, name, role):
    if not db.one('SELECT id FROM admin_roles WHERE id=?', (role,)): raise HTTPException(422, 'Unknown role.')
    token = 'ao_' + secrets.token_urlsafe(32)
    db.execute('INSERT INTO admin_keys(id,name,prefix,token_hash,role,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET token_hash=excluded.token_hash,prefix=excluded.prefix,revoked=0,created_at=excluded.created_at', (kid, name, token[:10], hashlib.sha256(token.encode()).hexdigest(), role, time.time()))
    return {'token': token, 'message': 'Copy this key now. Only its hash is stored; it will not be shown again.'}


@router.post('/keys')
def create_key(body: Key, request: Request = None):
    check_grant(request, body.role)
    return mint_key(db.new_id('key'), body.name, body.role)


@router.post('/keys/{kid}/regenerate')
def regenerate_key(kid: str, request: Request = None):
    row = db.one('SELECT * FROM admin_keys WHERE id=?', (kid,))
    if not row: raise HTTPException(404, 'Key not found.')
    check_grant(request, row['role'])
    return mint_key(kid, row['name'], row['role'])


@router.delete('/keys/{kid}')
def revoke_key(kid: str):
    db.execute('UPDATE admin_keys SET revoked=1 WHERE id=?', (kid,))
    return {'ok': True}


@router.get('/instance')
def instance():
    return {'version': '1.1.0', 'commit': os.getenv('VERCEL_GIT_COMMIT_SHA', 'development')[:8], 'environment': os.getenv('APP_ENV', 'local'), 'platform': 'Vercel' if os.getenv('VERCEL') else 'Python server', 'region': os.getenv('VERCEL_REGION', 'Not reported'), 'database': 'Supabase Postgres' if os.getenv('DATABASE_URL') else 'SQLite', 'uptime_seconds': round(time.time()-STARTED), 'uptime_scope': 'Current function process; resets on cold start', 'restart_supported': False, 'restart_url': 'https://vercel.com/medtechinfo69-oss-projects/backend', 'event_transport': 'Polling' if os.getenv('VERCEL') else 'WebSocket'}


@router.get('/diagnostics')
def diagnostics():
    start = time.perf_counter()
    db.one('SELECT 1')
    logs = [dict(r) for r in db.query('SELECT * FROM activity ORDER BY created_at DESC LIMIT 100')]
    return {**instance(), 'database_ms': round((time.perf_counter()-start)*1000), 'checked_at': time.time(), 'active_runtimes': db.one("SELECT count(*) AS n FROM agents WHERE status IN ('working','thinking','reviewing')")['n'], 'logs': logs}


class AgentControl(BaseModel):
    enabled: bool


@router.post('/agent-control/{aid}')
def agent_control(aid: str, body: AgentControl):
    if not db.one('SELECT id FROM agents WHERE id=?', (aid,)): raise HTTPException(404, 'Agent not found.')
    if not body.enabled and db.one("SELECT id FROM tasks WHERE assignee=? AND status='progress'", (aid,)): raise HTTPException(409, 'Agent is running a task. Pause the project first; in-flight provider calls cannot be terminated safely.')
    db.kv_set('agent_enabled_' + aid, '1' if body.enabled else '0')
    return {'ok': True, 'enabled': body.enabled}
