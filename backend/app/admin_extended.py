"""Persistent administration extensions. No mocked billing/restart/storage metrics."""
import ipaddress
import json
import secrets
import time
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from . import admin, db
router=APIRouter(prefix='/api/admin',tags=['administration'])


class SecurityPolicy(BaseModel):
    session_minutes:int=Field(default=720,ge=5,le=10080)
    allowed_ips:list[str]=Field(default_factory=list,max_length=50)


@router.get('/policy')
def policy():return json.loads(db.kv_get('security_policy','{"session_minutes":720,"allowed_ips":[]}'))


@router.put('/policy')
def policy_save(body:SecurityPolicy,request:Request):
    networks=[]
    for value in body.allowed_ips:
        try:networks.append(ipaddress.ip_network(value,strict=False))
        except ValueError:raise HTTPException(422,'Use valid IPv4/IPv6 addresses or CIDR ranges.')
    ip=request.headers.get('x-vercel-forwarded-for','').split(',')[0].strip() if __import__('os').getenv('VERCEL')=='1' else request.client.host
    if networks:
        try:allowed=any(ipaddress.ip_address(ip) in network for network in networks)
        except ValueError:allowed=False
        if not allowed:raise HTTPException(409,'The allowlist must include your current connection to avoid locking you out.')
    db.kv_set('security_policy',body.model_dump_json())
    return body.model_dump()


@router.get('/audit')
def audit(limit:int=100,offset:int=0):
    if not 1<=limit<=200 or not 0<=offset<=100000:raise HTTPException(422,'Invalid pagination.')
    return {'rows':[dict(r) for r in db.query('SELECT * FROM audit_events ORDER BY created DESC LIMIT ? OFFSET ?',(limit,offset))],'total':db.one('SELECT count(*) AS n FROM audit_events')['n']}


class RoleCreate(BaseModel):
    name:str=Field(min_length=2,max_length=40,pattern=r'^[A-Za-z][A-Za-z0-9 _-]+$')
    copy_from:str=Field(default='Viewer',max_length=40)


@router.post('/roles')
def create_role(body:RoleCreate,request:Request=None):
    admin.check_grant(request,body.copy_from)
    if body.name in ('Owner','Admin','Manager','Editor','Viewer'):raise HTTPException(409,'This is a protected system role name.')
    row=db.one('SELECT permissions FROM admin_roles WHERE id=?',(body.copy_from,))
    if not row:raise HTTPException(422,'Select a source role.')
    if db.one('SELECT id FROM admin_roles WHERE lower(id)=?',(body.name.lower(),)):raise HTTPException(409,'Role already exists.')
    db.execute('INSERT INTO admin_roles(id,permissions) VALUES(?,?)',(body.name,row['permissions']))
    return {'ok':True}


@router.delete('/roles/{rid}')
def delete_role(rid:str):
    if rid in ('Owner','Admin','Manager','Editor','Viewer'):raise HTTPException(409,'System roles cannot be deleted.')
    users=db.one('SELECT count(*) AS n FROM admin_users WHERE role=?',(rid,))['n']
    keys=db.one('SELECT count(*) AS n FROM admin_keys WHERE role=? AND revoked=0',(rid,))['n']
    if users or keys:raise HTTPException(409,'Reassign members and revoke/reassign API keys before deleting this role.')
    db.execute('DELETE FROM admin_roles WHERE id=?',(rid,));return {'ok':True}


@router.post('/users/{uid}/resend')
def resend(uid:str):
    row=admin.user(uid)
    if not row or row['status']!='invited':raise HTTPException(409,'Only pending invitations can be regenerated.')
    token=secrets.token_urlsafe(32)
    import hashlib
    db.execute('UPDATE admin_users SET invite_hash=?,invite_expires=? WHERE id=?',(hashlib.sha256(token.encode()).hexdigest(),time.time()+86400,uid))
    return {'invite_token':token,'delivery':'The previous invitation is invalid. Copy and securely share this new 24-hour single-use link. Email is not sent.'}


class InstanceConfig(BaseModel):
    name:str=Field(default='Agency Office',min_length=1,max_length=100)
    timezone:str=Field(default='UTC',max_length=100)
    language:str=Field(default='en',pattern='^(en|fr|ar)$')
    retention_days:int=Field(default=30,ge=1,le=365)


@router.get('/configuration')
def configuration():return json.loads(db.kv_get('instance_configuration',InstanceConfig().model_dump_json()))


@router.put('/configuration')
def save_configuration(body:InstanceConfig):
    from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
    try:ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError:raise HTTPException(422,'Use a valid IANA timezone, for example Africa/Tunis.')
    db.kv_set('instance_configuration',body.model_dump_json());db.kv_set('language',body.language)
    return body.model_dump()


@router.get('/storage')
def storage():
    media=db.one('SELECT count(*) AS n,coalesce(sum(length(data)),0) AS bytes FROM media_files')
    return {'media_files':media['n'],'media_bytes':media['bytes'],'audit_events':db.one('SELECT count(*) AS n FROM audit_events')['n'],'database_total_bytes':None,'note':'Counts cover this app schema only; Supabase total quota and billing are managed externally.'}


class Purge(BaseModel):
    confirmation:str


@router.post('/storage/purge-logs')
def purge(body:Purge):
    if body.confirmation!='PURGE LOGS':raise HTTPException(422,'Type PURGE LOGS to confirm.')
    days=configuration()['retention_days']
    db.execute('DELETE FROM audit_events WHERE created<?',(time.time()-days*86400,))
    return {'ok':True,'retention_days':days}


@router.get('/agent-detail/{aid}')
def agent_detail(aid:str):
    if not db.one('SELECT id FROM agents WHERE id=?',(aid,)):raise HTTPException(404,'Agent not found.')
    return {'tasks':[dict(r) for r in db.query('SELECT id,title,status,updated_at FROM tasks WHERE assignee=? ORDER BY updated_at DESC LIMIT 30',(aid,))], 'messages':[dict(r) for r in db.query('SELECT text,created_at FROM messages WHERE agent_id=? ORDER BY created_at DESC LIMIT 30',(aid,))]}


@router.get('/health-checks')
async def health_checks():
    from .ai_hub import models
    begin=time.perf_counter();db.one('SELECT 1');database_ms=round((time.perf_counter()-begin)*1000)
    now=time.time();catalog=await models()
    return {'checks':[{'name':'Database / storage','status':'healthy','latency_ms':database_ms,'checked_at':now,'kind':'database'}, {'name':'Protected administration API','status':'healthy','latency_ms':None,'checked_at':now,'kind':'api'}, {'name':'Scheduler','status':'unavailable' if __import__('os').getenv('VERCEL')=='1' else 'request-driven','latency_ms':None,'checked_at':now,'kind':'scheduler'}]+[{'name':p['label'],'provider':p['provider'],'status':'healthy' if p.get('valid') else 'unavailable','latency_ms':p.get('latency_ms'),'checked_at':p.get('checked_at'),'kind':'provider','error':p.get('error')} for p in catalog['providers']], 'failed_tasks_24h':db.one("SELECT count(*) AS n FROM tasks WHERE status IN ('failed','blocked') AND updated_at>?",( __import__('datetime').datetime.fromtimestamp(now-86400,__import__('datetime').timezone.utc).isoformat(),))['n']}
