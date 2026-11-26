"""Additive centrally managed SaaS. Legacy tables remain owner-only.
Scope comes from authenticated membership/session, NEVER a body/header tenant ID.
"""
import asyncio
import csv
import hashlib
import io
import json
import os
import secrets
import time
from contextlib import contextmanager
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from . import admin, db

router=APIRouter(prefix='/api/saas',tags=['SaaS'])
ai_router=APIRouter(prefix='/api/ai',tags=['Central AI gateway'])
SCHEMA='''
CREATE TABLE IF NOT EXISTS saas_agencies(tenant_id TEXT PRIMARY KEY,name TEXT NOT NULL,owner_email TEXT NOT NULL,status TEXT NOT NULL,config TEXT NOT NULL DEFAULT '{}',created REAL NOT NULL,deleted_at REAL);
CREATE TABLE IF NOT EXISTS saas_members(uid TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,role TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS saas_members_tenant ON saas_members(tenant_id);
CREATE TABLE IF NOT EXISTS saas_plans(id TEXT PRIMARY KEY,policy TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS saas_licenses(tenant_id TEXT PRIMARY KEY,license_key TEXT NOT NULL,plan TEXT NOT NULL,status TEXT NOT NULL,starts REAL NOT NULL,expires REAL NOT NULL,grace_days INTEGER NOT NULL DEFAULT 0,overrides TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS saas_templates(id TEXT PRIMARY KEY,name TEXT NOT NULL,role TEXT NOT NULL,description TEXT NOT NULL,prompt TEXT NOT NULL,skills TEXT NOT NULL,model TEXT NOT NULL DEFAULT '',plans TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS saas_agents(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,template_id TEXT NOT NULL,name TEXT NOT NULL,instructions TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'idle',removed INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS saas_agents_tenant ON saas_agents(tenant_id);
CREATE TABLE IF NOT EXISTS saas_projects(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,name TEXT NOT NULL,brief TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS saas_tasks(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,parent_id TEXT NOT NULL DEFAULT '',agent_id TEXT NOT NULL DEFAULT '',title TEXT NOT NULL,status TEXT NOT NULL,output TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',lease_until REAL NOT NULL DEFAULT 0,created REAL NOT NULL,updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS saas_messages(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,task_id TEXT NOT NULL,agent_id TEXT NOT NULL,text TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS saas_usage(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,user_id TEXT NOT NULL,agent_id TEXT NOT NULL,provider TEXT NOT NULL DEFAULT '',model TEXT NOT NULL DEFAULT '',input_tokens INTEGER NOT NULL DEFAULT 0,output_tokens INTEGER NOT NULL DEFAULT 0,estimated_cost REAL,status TEXT NOT NULL,reserved_tokens INTEGER NOT NULL,fingerprint TEXT NOT NULL,output TEXT NOT NULL DEFAULT '',created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS saas_usage_tenant_month ON saas_usage(tenant_id,created);
CREATE TABLE IF NOT EXISTS saas_image_outputs(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,data BLOB NOT NULL,content_type TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS saas_ai_attempts(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,request_id TEXT NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,input_tokens INTEGER NOT NULL,output_tokens INTEGER NOT NULL,estimated_cost REAL,status TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS saas_audit(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,user_id TEXT NOT NULL,action TEXT NOT NULL,ip TEXT NOT NULL,detail TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS saas_notifications(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,text TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS saas_tickets(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,subject TEXT NOT NULL,message TEXT NOT NULL,status TEXT NOT NULL,priority TEXT NOT NULL,internal_note TEXT NOT NULL DEFAULT '',created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS saas_projects_tenant ON saas_projects(tenant_id);
CREATE INDEX IF NOT EXISTS saas_tasks_tenant_project ON saas_tasks(tenant_id,project_id,status,created);
CREATE INDEX IF NOT EXISTS saas_messages_tenant_task ON saas_messages(tenant_id,task_id,created);
CREATE INDEX IF NOT EXISTS saas_audit_tenant ON saas_audit(tenant_id,created);
CREATE INDEX IF NOT EXISTS saas_notifications_tenant ON saas_notifications(tenant_id,created);
CREATE INDEX IF NOT EXISTS saas_tickets_tenant ON saas_tickets(tenant_id,created);
CREATE INDEX IF NOT EXISTS saas_attempts_tenant ON saas_ai_attempts(tenant_id,created);
CREATE TABLE IF NOT EXISTS saas_impersonations(session_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,expires REAL NOT NULL);
'''
ROLES={'tenant_owner','tenant_admin','manager','member'}
DEFAULT_POLICY={'max_users':5,'max_agents':5,'max_projects':10,'monthly_requests':1000,'monthly_tokens':1000000,'models':[],'features':['projects','agents','ai','builder'],'premium':False,'support':'standard'}

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Policy(Input):
    max_users:int=Field(default=5,ge=1,le=10000)
    max_agents:int=Field(default=5,ge=1,le=1000)
    max_projects:int=Field(default=10,ge=1,le=100000)
    monthly_requests:int=Field(default=1000,ge=0,le=10000000)
    monthly_tokens:int=Field(default=1000000,ge=0,le=10000000000)
    models:list[str]=Field(default_factory=list,max_length=200)
    features:list[str]=Field(default_factory=lambda:['projects','agents','ai','builder'],max_length=30)
    premium:bool=False
    support:str=Field(default='standard',max_length=60)


def initialize():
    db.executescript(SCHEMA)
    from .tenant_builder import SCHEMA as BUILDER_SCHEMA
    db.executescript(BUILDER_SCHEMA)
    for name,mult in [('Starter',1),('Professional',5),('Enterprise',20),('Custom',1)]:
        policy={**DEFAULT_POLICY,**{k:DEFAULT_POLICY[k]*mult for k in ('max_users','max_agents','max_projects','monthly_requests','monthly_tokens')}}
        db.execute('INSERT INTO saas_plans(id,policy) VALUES(?,?) ON CONFLICT(id) DO NOTHING',(name,db.jdump(policy)))
    names=['Manager / Director','Marketing Strategist','Graphic Designer','Developer','Copywriter','SEO Specialist','Social Media Manager','Facebook Ads Manager','Video Editor','Data Analyst','Content Creator','Brand Designer']
    for i,name in enumerate(names):
        db.execute('INSERT INTO saas_templates(id,name,role,description,prompt,skills,plans) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING',('catalog_'+str(i),name,name,'Reusable '+name.lower()+' specialist.','You are a '+name+'. Use only supplied facts. Clearly label assumptions. Deliver actionable work, not fabricated performance claims.',db.jdump([name]),db.jdump(['Starter','Professional','Enterprise','Custom'])))


@contextmanager
def transaction(tenant=None):
    # PostgreSQL advisory lock serializes quota+resource admission across workers;
    # SQLite BEGIN IMMEDIATE serializes writers across processes. Never hold over AI.
    with db._lock:
        c=db.get_conn()
        if os.getenv('DATABASE_URL'):
            with c.raw.transaction():
                if tenant:c.execute('SELECT pg_advisory_xact_lock(hashtext(?))',('saas:'+tenant,))
                yield c
        else:
            c.execute('BEGIN IMMEDIATE')
            try:yield c;c.commit()
            except BaseException:c.rollback();raise


def platform(identity):return bool(identity and identity.get('id')=='owner' and not identity.get('api_key'))


def mfa_enforced():return os.getenv('VERCEL')=='1' or os.getenv('APP_ENV')=='production' or os.getenv('SAAS_ENFORCE_MFA','true')=='true'


def mfa_ready(uid):
    row=db.one('SELECT enabled FROM account_security WHERE uid=?',(uid,))
    return bool(row and row['enabled'])


def authorize(connection,identity):
    """Return True when SaaS policy handled authorization; legacy otherwise."""
    if os.getenv('SAAS_MODE','true')=='false' and os.getenv('VERCEL')!='1' and os.getenv('APP_ENV')!='production':return False
    path=connection.scope['path'];method=connection.scope.get('method','GET')
    if platform(identity):
        if mfa_enforced() and not mfa_ready('owner') and not (path.startswith('/api/admin/me/') or path in ('/api/admin/me','/api/saas/me','/api/auth/logout')):
            raise HTTPException(428,'Boss Admin must enable two-factor authentication in Account before managing the platform.')
        from .account_security import session_id
        sid=session_id(connection.cookies.get('ao_session',''))
        imp=db.one('SELECT tenant_id FROM saas_impersonations WHERE session_id=? AND expires>?',(sid,time.time()))
        if imp:identity.update(tenant_id=imp['tenant_id'],platform_role='platform_owner',impersonating=True)
        else:identity['platform_role']='platform_owner'
    else:
        member=db.one('SELECT tenant_id,role FROM saas_members WHERE uid=?',(identity['id'],))
        if member:identity.update(tenant_id=member['tenant_id'],platform_role=member['role'])
        else:
            if path=='/api/admin/me' or path.startswith('/api/admin/me/') or path=='/api/auth/logout':return True
            raise HTTPException(403,'This identity has no agency assignment. Ask Boss Admin to assign it before accessing workspace data.')
    if path.startswith('/api/saas/platform/'):
        if not platform(identity) or identity.get('impersonating'):raise HTTPException(403,'Platform owner access required. Exit impersonation first.')
        return True
    if identity.get('tenant_id'):
        safe=(path.startswith('/api/saas/') or path in ('/api/ai','/api/ai/chat','/api/ai/image','/api/auth/logout','/api/admin/me') or path.startswith('/api/admin/me/'))
        if not safe:raise HTTPException(403,'This legacy endpoint is not available to agency workspaces.')
        if path not in ('/api/auth/logout','/api/saas/me','/api/saas/impersonation') and not path.startswith('/api/admin/me'):
            agency,license_,policy=entitlement(identity['tenant_id'])
            if agency['status']!='active':raise HTTPException(403,'Agency access suspended. Contact the platform administrator.')
            if method not in ('GET','HEAD','OPTIONS') and not valid_license(license_):raise HTTPException(402,'License expired or inactive. Workspace is read-only; contact the administrator.')
        return True
    if path.startswith('/api/saas/') or path.startswith('/api/ai'):
        if not platform(identity):raise HTTPException(403,'No agency membership. Contact the platform administrator.')
        return True
    return False


def identity(request):return request.state.identity

def scope(request,manage=False):
    who=identity(request);tid=who.get('tenant_id')
    if not tid:raise HTTPException(409,'Select an agency using audited impersonation to enter its workspace.')
    if manage and who.get('platform_role') not in ('platform_owner','tenant_owner','tenant_admin','manager'):raise HTTPException(403,'Agency administrator or manager permission required.')
    return tid


def entitlement(tid):
    a=db.one('SELECT * FROM saas_agencies WHERE tenant_id=?',(tid,));l=db.one('SELECT * FROM saas_licenses WHERE tenant_id=?',(tid,))
    if not a or not l:raise HTTPException(404,'Agency unavailable.')
    p=db.one('SELECT policy FROM saas_plans WHERE id=?',(l['plan'],))
    if not p:raise HTTPException(409,'Assigned plan unavailable.')
    return dict(a),dict(l),{**db.jload(p['policy']),**db.jload(l['overrides'],{})}


def valid_license(l):return l['status'] in ('active','trial') and l['starts']<=time.time()<l['expires']+l['grace_days']*86400


def audit(request,action,tid='',detail=''):
    ip=request.headers.get('x-vercel-forwarded-for','').split(',')[0].strip() if os.getenv('VERCEL')=='1' else (request.client.host if request.client else '')
    db.execute('INSERT INTO saas_audit(id,tenant_id,user_id,action,ip,detail,created) VALUES(?,?,?,?,?,?,?)',(db.new_id('audit'),tid,identity(request)['id'],action,ip,detail[:1000],time.time()))


def feature(tid,name):
    a,l,p=entitlement(tid)
    if a['status']!='active' or not valid_license(l):raise HTTPException(402,'Agency/license is not active. Contact the administrator.')
    if name not in p['features']:raise HTTPException(403,'Feature not included. Contact the administrator.')
    return p


@router.get('/me')
def me(request:Request):
    who=identity(request);tid=who.get('tenant_id');base={'user':{k:who.get(k) for k in ('id','name','email','platform_role','tenant_id','impersonating')},'mfa_required':platform(who) and mfa_enforced() and not mfa_ready('owner')}
    if tid:
        a,l,p=entitlement(tid);base.update(agency=a,license=l,policy=p,read_only=not valid_license(l),reminder_days=next((n for n in (1,7,14) if 0<(l['expires']-time.time())/86400<=n),None))
    return base


class AgencyCreate(Input):
    name:str=Field(min_length=2,max_length=100)
    owner_name:str=Field(min_length=1,max_length=100)
    email:str=Field(min_length=3,max_length=254)
    plan:str=Field(default='Starter',max_length=40)
    days:int=Field(default=30,ge=1,le=3650)


def invite_user(c,tid,name,email,role):
    admin.email_valid(email)
    if c.execute('SELECT id FROM admin_users WHERE lower(email)=?',(email.lower(),)).fetchone():raise HTTPException(409,'Email already registered or invited.')
    uid=db.new_id('usr');token=secrets.token_urlsafe(32)
    c.execute("INSERT INTO admin_users(id,name,email,role,status,invite_hash,invite_expires,created_at) VALUES(?,?,?,'Viewer','invited',?,?,?)",(uid,name,email.lower(),hashlib.sha256(token.encode()).hexdigest(),time.time()+86400,time.time()))
    c.execute('INSERT INTO saas_members(uid,tenant_id,role) VALUES(?,?,?)',(uid,tid,role))
    return token


@router.get('/platform/agencies')
def agencies():
    return [dict(r) for r in db.query('SELECT a.*,l.plan,l.status AS license_status,l.expires,(SELECT count(*) FROM saas_members m WHERE m.tenant_id=a.tenant_id) AS users,(SELECT count(*) FROM saas_agents x WHERE x.tenant_id=a.tenant_id AND x.removed=0) AS agents FROM saas_agencies a JOIN saas_licenses l ON l.tenant_id=a.tenant_id ORDER BY a.created DESC')]


@router.post('/platform/agencies')
def agency_create(body:AgencyCreate,request:Request):
    if not db.one('SELECT id FROM saas_plans WHERE id=?',(body.plan,)):raise HTTPException(422,'Unknown plan.')
    tid=db.new_id('tenant');now=time.time()
    with transaction(tid) as c:
        c.execute("INSERT INTO saas_agencies(tenant_id,name,owner_email,status,created) VALUES(?,?,?,'active',?)",(tid,body.name,body.email.lower(),now))
        c.execute("INSERT INTO saas_licenses(tenant_id,license_key,plan,status,starts,expires) VALUES(?,?,?,'active',?,?)",(tid,secrets.token_urlsafe(24),body.plan,now,now+body.days*86400))
        token=invite_user(c,tid,body.owner_name,body.email,'tenant_owner')
    audit(request,'agency.create',tid)
    return {'tenant_id':tid,'invite_token':token,'delivery':'Single-use invitation valid 24 hours. Share securely; automatic email delivery is not configured.'}


class AgencyEdit(Input):
    name:str=Field(min_length=2,max_length=100)
    status:str=Field(pattern='^(active|suspended|deleted)$')


@router.patch('/platform/agencies/{tid}')
def agency_edit(tid:str,body:AgencyEdit,request:Request):
    a,_,_=entitlement(tid)
    if a['deleted_at'] and time.time()-a['deleted_at']>30*86400:raise HTTPException(409,'Recovery window elapsed. Retained records require an audited retention process.')
    db.execute('UPDATE saas_agencies SET name=?,status=?,deleted_at=? WHERE tenant_id=?',(body.name,body.status,time.time() if body.status=='deleted' else None,tid));audit(request,'agency.'+body.status,tid)
    return {'ok':True}


@router.get('/platform/plans')
def plans():return [{'id':r['id'],**db.jload(r['policy'])} for r in db.query('SELECT * FROM saas_plans ORDER BY id')]


@router.put('/platform/plans/{name}')
def plan_save(name:str,body:Policy,request:Request):
    if not 1<=len(name)<=40:raise HTTPException(422,'Invalid plan name.')
    db.execute('INSERT INTO saas_plans(id,policy) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET policy=excluded.policy',(name,body.model_dump_json()));audit(request,'plan.save',detail=name)
    return {'ok':True}


class LicenseEdit(Input):
    plan:str=Field(max_length=40)
    status:str=Field(pattern='^(active|trial|suspended|expired)$')
    days:int=Field(ge=0,le=3650)
    grace_days:int=Field(default=0,ge=0,le=30)
    overrides:Policy|None=None


@router.put('/platform/agencies/{tid}/license')
def license_save(tid:str,body:LicenseEdit,request:Request):
    entitlement(tid)
    if not db.one('SELECT id FROM saas_plans WHERE id=?',(body.plan,)):raise HTTPException(422,'Unknown plan.')
    db.execute('UPDATE saas_licenses SET plan=?,status=?,starts=?,expires=?,grace_days=?,overrides=? WHERE tenant_id=?',(body.plan,body.status,time.time(),time.time()+body.days*86400,body.grace_days,body.overrides.model_dump_json() if body.overrides else '{}',tid));audit(request,'license.save',tid)
    return {'ok':True}


class Impersonate(Input):
    reason:str=Field(min_length=8,max_length=500)


@router.post('/platform/agencies/{tid}/impersonate')
def impersonate(tid:str,body:Impersonate,request:Request):
    entitlement(tid)
    from .account_security import session_id
    sid=session_id(request.cookies.get('ao_session',''))
    if not sid:raise HTTPException(403,'Browser session required.')
    db.execute('INSERT INTO saas_impersonations(session_id,tenant_id,expires) VALUES(?,?,?) ON CONFLICT(session_id) DO UPDATE SET tenant_id=excluded.tenant_id,expires=excluded.expires',(sid,tid,time.time()+1800));audit(request,'impersonation.start',tid,body.reason)
    return {'ok':True}


@router.delete('/impersonation')
def stop_impersonation(request:Request):
    if not platform(identity(request)):raise HTTPException(403,'Platform owner required.')
    from .account_security import session_id
    audit(request,'impersonation.stop',identity(request).get('tenant_id',''))
    db.execute('DELETE FROM saas_impersonations WHERE session_id=?',(session_id(request.cookies.get('ao_session','')),))
    return {'ok':True}


@router.get('/platform/agencies/{tid}/export')
def agency_export(tid:str,request:Request):
    a,l,p=entitlement(tid)
    data={'agency':a,'license':l,'policy':p}
    for name in ('agents','projects','tasks','messages','usage','tickets','notifications','audit','sites','site_versions','ai_attempts'):
        data[name]=[dict(r) for r in db.query('SELECT * FROM saas_'+name+' WHERE tenant_id=?',(tid,))]
    data['team']=[dict(r) for r in db.query('SELECT m.uid,m.role,u.name,u.email,u.status FROM saas_members m JOIN admin_users u ON u.id=m.uid WHERE m.tenant_id=?',(tid,))]
    audit(request,'agency.export',tid)
    return data


@router.get('/platform/overview')
def overview():
    now=time.time();month=month_start()
    usage=db.one('SELECT count(*) AS requests,coalesce(sum(input_tokens+output_tokens),0) AS tokens,sum(estimated_cost) AS estimated_cost FROM saas_usage WHERE created>=?',(month,))
    return {'agencies':db.one('SELECT count(*) AS n FROM saas_agencies')['n'],'active':db.one("SELECT count(*) AS n FROM saas_agencies WHERE status='active'")['n'],'suspended':db.one("SELECT count(*) AS n FROM saas_agencies WHERE status='suspended'")['n'],'users':db.one('SELECT count(*) AS n FROM saas_members')['n'],'agents':db.one('SELECT count(*) AS n FROM saas_agents WHERE removed=0')['n'],'active_licenses':db.one("SELECT count(*) AS n FROM saas_licenses WHERE status IN ('active','trial') AND starts<=? AND expires+grace_days*86400>?",(now,now))['n'],'usage':dict(usage),'errors_24h':db.one("SELECT count(*) AS n FROM saas_usage WHERE status='error' AND created>?",(now-86400,))['n'],'expiring':[dict(r) for r in db.query('SELECT a.name,l.expires FROM saas_agencies a JOIN saas_licenses l ON l.tenant_id=a.tenant_id WHERE l.expires BETWEEN ? AND ? ORDER BY l.expires',(now,now+14*86400))],'activity':[dict(r) for r in db.query('SELECT tenant_id,count(*) AS requests,sum(input_tokens+output_tokens) AS tokens FROM saas_usage WHERE created>=? GROUP BY tenant_id ORDER BY requests DESC',(month,))]}


def month_start():
    import datetime
    now=datetime.datetime.now(datetime.timezone.utc)
    return now.replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp()


@router.get('/usage')
def own_usage(request:Request):
    tid=scope(request);_,l,p=entitlement(tid)
    rows=db.query('SELECT id,agent_id,provider,model,input_tokens,output_tokens,status,created FROM saas_usage WHERE tenant_id=? AND created>=? ORDER BY created DESC LIMIT 500',(tid,month_start()))
    totals=db.one('SELECT count(*) AS requests,coalesce(sum(CASE WHEN status=\'pending\' THEN reserved_tokens ELSE input_tokens+output_tokens END),0) AS tokens FROM saas_usage WHERE tenant_id=? AND created>=?',(tid,month_start()))
    return {'rows':[dict(r) for r in rows],'totals':dict(totals),'remaining_requests':max(0,p['monthly_requests']-totals['requests']),'remaining_tokens':max(0,p['monthly_tokens']-totals['tokens']),'license':l,'read_only':not valid_license(l)}


@router.get('/platform/usage')
def platform_usage():return [dict(r) for r in db.query('SELECT tenant_id,agent_id,provider,model,status,count(*) AS requests,sum(input_tokens) AS input_tokens,sum(output_tokens) AS output_tokens,sum(estimated_cost) AS estimated_cost FROM saas_usage WHERE created>=? GROUP BY tenant_id,agent_id,provider,model,status',(month_start(),))]


@router.get('/platform/usage.csv')
def usage_csv():
    rows=platform_usage();out=io.StringIO();cols=['tenant_id','agent_id','provider','model','status','requests','input_tokens','output_tokens','estimated_cost'];writer=csv.DictWriter(out,fieldnames=cols);writer.writeheader()
    for row in rows:writer.writerow({k:('\''+str(v) if str(v).startswith(('=','+','-','@')) else v) for k,v in row.items()})
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="ai-usage.csv"'})


@router.get('/catalog')
def catalog(request:Request):
    tid=scope(request);_,l,p=entitlement(tid)
    return [{k:r[k] for k in ('id','name','role','description','skills','model','version')}|{'locked':l['plan'] not in db.jload(r['plans'])} for r in db.query('SELECT * FROM saas_templates WHERE active=1 ORDER BY name')]


@router.get('/platform/catalog')
def platform_catalog():return [dict(r) for r in db.query('SELECT * FROM saas_templates ORDER BY name')]


class Template(Input):
    name:str=Field(min_length=2,max_length=100)
    role:str=Field(min_length=2,max_length=100)
    description:str=Field(max_length=2000)
    prompt:str=Field(min_length=10,max_length=20000)
    skills:list[str]=Field(default_factory=list,max_length=50)
    model:str=Field(default='',max_length=200)
    plans:list[str]=Field(default_factory=lambda:['Starter','Professional','Enterprise','Custom'],max_length=50)
    active:bool=True


@router.put('/platform/catalog/{template_id}')
def save_template(template_id:str,body:Template,request:Request):
    if not 1<=len(template_id)<=80:raise HTTPException(422,'Invalid ID.')
    db.execute('INSERT INTO saas_templates(id,name,role,description,prompt,skills,model,plans,active) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,role=excluded.role,description=excluded.description,prompt=excluded.prompt,skills=excluded.skills,model=excluded.model,plans=excluded.plans,active=excluded.active,version=saas_templates.version+1',(template_id,body.name,body.role,body.description,body.prompt,db.jdump(body.skills),body.model,db.jdump(body.plans),int(body.active)))
    for row in db.query('SELECT DISTINCT tenant_id FROM saas_agents WHERE template_id=? AND removed=0',(template_id,)):
        db.execute('INSERT INTO saas_notifications(id,tenant_id,text,created) VALUES(?,?,?,?)',(db.new_id('notice'),row['tenant_id'],'Agent template updated: '+body.name,time.time()))
    audit(request,'catalog.save',detail=template_id);return {'ok':True}


class Recruit(Input):
    template_id:str=Field(max_length=80)
    name:str=Field(min_length=1,max_length=100)
    instructions:str=Field(default='',max_length=10000)


@router.get('/agents')
def agents(request:Request):return [dict(r) for r in db.query("SELECT a.*,t.role,t.skills,t.version,(SELECT count(*) FROM saas_tasks x WHERE x.tenant_id=a.tenant_id AND x.agent_id=a.id AND x.status='done') AS completed_tasks,(SELECT coalesce(sum(u.input_tokens+u.output_tokens),0) FROM saas_usage u WHERE u.tenant_id=a.tenant_id AND u.agent_id=a.id) AS tokens,(SELECT max(x.updated) FROM saas_tasks x WHERE x.tenant_id=a.tenant_id AND x.agent_id=a.id) AS last_activity,(SELECT x.title FROM saas_tasks x WHERE x.tenant_id=a.tenant_id AND x.agent_id=a.id AND x.status='running' LIMIT 1) AS current_task FROM saas_agents a JOIN saas_templates t ON t.id=a.template_id WHERE a.tenant_id=? AND a.removed=0 ORDER BY a.created",(scope(request),))]


@router.post('/agents')
def recruit(body:Recruit,request:Request):
    tid=scope(request,True);p=feature(tid,'agents');_,l,_=entitlement(tid)
    template=db.one('SELECT * FROM saas_templates WHERE id=? AND active=1',(body.template_id,))
    if not template or l['plan'] not in db.jload(template['plans']):raise HTTPException(403,'Agent locked for this plan. Contact the administrator.')
    aid=db.new_id('agent')
    with transaction(tid) as c:
        if c.execute('SELECT count(*) AS n FROM saas_agents WHERE tenant_id=? AND removed=0',(tid,)).fetchone()['n']>=p['max_agents']:raise HTTPException(409,'Agent limit reached. Contact the administrator.')
        c.execute('INSERT INTO saas_agents(id,tenant_id,template_id,name,instructions,created) VALUES(?,?,?,?,?,?)',(aid,tid,body.template_id,body.name,body.instructions,time.time()))
    audit(request,'agent.recruit',tid,aid);return {'id':aid}


class AgentEdit(Input):
    name:str=Field(min_length=1,max_length=100)
    instructions:str=Field(default='',max_length=10000)
    status:str=Field(pattern='^(idle|paused)$')


@router.patch('/agents/{aid}')
def edit_agent(aid:str,body:AgentEdit,request:Request):
    tid=scope(request,True)
    if not db.one('SELECT id FROM saas_agents WHERE id=? AND tenant_id=? AND removed=0',(aid,tid)):raise HTTPException(404,'Agent not found.')
    db.execute('UPDATE saas_agents SET name=?,instructions=?,status=? WHERE id=? AND tenant_id=?',(body.name,body.instructions,body.status,aid,tid));audit(request,'agent.configure',tid,aid);return {'ok':True}


@router.delete('/agents/{aid}')
def remove_agent(aid:str,request:Request):
    tid=scope(request,True)
    if not db.one('SELECT id FROM saas_agents WHERE id=? AND tenant_id=?',(aid,tid)):raise HTTPException(404,'Agent not found.')
    if db.one("SELECT id FROM saas_tasks WHERE tenant_id=? AND agent_id=? AND status IN ('running','pending')",(tid,aid)):raise HTTPException(409,'Agent has unfinished work; finish it before removal.')
    db.execute('UPDATE saas_agents SET removed=1,status=\'paused\' WHERE id=? AND tenant_id=?',(aid,tid));audit(request,'agent.remove',tid,aid);return {'ok':True,'history_retained':True}


class Project(Input):
    name:str=Field(min_length=1,max_length=120)
    brief:str=Field(min_length=1,max_length=15000)


@router.get('/projects')
def projects(request:Request):return [dict(r) for r in db.query('SELECT * FROM saas_projects WHERE tenant_id=? ORDER BY created DESC',(scope(request),))]


@router.post('/projects')
def create_project(body:Project,request:Request):
    tid=scope(request,True);p=feature(tid,'projects');pid=db.new_id('project')
    with transaction(tid) as c:
        if c.execute('SELECT (SELECT count(*) FROM saas_projects WHERE tenant_id=?)+(SELECT count(*) FROM saas_sites WHERE tenant_id=?) AS n',(tid,tid)).fetchone()['n']>=p['max_projects']:raise HTTPException(409,'Project limit reached.')
        c.execute('INSERT INTO saas_projects(id,tenant_id,name,brief,created) VALUES(?,?,?,?,?)',(pid,tid,body.name,body.brief,time.time()))
    audit(request,'project.create',tid,pid);return {'id':pid}


@router.get('/projects/{pid}')
def project(pid:str,request:Request):
    tid=scope(request);p=db.one('SELECT * FROM saas_projects WHERE id=? AND tenant_id=?',(pid,tid))
    if not p:raise HTTPException(404,'Project not found.')
    return {**dict(p),'tasks':[dict(r) for r in db.query('SELECT * FROM saas_tasks WHERE project_id=? AND tenant_id=? ORDER BY created',(pid,tid))],'messages':[dict(r) for r in db.query('SELECT m.* FROM saas_messages m JOIN saas_tasks t ON t.id=m.task_id AND t.tenant_id=m.tenant_id WHERE t.project_id=? AND m.tenant_id=? ORDER BY m.created',(pid,tid))]}


class TeamInvite(Input):
    name:str=Field(min_length=1,max_length=100)
    email:str=Field(min_length=3,max_length=254)
    role:str=Field(pattern='^(tenant_admin|manager|member)$')


@router.get('/team')
def team(request:Request):return [dict(r) for r in db.query('SELECT u.id,u.name,u.email,u.status,m.role FROM admin_users u JOIN saas_members m ON m.uid=u.id WHERE m.tenant_id=?',(scope(request),))]


@router.post('/team')
def invite_team(body:TeamInvite,request:Request):
    tid=scope(request);who=identity(request)
    if who['platform_role'] not in ('platform_owner','tenant_owner','tenant_admin'):raise HTTPException(403,'Team administration permission required.')
    if body.role=='tenant_admin' and who['platform_role']=='tenant_admin':raise HTTPException(403,'Only the tenant owner may appoint administrators.')
    _,_,p=entitlement(tid)
    with transaction(tid) as c:
        if c.execute('SELECT count(*) AS n FROM saas_members WHERE tenant_id=?',(tid,)).fetchone()['n']>=p['max_users']:raise HTTPException(409,'Team member limit reached.')
        token=invite_user(c,tid,body.name,body.email,body.role)
    audit(request,'team.invite',tid,body.role);return {'invite_token':token,'delivery':'Share this single-use 24-hour invitation securely. Email not configured.'}


@router.delete('/team/{uid}')
def remove_member(uid:str,request:Request):
    tid=scope(request);who=identity(request)
    if who['platform_role'] not in ('platform_owner','tenant_owner','tenant_admin'):raise HTTPException(403,'Team administrator required.')
    m=db.one('SELECT role FROM saas_members WHERE uid=? AND tenant_id=?',(uid,tid))
    if not m:raise HTTPException(404,'Member not found.')
    if m['role']=='tenant_owner' or uid==who['id'] or (m['role']=='tenant_admin' and who['platform_role']=='tenant_admin'):raise HTTPException(409,'Cannot remove yourself, the owner or a peer administrator.')
    db.execute("UPDATE admin_users SET status='disabled',session_version=session_version+1 WHERE id=?",(uid,));audit(request,'team.remove',tid,uid);return {'ok':True}


class Branding(Input):
    name:str=Field(min_length=2,max_length=100)
    brand_voice:str=Field(default='',max_length=5000)
    accent:str=Field(default='#6366f1',pattern='^#[0-9a-fA-F]{6}$')
    logo:str=Field(default='',max_length=200000)
    onboarding_complete:bool=False


@router.put('/onboarding')
def onboarding(body:Branding,request:Request):
    tid=scope(request,True);_,_,p=entitlement(tid)
    if body.logo:
        # Reuse the strict PNG header/dimension validator without mutating profile.
        import base64,struct
        try:
            if not body.logo.startswith('data:image/png;base64,'):raise ValueError()
            raw=base64.b64decode(body.logo.split(',')[1],validate=True)
            if len(raw)>150000 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR' or raw[12:16]!=b'IHDR' or not all(1<=n<=256 for n in struct.unpack('>II',raw[16:24])):raise ValueError()
        except (ValueError,struct.error):raise HTTPException(422,'Use a PNG logo of at most 256px and 150 KB.')
    config=body.model_dump()
    if 'white_label' not in p['features']:config['accent']='#6366f1'
    db.execute('UPDATE saas_agencies SET name=?,config=? WHERE tenant_id=?',(body.name,db.jdump(config),tid));audit(request,'onboarding.save',tid);return {'ok':True}


@router.get('/notifications')
def notifications(request:Request):return [dict(r) for r in db.query('SELECT * FROM saas_notifications WHERE tenant_id=? ORDER BY created DESC LIMIT 100',(scope(request),))]


class Ticket(Input):
    subject:str=Field(min_length=3,max_length=150)
    message:str=Field(min_length=5,max_length=10000)
    priority:str=Field(default='normal',pattern='^(low|normal|high|urgent)$')


@router.get('/tickets')
def tickets(request:Request):return [dict(r) for r in db.query('SELECT id,tenant_id,subject,message,status,priority,created FROM saas_tickets WHERE tenant_id=? ORDER BY created DESC',(scope(request),))]


@router.post('/tickets')
def create_ticket(body:Ticket,request:Request):
    tid=scope(request);key=db.new_id('ticket');db.execute("INSERT INTO saas_tickets(id,tenant_id,subject,message,status,priority,created) VALUES(?,?,?,?,'open',?,?)",(key,tid,body.subject,body.message,body.priority,time.time()));audit(request,'ticket.create',tid,key);return {'id':key}


@router.get('/platform/tickets')
def platform_tickets():return [dict(r) for r in db.query('SELECT * FROM saas_tickets ORDER BY created DESC LIMIT 500')]


class TicketEdit(Input):
    status:str=Field(pattern='^(open|in_progress|resolved|closed)$')
    internal_note:str=Field(max_length=10000)


@router.patch('/platform/tickets/{ticket_id}')
def update_ticket(ticket_id:str,body:TicketEdit,request:Request):
    row=db.one('SELECT tenant_id FROM saas_tickets WHERE id=?',(ticket_id,))
    if not row:raise HTTPException(404,'Ticket not found.')
    db.execute('UPDATE saas_tickets SET status=?,internal_note=? WHERE id=?',(body.status,body.internal_note,ticket_id));audit(request,'ticket.update',row['tenant_id'],ticket_id);return {'ok':True}


@router.get('/platform/audit')
def audit_list():return [dict(r) for r in db.query('SELECT * FROM saas_audit ORDER BY created DESC LIMIT 500')]


@router.get('/connections')
def tenant_connections(request:Request):
    tid=scope(request);_,_,p=entitlement(tid)
    return {'models':authorized_models(p),'notice':'Providers and credentials are managed centrally. Contact your administrator for model access.'}


def authorized_models(policy):
    from .config import PROVIDER_PRESETS
    result=[]
    for key in PROVIDER_PRESETS:
        if db.kv_get('disconnected_'+key)=='1':continue
        catalog=db.jload(db.kv_get('catalog_'+key,'{}'),{})
        if not catalog.get('valid'):continue
        for m in catalog.get('models',[]):
            identifier=key+'/'+m['id']
            if identifier in policy['models'] and (policy['premium'] or m.get('free')):
                result.append({'id':identifier,'provider':key,'model':m['id'],'free':bool(m.get('free'))})
    return result


class AIRequest(Input):
    request_id:str=Field(min_length=8,max_length=100,pattern='^[A-Za-z0-9_-]+$')
    prompt:str=Field(min_length=1,max_length=16000)
    model:str=Field(default='',max_length=240)
    agent_id:str=Field(default='',max_length=80)
    max_tokens:int=Field(default=2000,ge=32,le=6000)


async def gateway(body,request):
    tid=scope(request);p=feature(tid,'ai');who=identity(request)
    models=authorized_models(p)
    if body.model:models=[m for m in models if m['id']==body.model]+[m for m in models if m['id']!=body.model]
    if body.model and not any(m['id']==body.model for m in models):raise HTTPException(403,'Model is not authorized for this plan.')
    if not models:raise HTTPException(409,'No authorized, verified AI model. Ask the platform administrator to test a provider and assign models to your plan.')
    routing=db.jload(db.kv_get('saas_routing','{}'),{})
    if not body.model and routing.get('strategy','free-first')=='free-first':models.sort(key=lambda m:not m['free'])
    prompt=body.prompt;system='You are a marketing agency assistant. Do not invent facts, results or statistics.'
    if body.agent_id:
        a=db.one('SELECT a.*,t.prompt,t.model FROM saas_agents a JOIN saas_templates t ON t.id=a.template_id WHERE a.id=? AND a.tenant_id=? AND a.removed=0',(body.agent_id,tid))
        if not a:raise HTTPException(404,'Agent not found.')
        if a['status']=='paused':raise HTTPException(409,'Agent is paused.')
        if not body.model and a['model']:models.sort(key=lambda m:m['id']!=a['model'])
        system=a['prompt']+'\nAgency instructions: '+a['instructions']
    agency,_,_=entitlement(tid);system+='\nBrand context: '+agency['config']
    fingerprint=hashlib.sha256(db.jdump({**body.model_dump(),'uid':who['id']}).encode()).hexdigest()
    key=hashlib.sha256((tid+':'+body.request_id).encode()).hexdigest()
    # Byte count conservatively bounds tokenization for supported UTF-8 text;
    # reserve maximum output for EVERY fallback attempt before contacting AI.
    input_bound=len((prompt+system).encode())+128
    reserve=(input_bound+body.max_tokens)*min(len(models),3)
    with transaction(tid) as c:
        previous=c.execute('SELECT * FROM saas_usage WHERE id=? AND tenant_id=?',(key,tid)).fetchone()
        if previous:
            if previous['fingerprint']!=fingerprint:raise HTTPException(409,'Idempotency key already used for different input.')
            if previous['status']=='done':return {'content':previous['output'],'model':previous['model'],'provider':previous['provider'],'cached':True}
            raise HTTPException(409,'Request already admitted. Inspect usage before retrying with a new request ID.')
        used=c.execute("SELECT count(*) AS requests,coalesce(sum(CASE WHEN status='done' THEN input_tokens+output_tokens ELSE reserved_tokens END),0) AS tokens FROM saas_usage WHERE tenant_id=? AND created>=?",(tid,month_start())).fetchone()
        if used['requests']>=p['monthly_requests'] or used['tokens']+reserve>p['monthly_tokens']:raise HTTPException(429,'Agency AI quota reached or insufficient unreserved tokens. Contact the administrator.')
        c.execute("INSERT INTO saas_usage(id,tenant_id,user_id,agent_id,status,reserved_tokens,fingerprint,created) VALUES(?,?,?,?,'pending',?,?,?)",(key,tid,who['id'],body.agent_id,reserve,fingerprint,time.time()))
    from .provider import OpenAIProvider,ProviderConfig
    from .ai_hub import config
    total_in=0;total_out=0;total_cost=0;unpriced=False
    prices=db.jload(db.kv_get('saas_prices','{}'),{})
    def record_attempt(candidate,n,tin,tout,status):
        nonlocal total_cost,unpriced
        price=prices.get(candidate['id'])
        cost=(tin*price['input']+tout*price['output'])/1000000 if price else None
        if cost is None:unpriced=True
        else:total_cost+=cost
        db.execute('INSERT INTO saas_ai_attempts(id,tenant_id,request_id,provider,model,input_tokens,output_tokens,estimated_cost,status,created) VALUES(?,?,?,?,?,?,?,?,?,?)',(key+'_'+str(n),tid,key,candidate['provider'],candidate['model'],tin,tout,cost,status,time.time()))
    for n,candidate in enumerate(models[:3]):
        try:
            base,token,_=config(candidate['provider'])
            if candidate['provider']!='ollama' and not token:raise ValueError('Provider unconfigured')
            if candidate['provider']=='ollama_cloud' and base.rstrip('/').endswith('/api'):base=base.rstrip('/')[:-4]+'/v1'
            if candidate['provider']=='ollama' and not base.rstrip('/').endswith('/v1'):base=base.rstrip('/')+'/v1'
            transport=OpenAIProvider(ProviderConfig(candidate['provider'],candidate['provider'],base,token or 'ollama',candidate['model']))
            transport.max_retries=1
            result=await asyncio.wait_for(transport.chat([{'role':'system','content':system},{'role':'user','content':prompt}],max_tokens=body.max_tokens),timeout=60)
            if not result.text.strip():raise ValueError('Empty response')
        except Exception:
            # Failed/timeout attempts may still be billed by the provider.
            total_in+=input_bound;total_out+=body.max_tokens
            record_attempt(candidate,n,input_bound,body.max_tokens,'error')
            continue
        # Bookkeeping failures must NOT trigger another upstream generation.
        tin=result.usage.tokens_in or input_bound;tout=result.usage.tokens_out or body.max_tokens
        total_in+=tin;total_out+=tout
        record_attempt(candidate,n,tin,tout,'done')
        cost=None if unpriced else total_cost
        db.execute("UPDATE saas_usage SET status='done',provider=?,model=?,input_tokens=?,output_tokens=?,estimated_cost=?,output=? WHERE id=? AND tenant_id=?",(candidate['provider'],candidate['model'],total_in,total_out,cost,result.text,key,tid))
        audit(request,'ai.complete',tid,key)
        return {'content':result.text,'model':candidate['model'],'provider':candidate['provider'],'cached':False}
    db.execute("UPDATE saas_usage SET status='error',input_tokens=?,output_tokens=?,estimated_cost=? WHERE id=? AND tenant_id=?",(total_in,total_out,None if unpriced else total_cost,key,tid));audit(request,'ai.error',tid,key)
    raise HTTPException(502,'All authorized providers failed. The attempt is recorded; uncertain upstream usage remains conservatively reserved.') from None


@ai_router.post('')
@ai_router.post('/chat')
async def ai_chat(body:AIRequest,request:Request):return await gateway(body,request)


@router.post('/projects/{pid}/delegate')
async def delegate(pid:str,body:AIRequest,request:Request):
    tid=scope(request,True);project_data=project(pid,request);feature(tid,'ai')
    manager=db.one("SELECT a.id FROM saas_agents a JOIN saas_templates t ON t.id=a.template_id WHERE a.tenant_id=? AND a.removed=0 AND a.status<>'paused' AND t.id='catalog_0'",(tid,))
    if not manager:raise HTTPException(409,'Recruit an active Manager / Director first.')
    root=db.new_id('task');now=time.time()
    # Parent request key prevents duplicate plan creation on repeat submissions.
    root='task_'+hashlib.sha256((tid+':'+body.request_id).encode()).hexdigest()[:24]
    with transaction(tid) as c:
        if c.execute('SELECT id FROM saas_tasks WHERE id=? AND tenant_id=?',(root,tid)).fetchone():raise HTTPException(409,'Delegation already exists. Open the project timeline.')
        c.execute("INSERT INTO saas_tasks(id,tenant_id,project_id,agent_id,title,status,created,updated) VALUES(?,?,?,?,?,'running',?,?)",(root,tid,pid,manager['id'],body.prompt[:150],now,now))
    db.execute('INSERT INTO saas_messages(id,tenant_id,task_id,agent_id,text,created) VALUES(?,?,?,?,?,?)',(db.new_id('msg'),tid,root,'',body.prompt,time.time()))
    db.execute("UPDATE saas_agents SET status='working' WHERE id=? AND tenant_id=?",(manager['id'],tid))
    try:
        roster=agents(request)
        prompt='Create an execution plan for: '+body.prompt+'\nProject brief: '+project_data['brief']+'\nAvailable specialists: '+db.jdump([{'id':a['id'],'role':a['role']} for a in roster])+'\nReturn ONLY JSON: {"tasks":[{"agent_id":"exact specialist id","title":"specific actionable task"}]}. At most 6 tasks. Do not assign the Manager.'
        response=await gateway(AIRequest(request_id=body.request_id+'_plan',prompt=prompt[:16000],agent_id=manager['id']),request)
        from .sitebuilder import repair_json
        plan=repair_json(response['content']);items=plan.get('tasks',[])
        if not isinstance(items,list) or not 1<=len(items)<=6:raise ValueError()
        allowed={a['id'] for a in roster if a['id']!=manager['id'] and a['status']!='paused'}
        validated=[]
        for item in items:
            if not isinstance(item,dict) or item.get('agent_id') not in allowed or not isinstance(item.get('title'),str) or not 1<=len(item['title'])<=1000:raise ValueError()
            validated.append(item)
        with transaction(tid) as c:
            for i,item in enumerate(validated):
                c.execute("INSERT INTO saas_tasks(id,tenant_id,project_id,parent_id,agent_id,title,status,created,updated) VALUES(?,?,?,?,?,?,'pending',?,?)",(root+'_'+str(i),tid,pid,root,item['agent_id'],item['title'],now,now))
            c.execute("UPDATE saas_tasks SET status='delegated',output=?,updated=? WHERE id=? AND tenant_id=?",(response['content'],time.time(),root,tid))
        db.execute("UPDATE saas_agents SET status='idle' WHERE id=? AND tenant_id=? AND status='working'",(manager['id'],tid))
        audit(request,'manager.delegate',tid,root);return project(pid,request)
    except Exception:
        db.execute("UPDATE saas_agents SET status='error' WHERE id=? AND tenant_id=? AND status='working'",(manager['id'],tid))
        db.execute("UPDATE saas_tasks SET status='error',error='Manager planning failed or returned invalid assignments',updated=? WHERE id=? AND tenant_id=?",(time.time(),root,tid))
        raise HTTPException(502,'Manager could not produce a valid delegation plan. Check the task timeline and provider configuration.') from None


@router.post('/projects/{pid}/advance')
async def advance(pid:str,request:Request):
    tid=scope(request,True);project_data=project(pid,request);feature(tid,'ai');now=time.time()
    with transaction(tid) as c:
        task=c.execute("SELECT * FROM saas_tasks WHERE tenant_id=? AND project_id=? AND status='pending' ORDER BY created,id LIMIT 1",(tid,pid)).fetchone()
        if not task:
            if c.execute("SELECT id FROM saas_tasks WHERE tenant_id=? AND project_id=? AND status='running'",(tid,pid)).fetchone():raise HTTPException(409,'A task is already executing. Do not duplicate an uncertain provider request.')
            parent=c.execute("SELECT * FROM saas_tasks WHERE tenant_id=? AND project_id=? AND status='delegated' ORDER BY created LIMIT 1",(tid,pid)).fetchone()
            if not parent:return {'complete':True}
            if c.execute("SELECT id FROM saas_tasks WHERE tenant_id=? AND parent_id=? AND status<>'done'",(tid,parent['id'])).fetchone():raise HTTPException(409,'Resolve failed subtasks before manager review.')
            task=parent
        c.execute("UPDATE saas_tasks SET status='running',lease_until=?,updated=? WHERE id=? AND tenant_id=?",(now+240,now,task['id'],tid))
    db.execute("UPDATE saas_agents SET status='working' WHERE id=? AND tenant_id=?",(task['agent_id'],tid))
    try:
        context=[dict(r) for r in db.query("SELECT title,output FROM saas_tasks WHERE tenant_id=? AND project_id=? AND parent_id=? AND status='done' ORDER BY created",(tid,pid,task['parent_id'] or task['id']))]
        original=db.one("SELECT text FROM saas_messages WHERE tenant_id=? AND task_id=? AND agent_id='' ORDER BY created LIMIT 1",(tid,task['parent_id'] or task['id']))
        prompt=task['title']+'\nProject brief: '+project_data['brief']+'\nOriginal request: '+(original['text'] if original else '')+'\nCollaborator outputs: '+db.jdump(context)
        if not task['parent_id']:prompt='As Manager, review quality and consistency, identify limitations, and deliver the combined final result.\n'+prompt
        result=await gateway(AIRequest(request_id=task['id']+'_execute_'+str(int(task['updated']*1000)),prompt=prompt[:16000],agent_id=task['agent_id']),request)
        with transaction(tid) as c:
            c.execute("UPDATE saas_tasks SET status='done',output=?,updated=? WHERE id=? AND tenant_id=?",(result['content'],time.time(),task['id'],tid))
            c.execute('INSERT INTO saas_messages(id,tenant_id,task_id,agent_id,text,created) VALUES(?,?,?,?,?,?)',(db.new_id('msg'),tid,task['id'],task['agent_id'],result['content'],time.time()))
        db.execute("UPDATE saas_agents SET status='idle' WHERE id=? AND tenant_id=? AND status='working'",(task['agent_id'],tid))
        audit(request,'task.complete',tid,task['id']);return project(pid,request)
    except Exception:
        db.execute("UPDATE saas_agents SET status='error' WHERE id=? AND tenant_id=? AND status='working'",(task['agent_id'],tid))
        db.execute("UPDATE saas_tasks SET status='error',error='Execution failed; check usage before retrying',updated=? WHERE id=? AND tenant_id=?",(time.time(),task['id'],tid))
        raise HTTPException(502,'Task execution failed. Its history and usage are retained.') from None


@router.post('/platform/demo-agencies')
def seed_demos(request:Request):
    created=[]
    for plan in ('Starter','Professional','Enterprise'):
        email=plan.lower()+'-demo@example.invalid'
        if db.one('SELECT tenant_id FROM saas_agencies WHERE owner_email=?',(email,)):continue
        result=agency_create(AgencyCreate(name=plan+' Demo',owner_name=plan+' Demo Owner',email=email,plan=plan),request)
        created.append(result['tenant_id'])
    audit(request,'demo.seed',detail='Empty demo workspaces only; no usage or AI work fabricated.')
    return {'created':created,'note':'Empty demonstration agencies. example.invalid addresses do not receive email; configure a real owner before use.'}


@router.post('/platform/agencies/{tid}/reset-owner')
def reset_owner(tid:str,request:Request):
    entitlement(tid)
    row=db.one("SELECT uid FROM saas_members WHERE tenant_id=? AND role='tenant_owner'",(tid,))
    if not row:raise HTTPException(404,'Owner not found.')
    token=secrets.token_urlsafe(32)
    db.execute("UPDATE admin_users SET status='invited',invite_hash=?,invite_expires=?,session_version=session_version+1 WHERE id=?",(hashlib.sha256(token.encode()).hexdigest(),time.time()+86400,row['uid']))
    audit(request,'agency.reset_owner',tid)
    return {'invite_token':token,'delivery':'Owner sessions revoked. Share this single-use password-reset invitation securely. Existing 2FA remains enabled.'}


class PlatformSettings(Input):
    name:str=Field(default='Agency Office',min_length=2,max_length=100)
    domain:str=Field(default='',max_length=200)
    legal_text:str=Field(default='',max_length=20000)
    default_plan:str=Field(default='Starter',max_length=40)
    registration_mode:str=Field(default='invite-only',pattern='^invite-only$')


@router.get('/platform/settings')
def platform_settings():return db.jload(db.kv_get('saas_platform_settings',PlatformSettings().model_dump_json()))


@router.put('/platform/settings')
def platform_settings_save(body:PlatformSettings,request:Request):
    if not db.one('SELECT id FROM saas_plans WHERE id=?',(body.default_plan,)):raise HTTPException(422,'Unknown default plan.')
    db.kv_set('saas_platform_settings',body.model_dump_json());audit(request,'platform.settings');return {'ok':True}


class Announcement(Input):
    text:str=Field(min_length=3,max_length=5000)


@router.post('/platform/announcements')
def announce(body:Announcement,request:Request):
    for a in db.query("SELECT tenant_id FROM saas_agencies WHERE status='active'"):
        db.execute('INSERT INTO saas_notifications(id,tenant_id,text,created) VALUES(?,?,?,?)',(db.new_id('notice'),a['tenant_id'],body.text,time.time()))
    audit(request,'announcement.publish');return {'ok':True}


class Price(Input):
    input:float=Field(ge=0,le=10000,allow_inf_nan=False)
    output:float=Field(ge=0,le=10000,allow_inf_nan=False)


class Routing(Input):
    strategy:str=Field(default='free-first',pattern='^(free-first|quality-first)$')
    prices:dict[str,Price]=Field(default_factory=dict,max_length=200)


@router.get('/platform/routing')
def routing_get():return {'strategy':db.jload(db.kv_get('saas_routing','{}'),{}).get('strategy','free-first'),'prices':db.jload(db.kv_get('saas_prices','{}'),{})}


@router.put('/platform/routing')
def routing_save(body:Routing,request:Request):
    if any(len(k)>240 or '/' not in k for k in body.prices):raise HTTPException(422,'Use provider/model IDs for price metadata.')
    db.kv_set('saas_routing',json.dumps({'strategy':body.strategy}));db.kv_set('saas_prices',json.dumps({k:v.model_dump() for k,v in body.prices.items()}));audit(request,'routing.save');return {'ok':True}


class ImageInput(Input):
    request_id:str=Field(min_length=8,max_length=100,pattern='^[A-Za-z0-9_-]+$')
    prompt:str=Field(min_length=1,max_length=2000)


@ai_router.post('/image')
async def agency_image(body:ImageInput,request:Request):
    tid=scope(request);policy=feature(tid,'image');who=identity(request)
    from . import ai_hub
    model=ai_hub.selected()['image_model']
    if model=='none':raise HTTPException(409,'Platform image generation is disabled.')
    fingerprint=hashlib.sha256(('image:'+body.prompt+who['id']).encode()).hexdigest()
    key=hashlib.sha256((tid+':'+body.request_id).encode()).hexdigest()
    with transaction(tid) as c:
        old=c.execute('SELECT * FROM saas_usage WHERE id=? AND tenant_id=?',(key,tid)).fetchone()
        if old:
            if old['fingerprint']!=fingerprint:raise HTTPException(409,'Idempotency key already used for different input.')
            image=c.execute('SELECT * FROM saas_image_outputs WHERE id=? AND tenant_id=?',(key,tid)).fetchone()
            if image:return Response(bytes(image['data']),media_type=image['content_type'],headers={'Cache-Control':'no-store'})
            raise HTTPException(409,'Image request already admitted; inspect usage before retrying.')
        used=c.execute('SELECT count(*) AS n FROM saas_usage WHERE tenant_id=? AND created>=?',(tid,month_start())).fetchone()['n']
        if used>=policy['monthly_requests']:raise HTTPException(429,'Monthly AI request quota reached.')
        c.execute("INSERT INTO saas_usage(id,tenant_id,user_id,agent_id,provider,model,status,reserved_tokens,fingerprint,created) VALUES(?,?,?,'','image',?,'pending',0,?,?)",(key,tid,who['id'],model,fingerprint,time.time()))
    try:
        result=await ai_hub.image(ai_hub.ImageRequest(prompt=body.prompt))
        if not result.media_type.startswith('image/') or len(result.body)>10_000_000:raise ValueError()
    except Exception:
        db.execute("UPDATE saas_usage SET status='error' WHERE id=? AND tenant_id=?",(key,tid));audit(request,'ai.image.error',tid,key)
        raise HTTPException(502,'Image provider failed. Usage recorded; no placeholder substituted.') from None
    with transaction(tid) as c:
        c.execute('INSERT INTO saas_image_outputs(id,tenant_id,data,content_type) VALUES(?,?,?,?)',(key,tid,result.body,result.media_type))
        c.execute("UPDATE saas_usage SET status='done' WHERE id=? AND tenant_id=?",(key,tid))
    audit(request,'ai.image.complete',tid,key)
    return Response(result.body,media_type=result.media_type,headers={'Cache-Control':'no-store'})


@router.post('/projects/{pid}/tasks/{task_id}/retry')
def retry_task(pid:str,task_id:str,body:Impersonate,request:Request):
    tid=scope(request,True);feature(tid,'ai');project(pid,request)
    with transaction(tid) as c:
        task=c.execute('SELECT * FROM saas_tasks WHERE id=? AND project_id=? AND tenant_id=?',(task_id,pid,tid)).fetchone()
        if not task:raise HTTPException(404,'Task not found.')
        if task['status']!='error' and not (task['status']=='running' and task['lease_until']<time.time()):raise HTTPException(409,'Only failed or expired in-flight work can be manually retried.')
        if not task['parent_id']:raise HTTPException(409,'Start a new Manager request after a failed plan/review; existing history remains available.')
        c.execute("UPDATE saas_tasks SET status='pending',error='',updated=? WHERE id=? AND tenant_id=?",(max(time.time(),task['updated']+.001),task_id,tid))
    audit(request,'task.retry.authorize',tid,task_id+' '+body.reason)
    return {'ok':True,'notice':'Previous reservations remain. The next execution is a new, quota-checked provider request.'}


@router.get('/platform/unassigned-users')
def unassigned_users():return [dict(r) for r in db.query("SELECT id,name,email,status FROM admin_users WHERE id<>'owner' AND id NOT IN (SELECT uid FROM saas_members)")]


class AssignUser(Input):
    role:str=Field(pattern='^(tenant_admin|manager|member)$')


@router.post('/platform/agencies/{tid}/assign/{uid}')
def assign_legacy_user(tid:str,uid:str,body:AssignUser,request:Request):
    _,_,policy=entitlement(tid)
    if uid=='owner' or not admin.user(uid):raise HTTPException(409,'Cannot assign the platform owner or an unknown user.')
    with transaction(tid) as c:
        if c.execute('SELECT uid FROM saas_members WHERE uid=?',(uid,)).fetchone():raise HTTPException(409,'User is already assigned. Cross-agency reassignment is not permitted.')
        if c.execute('SELECT count(*) AS n FROM saas_members WHERE tenant_id=?',(tid,)).fetchone()['n']>=policy['max_users']:raise HTTPException(409,'Agency user limit reached.')
        c.execute('INSERT INTO saas_members(uid,tenant_id,role) VALUES(?,?,?)',(uid,tid,body.role))
        c.execute('UPDATE admin_users SET session_version=session_version+1 WHERE id=?',(uid,))
    audit(request,'legacy_user.assign',tid,uid);return {'ok':True}
