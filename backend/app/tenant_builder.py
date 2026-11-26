"""Tenant-scoped adapter for the existing Builder UI, through /api/ai gateway."""
import asyncio
import io
import json
import time
import zipfile
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import Response,StreamingResponse
from pydantic import Field
from . import db,saas,sitebuilder
router=APIRouter(prefix='/api/saas/builder',tags=['Agency Builder'])
SCHEMA='''
CREATE TABLE IF NOT EXISTS saas_sites(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,name TEXT NOT NULL,brief TEXT NOT NULL,files TEXT NOT NULL,messages TEXT NOT NULL DEFAULT '[]',created REAL NOT NULL,updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS saas_site_versions(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,label TEXT NOT NULL,files TEXT NOT NULL,created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS saas_site_versions_tenant ON saas_site_versions(tenant_id,project_id,created);
CREATE INDEX IF NOT EXISTS saas_sites_tenant ON saas_sites(tenant_id);
'''

def check(request,write=False):
    tid=saas.scope(request,write)
    _,_,policy=saas.entitlement(tid)
    if 'builder' not in policy['features']:raise HTTPException(403,'Builder is not included in this plan. Contact the administrator.')
    if write:saas.feature(tid,'builder')
    return tid,policy


def site(pid,tid):
    row=db.one('SELECT * FROM saas_sites WHERE id=? AND tenant_id=?',(pid,tid))
    if not row:raise HTTPException(404,'Website not found.')
    return {**dict(row),'files':json.loads(row['files']),'messages':json.loads(row['messages'])}


def snapshot(pid,tid,files,label,messages=None):
    sitebuilder.validate_files(files)
    with saas.transaction(tid) as c:
        c.execute('UPDATE saas_sites SET files=?,updated=? WHERE id=? AND tenant_id=?',(json.dumps(files),time.time(),pid,tid))
        if messages is not None:c.execute('UPDATE saas_sites SET messages=? WHERE id=? AND tenant_id=?',(json.dumps(messages),pid,tid))
        c.execute('INSERT INTO saas_site_versions(id,tenant_id,project_id,label,files,created) VALUES(?,?,?,?,?,?)',(db.new_id('version'),tid,pid,label[:120],json.dumps(files),time.time()))


@router.get('/projects')
def sites(request:Request):
    tid,_=check(request)
    return [dict(r) for r in db.query('SELECT id,name,brief,created,updated FROM saas_sites WHERE tenant_id=? ORDER BY updated DESC',(tid,))]


class New(saas.Input):
    name:str=Field(min_length=1,max_length=120)
    brief:str=Field(default='',max_length=12000)


@router.post('/projects')
def create(body:New,request:Request):
    tid,p=check(request,True);pid=db.new_id('site');now=time.time()
    files=sitebuilder.render_site({'business':body.name,'headline':'Your next website starts here.','services':[],'faq':[]})
    with saas.transaction(tid) as c:
        n=c.execute('SELECT (SELECT count(*) FROM saas_sites WHERE tenant_id=?)+(SELECT count(*) FROM saas_projects WHERE tenant_id=?) AS n',(tid,tid)).fetchone()['n']
        if n>=p['max_projects']:raise HTTPException(409,'Project limit reached.')
        c.execute('INSERT INTO saas_sites(id,tenant_id,name,brief,files,created,updated) VALUES(?,?,?,?,?,?,?)',(pid,tid,body.name,body.brief,json.dumps(files),now,now))
    snapshot(pid,tid,files,'Initial draft');saas.audit(request,'builder.create',tid,pid)
    return site(pid,tid)


@router.get('/projects/{pid}')
def get(pid:str,request:Request):return site(pid,check(request)[0])


class Rename(saas.Input):name:str=Field(min_length=1,max_length=120)


@router.patch('/projects/{pid}')
def rename(pid:str,body:Rename,request:Request):
    tid,_=check(request,True);site(pid,tid)
    db.execute('UPDATE saas_sites SET name=?,updated=? WHERE id=? AND tenant_id=?',(body.name,time.time(),pid,tid));return {'ok':True}


class Files(saas.Input):
    files:dict[str,str]
    label:str=Field(default='Manual edit',max_length=120)


@router.put('/projects/{pid}/files')
def save(pid:str,body:Files,request:Request):
    tid,_=check(request,True);site(pid,tid)
    try:snapshot(pid,tid,body.files,body.label)
    except ValueError:raise HTTPException(422,'Files failed safety validation.') from None
    saas.audit(request,'builder.save',tid,pid);return {'ok':True}


@router.get('/projects/{pid}/versions')
def versions(pid:str,request:Request):
    tid,_=check(request);site(pid,tid)
    return [dict(r) for r in db.query('SELECT id,label,created FROM saas_site_versions WHERE tenant_id=? AND project_id=? ORDER BY created DESC',(tid,pid))]


@router.get('/projects/{pid}/versions/{vid}')
def version(pid:str,vid:str,request:Request):
    tid,_=check(request);site(pid,tid)
    row=db.one('SELECT * FROM saas_site_versions WHERE id=? AND project_id=? AND tenant_id=?',(vid,pid,tid))
    if not row:raise HTTPException(404,'Version not found.')
    return {**dict(row),'files':json.loads(row['files'])}


@router.post('/projects/{pid}/versions/{vid}/restore')
def restore(pid:str,vid:str,request:Request):
    tid,_=check(request,True);v=version(pid,vid,request);snapshot(pid,tid,v['files'],'Restored: '+v['label']);return site(pid,tid)


@router.get('/projects/{pid}/export')
def export(pid:str,request:Request):
    data=site(pid,check(request)[0]);buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for name,text in data['files'].items():z.writestr(name,text)
    return Response(buffer.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="website.zip"'})


@router.get('/projects/{pid}/qa')
def qa(pid:str,request:Request):return sitebuilder.qa(site(pid,check(request)[0])['files'])


class Generate(saas.Input):
    prompt:str=Field(min_length=1,max_length=12000)
    mode:str=Field(default='build',pattern='^(build|edit|marketing)$')


@router.post('/projects/{pid}/generate')
async def generate(pid:str,body:Generate,request:Request):
    tid,_=check(request,True);p=site(pid,tid)
    async def stream():
        def event(value):return 'data: '+json.dumps(value)+'\n\n'
        yield event({'type':'step','step':'Generating through your agency AI gateway (buffered)'})
        try:
            prompt='Build a complete responsive accessible frontend website using only supplied facts. Return ONLY JSON {"files":{"index.html":"...","styles.css":"...","script.js":"..."}}. Use HTML5 doctype, html/head/body/main, exactly one h1, title, meta description, viewport, image alt, responsive @media, :focus-visible. No external dependencies or network requests except Google Fonts. Real interactive JavaScript, no TODOs.\nRequest: '+body.prompt
            if body.mode!='build':prompt+='\nCurrent files: '+json.dumps(p['files'])
            result=await asyncio.wait_for(saas.gateway(saas.AIRequest(request_id=db.new_id('build'),prompt=prompt[:16000],max_tokens=6000),request),timeout=110)
            parsed=sitebuilder.repair_json(result['content']);files=parsed['files'];sitebuilder.validate_files(files);report=sitebuilder.qa(files)
            failed=[c for c in report['checks'] if not c['passed']]
            if failed:
                yield event({'type':'step','step':'One static validation repair'})
                repair='Repair these static issues: '+json.dumps(failed)+'\nReturn ONLY JSON {"files":{...}} with complete index.html, styles.css and script.js. Current files: '+json.dumps(files)
                result=await asyncio.wait_for(saas.gateway(saas.AIRequest(request_id=db.new_id('repair'),prompt=repair[:16000],max_tokens=6000),request),timeout=100)
                files=sitebuilder.repair_json(result['content'])['files'];sitebuilder.validate_files(files);report=sitebuilder.qa(files)
                if not all(c['passed'] for c in report['checks']):raise ValueError('Static checks failed')
            # Recheck entitlement immediately before committing generated content.
            check(request,True)
            history=(p['messages']+[{'role':'user','content':body.prompt},{'role':'assistant','content':'Website generated via the agency AI gateway.'}])[-100:]
            snapshot(pid,tid,files,'AI generation',history);saas.audit(request,'builder.generate',tid,pid)
            yield event({'type':'token','text':json.dumps({'files':files})})
            yield event({'type':'done','provider':result['provider'],'model':result['model'],'report':report,'fixed_issues':len(failed)})
        except Exception:
            yield event({'type':'error','message':'Generation failed, quota was reached, or files failed safety/static validation. Saved files are preserved. Review License & Usage and contact your administrator.'})
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
