"""TOTP, recovery codes and individually revocable signed-in sessions."""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from . import admin, db, vault
router=APIRouter(prefix='/api/admin/me',tags=['account security'])
SCHEMA='''CREATE TABLE IF NOT EXISTS account_security (uid TEXT PRIMARY KEY, secret TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, backups TEXT NOT NULL DEFAULT '[]', last_counter INTEGER NOT NULL DEFAULT -1);
CREATE TABLE IF NOT EXISTS account_sessions (id TEXT PRIMARY KEY, uid TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, last_seen REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS account_sessions_user ON account_sessions(uid);'''


def initialize():
    db.get_conn().executescript(SCHEMA);db.get_conn().commit()


def code(secret,counter):
    key=base64.b32decode(secret+'='*(-len(secret)%8))
    digest=hmac.new(key,struct.pack('>Q',counter),hashlib.sha1).digest();offset=digest[-1]&15
    return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)


def verify(uid,otp):
    row=db.one('SELECT * FROM account_security WHERE uid=?',(uid,))
    if not row or not row['enabled']: return True
    secret=vault.decrypt(row['secret']);counter=int(time.time())//30
    for n in (counter-1,counter,counter+1):
        if n>row['last_counter'] and hmac.compare_digest(code(secret,n),otp):
            used=db.one('UPDATE account_security SET last_counter=? WHERE uid=? AND last_counter<? RETURNING uid',(n,uid,n))
            return bool(used)
    digest=hashlib.sha256(otp.encode()).hexdigest();backups=json.loads(row['backups'])
    if digest in backups:
        backups.remove(digest)
        return bool(db.one('UPDATE account_security SET backups=? WHERE uid=? AND backups=? RETURNING uid',(json.dumps(backups),uid,row['backups'])))
    return False


def session_id(token):
    try: return json.loads(base64.urlsafe_b64decode(token.split('.')[0]+'=='))['nonce']
    except Exception: return ''


@router.get('/security')
def status(request:Request):
    uid=admin.current(request)['id'];row=db.one('SELECT enabled,backups FROM account_security WHERE uid=?',(uid,))
    sessions=[dict(r) for r in db.query('SELECT id,created,expires,last_seen FROM account_sessions WHERE uid=? AND revoked=0 AND expires>? ORDER BY created DESC',(uid,time.time()))]
    current=session_id(request.cookies.get('ao_session',''))
    for s in sessions:s['current']=s['id']==current
    return {'totp_enabled':bool(row and row['enabled']),'recovery_codes_remaining':len(json.loads(row['backups'])) if row else 0,'sessions':sessions}


class PasswordProof(BaseModel):
    password:str=Field(min_length=1,max_length=1024)
    otp:str=Field(default='',max_length=100)


def prove(request,body):
    uid=admin.current(request)['id'];row=admin.user(uid)
    fallback=request.app.state.owner_access.password
    valid=admin.password_valid(body.password,row['password_hash']) if row['password_hash'] else uid=='owner' and hmac.compare_digest(hashlib.sha256(body.password.encode()).digest(),hashlib.sha256(fallback.encode()).digest())
    if not valid:raise HTTPException(400,'Current password is incorrect.')
    return uid


@router.post('/totp/setup')
def setup(body:PasswordProof,request:Request):
    uid=prove(request,body);old=db.one('SELECT enabled FROM account_security WHERE uid=?',(uid,))
    if old and old['enabled']:raise HTTPException(409,'Two-factor authentication is already enabled.')
    secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
    db.execute("INSERT INTO account_security(uid,secret) VALUES(?,?) ON CONFLICT(uid) DO UPDATE SET secret=excluded.secret",(uid,vault.encrypt(secret)))
    label=quote('Agency Office:'+admin.current(request).get('email',uid),safe='')
    return {'secret':secret,'uri':f'otpauth://totp/{label}?secret={secret}&issuer=Agency%20Office','message':'Scan locally in your authenticator, then confirm a code. This setup secret is shown only now.'}


class OTP(BaseModel):
    otp:str=Field(min_length=6,max_length=100)


@router.post('/totp/enable')
def enable(body:OTP,request:Request):
    uid=admin.current(request)['id'];row=db.one('SELECT * FROM account_security WHERE uid=?',(uid,))
    if not row or row['enabled']:raise HTTPException(409,'Begin a new setup first.')
    counter=int(time.time())//30
    if not any(hmac.compare_digest(code(vault.decrypt(row['secret']),c),body.otp) for c in (counter-1,counter,counter+1)):raise HTTPException(400,'Invalid authenticator code.')
    codes=[secrets.token_hex(6) for _ in range(8)]
    db.execute('UPDATE account_security SET enabled=1,backups=?,last_counter=? WHERE uid=?',(json.dumps([hashlib.sha256(c.encode()).hexdigest() for c in codes]),counter,uid))
    db.execute('UPDATE account_sessions SET revoked=1 WHERE uid=? AND id<>?',(uid,session_id(request.cookies.get('ao_session',''))))
    return {'backup_codes':codes,'message':'Save these recovery codes securely. Each can be used once; they will not be shown again.'}


@router.post('/totp/disable')
def disable(body:PasswordProof,request:Request):
    uid=prove(request,body)
    if not verify(uid,body.otp):raise HTTPException(400,'Invalid or already used authenticator/recovery code.')
    db.execute('DELETE FROM account_security WHERE uid=?',(uid,))
    return {'ok':True}


@router.delete('/sessions/{sid}')
def revoke(sid:str,request:Request):
    uid=admin.current(request)['id']
    db.execute('UPDATE account_sessions SET revoked=1 WHERE uid=? AND id=?',(uid,sid))
    return {'ok':True}


@router.post('/sessions/sign-out-others')
def revoke_others(request:Request):
    uid=admin.current(request)['id']
    db.execute('UPDATE account_sessions SET revoked=1 WHERE uid=? AND id<>?',(uid,session_id(request.cookies.get('ao_session',''))))
    return {'ok':True}


class Preferences(BaseModel):
    language:str=Field(default='en',pattern='^(en|fr|ar)$')
    activity_notifications:bool=True
    sound:bool=True
    avatar:str=Field(default='',max_length=200000)


@router.get('/preferences')
def preferences(request:Request):
    uid=admin.current(request)['id']
    return json.loads(db.kv_get('profile_preferences_'+uid,Preferences().model_dump_json()))


@router.put('/preferences')
def save_preferences(body:Preferences,request:Request):
    uid=admin.current(request)['id']
    if body.avatar:
        import re
        if not re.fullmatch(r'data:image/png;base64,[A-Za-z0-9+/=]+',body.avatar):raise HTTPException(422,'Avatar must be a cropped PNG image.')
        try:
            raw=base64.b64decode(body.avatar.split(',')[1],validate=True)
            if len(raw)>150000 or len(raw)<24 or not raw.startswith(b'\x89PNG\r\n\x1a\n') or raw[12:16]!=b'IHDR':raise ValueError()
            width,height=struct.unpack('>II',raw[16:24])
            if not 1<=width<=256 or not 1<=height<=256:raise ValueError()
        except ValueError:raise HTTPException(422,'Invalid or oversized PNG avatar.')
    db.kv_set('profile_preferences_'+uid,body.model_dump_json())
    return body.model_dump()


class SignOutAll(BaseModel):
    confirmation:str


@router.post('/sessions/sign-out-all')
def revoke_all(body:SignOutAll,request:Request):
    if body.confirmation!='SIGN OUT':raise HTTPException(422,'Type SIGN OUT to confirm.')
    uid=admin.current(request)['id'];db.execute('UPDATE account_sessions SET revoked=1 WHERE uid=?',(uid,))
    return {'ok':True}
