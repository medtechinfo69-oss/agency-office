from __future__ import annotations
import asyncio, json, os, re, sqlite3, time, uuid, zipfile, io, html
from pathlib import Path
from urllib.parse import quote
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parents[2]
load_dotenv(ROOT/'.env')
DATA=ROOT/'backend'/'data'; DATA.mkdir(exist_ok=True)
DB=DATA/'siteforge.db'
PROMPTS=ROOT/'prompts'/'sitebuilder'
router=APIRouter()
from . import db as agency_db
# Intended for local use. Vite proxies all browser requests.
queue=asyncio.Lock()
OLLAMA=os.getenv('OLLAMA_BASE_URL','http://localhost:11434').rstrip('/')
DEFAULT=os.getenv('DEFAULT_MODEL','qwen2.5-coder:3b')
PROVIDERS={'ollama':('Ollama',None),'openrouter':('OpenRouter','OPENROUTER_API_KEY'),'groq':('Groq','GROQ_API_KEY'),'gemini':('Gemini','GEMINI_API_KEY')}
DEFAULT_CLOUD={'openrouter':'openai/gpt-oss-20b:free','groq':'llama-3.3-70b-versatile','gemini':'gemini-2.5-flash'}
ALLOWED={'index.html','styles.css','script.js'}

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try: return super().__exit__(exc_type, exc, tb)
        finally: self.close()

def db():
    c=sqlite3.connect(DB,timeout=20,factory=ClosingConnection); c.row_factory=sqlite3.Row; return c

def init():
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,brief TEXT NOT NULL,files TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL); CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created REAL NOT NULL); CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,label TEXT NOT NULL,files TEXT NOT NULL,created REAL NOT NULL); CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
        if not c.execute('SELECT 1 FROM projects LIMIT 1').fetchone():
            plan={'business':'Northstar Insurance','headline':'Confidence for the road ahead.','subheadline':'Insurance guidance built around you, your family, and the things that matter most.','cta':'Explore coverage','primary_color':'#386e60','about':'Clear answers. Thoughtful guidance. A more confident way forward.','seo_description':'Explore insurance guidance with Northstar Insurance.','services':[{'title':'Personal coverage','description':'Explore options for the people and belongings that matter to you.'},{'title':'Business coverage','description':'Find coverage options that fit the way you work.'},{'title':'Helpful guidance','description':'Start a conversation about your individual needs.'}],'faq':[{'question':'How do I get started?','answer':'Send us a message to discuss your coverage needs.'},{'question':'Which coverage is right for me?','answer':'Your needs are unique. Contact us to explore your options.'}],'contact_heading':'Let’s find your way forward.'}
            files=render_site(plan); now=time.time(); c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',('demo','Northstar Insurance','A refined insurance agency website. Demo content; replace before publishing.',json.dumps(files),now,now)); c.execute('INSERT INTO versions(project_id,label,files,created) VALUES(?,?,?,?)',('demo','Initial demo',json.dumps(files),now)); c.execute('INSERT INTO messages(project_id,role,content,created) VALUES(?,?,?,?)',('demo','assistant','Welcome to your studio. This is a sample insurance site. Tell Nora what you’d like to change.',now))

def get_setting(key,default=''):
    with db() as c:
        r=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone(); return r[0] if r else default

def set_setting(key,value):
    with db() as c: c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))

def project(pid):
    with db() as c: r=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
    if not r: raise HTTPException(404,'Project not found')
    d=dict(r); d['files']=json.loads(d['files']); return d

def messages(pid):
    with db() as c: return [dict(r) for r in c.execute('SELECT role,content,created FROM messages WHERE project_id=? ORDER BY id',(pid,))]

def save_message(pid,role,text):
    with db() as c: c.execute('INSERT INTO messages(project_id,role,content,created) VALUES(?,?,?,?)',(pid,role,text,time.time()))

def validate_files(files):
    if not isinstance(files,dict) or not files or len(files)>3: raise ValueError('Expected up to three supported files')
    for path,content in files.items():
        if path not in ALLOWED or not isinstance(content,str) or len(content.encode())>250_000: raise ValueError('Invalid path or oversized file')
        if re.search(r'(?i)<script\b[^>]*\bsrc\s*=\s*[\"\']?https?://|\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts)\s*\(|\bimport\s*\(|<iframe\b|<object\b|<embed\b|<form\b[^>]*\baction\s*=\s*["\']?https?://',content): raise ValueError('External executable scripts, embedded frames and network calls are not permitted')
    return files

def snapshot(pid, files, label):
    validate_files(files); now=time.time()
    with db() as c:
        c.execute('UPDATE projects SET files=?,updated=? WHERE id=?',(json.dumps(files),now,pid)); c.execute('INSERT INTO versions(project_id,label,files,created) VALUES(?,?,?,?)',(pid,label[:120],json.dumps(files),now))

def repair_json(text):
    text=re.sub(r'^\s*```(?:json)?\s*|\s*```\s*$', '', text.strip(), flags=re.I)
    first=text.find('{'); last=text.rfind('}')
    if first>=0 and last>=first: text=text[first:last+1]
    text=re.sub(r',\s*([}\]])',r'\1',text)
    return json.loads(text)

def H(v): return html.escape(str(v or ''),quote=True)

def render_site(p):
    color=p.get('primary_color','#386e60'); color=color if re.fullmatch(r'#[0-9a-fA-F]{6}',str(color)) else '#386e60'
    services=p.get('services',[]); services=services if isinstance(services,list) else []
    faq=p.get('faq',[]); faq=faq if isinstance(faq,list) else []
    def cards(items):
        return ''.join('<article class="service"><span class="service-icon">✳</span><h3>'+H(x.get('title'))+'</h3><p>'+H(x.get('description'))+'</p><a href="#contact">Learn more <span>↗</span></a></article>' for x in items[:6] if isinstance(x,dict))
    questions=''.join('<details><summary>'+H(x.get('question'))+'</summary><p>'+H(x.get('answer'))+'</p></details>' for x in faq[:6] if isinstance(x,dict))
    lang=p.get('language','en'); lang=lang if lang in ('en','fr','ar') else 'en'; direction='rtl' if lang=='ar' else 'ltr'
    index='''<!doctype html><html lang="'''+lang+'''" dir="'''+direction+'''"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'''+H(p.get('business','Your business'))+'''</title><meta name="description" content="'''+H(p.get('seo_description','Get in touch to learn more.'))+'''"><meta property="og:title" content="'''+H(p.get('business'))+'''"><meta property="og:description" content="'''+H(p.get('seo_description'))+'''"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E✳%3C/text%3E%3C/svg%3E"><link rel="stylesheet" href="styles.css"><script src="script.js" defer></script></head><body><header class="header"><a class="brand" href="#home"><span class="brand-mark">✳</span> '''+H(p.get('business'))+'''</a><button class="menu-toggle" aria-label="Toggle menu" aria-expanded="false">☰</button><nav id="nav"><a href="#services">Services</a><a href="#about">About</a><a href="#faq">FAQ</a><a class="nav-cta" href="#contact">Get in touch ↗</a></nav></header><main id="home"><section class="hero"><div class="hero-content"><span class="eyebrow"><span>✳</span> HERE FOR WHAT MATTERS</span><h1>'''+H(p.get('headline'))+'''</h1><p>'''+H(p.get('subheadline'))+'''</p><div class="hero-actions"><a class="button" href="#services">'''+H(p.get('cta','Explore services'))+''' <span>↗</span></a><a class="text-link" href="#about">Get to know us <span>→</span></a></div><div class="hero-note"><span class="note-icon">✳</span> Thoughtful guidance, tailored to you.</div></div><div class="hero-visual" role="img" aria-label="Abstract landscape illustration"><div class="sun"></div><div class="hill hill-one"></div><div class="hill hill-two"></div><div class="visual-label"><span>✳</span><div><b>A little more peace of mind.</b><small>Made for real life.</small></div></div></div></section><section class="section services" id="services"><div class="section-head"><div><span class="eyebrow">WHAT WE DO</span><h2>Support for every<br>chapter of life.</h2></div><p>Explore the ways we can help you move forward with clarity and confidence.</p></div><div class="service-grid">'''+cards(services)+'''</div></section><section id="about" class="about"><div><span class="eyebrow">A MORE PERSONAL APPROACH</span><h2>Good decisions start with a conversation.</h2></div><div><p>'''+H(p.get('about'))+'''</p><a class="text-link" href="#contact">Let’s talk <span>→</span></a></div></section><section class="section faq" id="faq"><div><span class="eyebrow">GOOD TO KNOW</span><h2>Questions, answered.</h2></div><div>'''+questions+'''</div></section><section class="contact" id="contact"><div><span class="eyebrow">READY WHEN YOU ARE</span><h2>'''+H(p.get('contact_heading'))+'''</h2><p>Tell us a little about what you’re looking for.</p></div><form id="contact-form"><label for="name">Your name</label><input id="name" name="name" required placeholder="Name"><label for="email">Email address</label><input id="email" name="email" type="email" required placeholder="you@example.com"><label for="message">How can we help?</label><textarea id="message" name="message" required placeholder="Tell us more"></textarea><button class="button" type="submit">Prepare message ↗</button><p id="form-note">Form is a placeholder. Add a contact email before publishing.</p></form></section></main><footer><a class="brand" href="#home"><span class="brand-mark">✳</span> '''+H(p.get('business'))+'''</a><p>Made with care for what matters.</p><a href="#home">Back to top ↑</a></footer></body></html>'''
    css=''' :root{--brand:COLOR;--ink:#1b2a25;--muted:#65716c;--cream:#f8f7f1}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--cream);color:var(--ink);font-family:Inter,system-ui,sans-serif}a{color:inherit;text-decoration:none}a:focus-visible,button:focus-visible,input:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid #d48b42;outline-offset:3px}.header{height:82px;display:flex;align-items:center;justify-content:space-between;max-width:1440px;margin:auto;padding:0 6%;border-bottom:1px solid #e8e9e0}.brand{font-weight:750;letter-spacing:-.04em;font-size:20px;display:flex;align-items:center;gap:10px}.brand-mark{color:var(--brand);font-size:29px}.header nav{display:flex;align-items:center;gap:36px;font-size:13px;font-weight:600}.nav-cta{background:var(--ink);color:white;border-radius:5px;padding:14px 19px}.menu-toggle{display:none}.hero{max-width:1440px;margin:auto;padding:74px 6% 90px;display:grid;grid-template-columns:1fr 1fr;gap:6%;align-items:center}.eyebrow{font-size:11px;letter-spacing:.16em;font-weight:800;color:var(--brand)}.eyebrow span{font-size:18px}h1,h2{font-family:Georgia,serif;letter-spacing:-.045em;font-weight:500;line-height:1.07}h1{font-size:clamp(44px,5vw,76px);max-width:660px;margin:30px 0 24px}h2{font-size:clamp(34px,3.8vw,52px);margin:20px 0}.hero-content>p,.section-head>p,.about p{color:var(--muted);font-size:16px;line-height:1.8;max-width:475px}.hero-actions{display:flex;align-items:center;gap:27px;margin-top:34px}.button{background:var(--brand);color:white;display:inline-flex;gap:35px;align-items:center;justify-content:space-between;padding:16px 20px;border:0;border-radius:5px;font-weight:700;font-size:13px;cursor:pointer}.text-link{font-size:13px;font-weight:700}.hero-note{border-top:1px solid #e1e5dc;margin-top:64px;padding-top:20px;font-size:12px;color:#78837a}.note-icon{color:var(--brand);margin-right:8px}.hero-visual{background:#c8dacb;min-height:480px;position:relative;overflow:hidden;border-radius:8px}.sun{position:absolute;top:14%;left:24%;width:145px;height:145px;background:#eee4c9;border-radius:50%}.hill{position:absolute;border-radius:50%;width:130%;height:85%;left:-35%;bottom:-47%;background:#82a995;transform:rotate(-20deg)}.hill-two{left:25%;bottom:-58%;background:#557e6b;transform:rotate(24deg)}.visual-label{position:absolute;bottom:26px;left:26px;background:#fffdf8;padding:15px 19px;display:flex;align-items:center;gap:13px;border-radius:5px;font-size:12px}.visual-label span{font-size:30px;color:var(--brand)}.visual-label small{display:block;color:var(--muted);margin-top:4px}.section{max-width:1440px;margin:auto;padding:90px 6%}.section-head{display:flex;justify-content:space-between;align-items:end;margin-bottom:35px}.section-head>p{max-width:335px}.service-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.service{background:white;border:1px solid #ebeee8;padding:28px;border-radius:7px;min-height:240px}.service-icon{color:var(--brand);font-size:29px}.service h3{margin:23px 0 12px;font-family:Georgia,serif;font-size:22px;font-weight:500}.service p{font-size:13px;line-height:1.7;color:var(--muted);min-height:55px}.service a{font-size:12px;font-weight:700}.service a span{float:right}.about{background:#dce9de;display:grid;grid-template-columns:1fr 1fr;gap:15%;padding:85px 6%}.about>div:first-child{max-width:550px}.about p{color:#40554b}.faq{display:grid;grid-template-columns:1fr 1fr;gap:10%}details{border-bottom:1px solid #dfe4dc;padding:20px 0}summary{cursor:pointer;font-weight:700;font-size:14px}details p{color:var(--muted);line-height:1.7;font-size:14px}.contact{padding:90px 6%;background:#203c32;color:white;display:grid;grid-template-columns:1fr 1fr;gap:12%}.contact .eyebrow{color:#a9d4b7}.contact p{color:#bdd1c4;line-height:1.6}form{display:grid;gap:10px}label{font-size:12px;font-weight:700}input,textarea{font:inherit;padding:13px;border:1px solid #8fa69a;border-radius:4px}textarea{min-height:90px}form .button{justify-content:center;margin-top:8px}#form-note{font-size:11px}footer{padding:32px 6%;display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--muted)}@media(max-width:768px){.header{height:68px}.menu-toggle{display:block;border:0;background:none;font-size:24px;color:var(--ink)}.header nav{display:none;position:absolute;top:68px;left:0;right:0;z-index:2;background:var(--cream);padding:20px 6%;flex-direction:column;align-items:flex-start}.header nav.open{display:flex}.hero{grid-template-columns:1fr;padding-top:45px;gap:35px}.hero-visual{min-height:360px}.hero-note{margin-top:35px}.section-head{display:block}.service-grid{grid-template-columns:1fr}.about,.faq,.contact{grid-template-columns:1fr;gap:25px}.section{padding-top:65px;padding-bottom:65px}footer{flex-wrap:wrap;gap:18px}}
'''.replace('COLOR',color)
    js='''const button=document.querySelector('.menu-toggle');const nav=document.querySelector('#nav');button?.addEventListener('click',()=>{const opened=nav.classList.toggle('open');button.setAttribute('aria-expanded',String(opened))});nav?.addEventListener('click',e=>{if(e.target.closest('a')){nav.classList.remove('open');button.setAttribute('aria-expanded','false')}});document.querySelector('#contact-form')?.addEventListener('submit',e=>{e.preventDefault();document.querySelector('#form-note').textContent='Please add a contact email or form handler before publishing.'});'''
    return {'index.html':index,'styles.css':css,'script.js':js}

class NewProject(BaseModel): name:str=Field(min_length=1,max_length=120); brief:str=Field(default='',max_length=12000)
class Rename(BaseModel): name:str=Field(min_length=1,max_length=120)
class Save(BaseModel): files:dict; label:str='Manual edit'
class Generate(BaseModel): prompt:str=Field(min_length=1,max_length=12000); mode:str='build'; language:str='en'
class ModelChoice(BaseModel): provider:str='ollama'; model:str=Field(min_length=1,max_length=200)
class Pull(BaseModel): model:str=Field(min_length=1,max_length=200)

@router.get('/projects')
def list_projects():
    with db() as c: return [dict(r) for r in c.execute('SELECT id,name,brief,created,updated FROM projects ORDER BY updated DESC')]
@router.post('/projects')
def create_project(body:NewProject):
    pid=uuid.uuid4().hex[:12]; now=time.time(); files=render_site({'business':body.name,'headline':'Something wonderful starts here.','subheadline':'Your new website is ready to take shape.','cta':'Explore','services':[],'faq':[],'about':'Tell us about your business.','contact_heading':'Let’s talk.'})
    with db() as c: c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',(pid,body.name,body.brief,json.dumps(files),now,now)); c.execute('INSERT INTO versions(project_id,label,files,created) VALUES(?,?,?,?)',(pid,'Initial draft',json.dumps(files),now))
    return project(pid)
@router.get('/projects/{pid}')
def get_project(pid:str):
    p=project(pid); p['messages']=messages(pid); return p
@router.patch('/projects/{pid}')
def rename(pid:str,body:Rename):
    project(pid)
    with db() as c: c.execute('UPDATE projects SET name=?,updated=? WHERE id=?',(body.name,time.time(),pid))
    return {'ok':True}
@router.put('/projects/{pid}/files')
def save_files(pid:str,body:Save):
    project(pid)
    try: snapshot(pid,body.files,body.label)
    except ValueError as e: raise HTTPException(400,str(e))
    return {'ok':True}
@router.get('/projects/{pid}/versions')
def versions(pid:str):
    project(pid)
    with db() as c: return [dict(r) for r in c.execute('SELECT id,label,created FROM versions WHERE project_id=? ORDER BY id DESC',(pid,))]
@router.get('/projects/{pid}/versions/{vid}')
def get_version(pid:str,vid:int):
    with db() as c: row=c.execute('SELECT id,label,created,files FROM versions WHERE project_id=? AND id=?',(pid,vid)).fetchone()
    if not row: raise HTTPException(404,'Version not found')
    d=dict(row); d['files']=json.loads(d['files']); return d
@router.post('/projects/{pid}/versions/{vid}/restore')
def restore(pid:str,vid:int):
    v=get_version(pid,vid); snapshot(pid,v['files'],'Restored: '+v['label']); return project(pid)
@router.get('/projects/{pid}/export')
def export(pid:str):
    p=project(pid); bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in p['files'].items(): z.writestr(name,content)
    return Response(bio.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="siteforge-export.zip"'})
@router.get('/settings')
def settings():
    provider=get_setting('provider',os.getenv('PROVIDER','ollama')); model=get_setting('model',DEFAULT)
    return {'provider':provider,'model':model,'providers':[{'id':k,'label':v[0],'configured': k=='ollama' or bool(provider_key(k))} for k,v in PROVIDERS.items()]}
@router.put('/settings')
def update_settings(body:ModelChoice):
    if body.provider not in PROVIDERS: raise HTTPException(400,'Unknown provider')
    if body.provider=='openrouter' and not body.model.endswith(':free'): raise HTTPException(400,'Only OpenRouter :free models are permitted')
    set_setting('provider',body.provider); set_setting('model',body.model); return {'ok':True}
@router.get('/ollama/models')
async def ollama_models():
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r=await c.get(OLLAMA+'/api/tags'); r.raise_for_status(); items=r.json().get('models',[])
        async with httpx.AsyncClient(timeout=8) as c:
            ps=await c.get(OLLAMA+'/api/ps'); ps.raise_for_status(); running=[x.get('name','') for x in ps.json().get('models',[])]
        active=get_setting('active_model','')
        return {'online':True,'models':[{'name':m['name'],'size':m.get('size',0),'parameters':m.get('details',{}).get('parameter_size','')} for m in items], 'active':active if active in running else ''}
    except Exception: return {'online':False,'models':[],'active':''}
@router.post('/ollama/activate')
async def activate(body:Pull):
    if queue.locked(): raise HTTPException(409,'A generation is running; stop it before switching models.')
    try:
        async with queue, httpx.AsyncClient(timeout=300) as c:
            old=get_setting('active_model','')
            if old and old!=body.model: await c.post(OLLAMA+'/api/generate',json={'model':old,'keep_alive':0})
            r=await c.post(OLLAMA+'/api/generate',json={'model':body.model,'prompt':'Hi','stream':False,'keep_alive':'30m','options':{'num_predict':1,'num_ctx':4096}}); r.raise_for_status()
            set_setting('active_model',body.model)
        return {'ok':True,'model':body.model}
    except Exception: raise HTTPException(502,'Could not activate the model. Check Ollama and available RAM.')
@router.post('/ollama/unload')
async def unload(body:Pull):
    if queue.locked(): raise HTTPException(409,'Stop the current generation first.')
    try:
        async with queue, httpx.AsyncClient(timeout=30) as c:
            r=await c.post(OLLAMA+'/api/generate',json={'model':body.model,'keep_alive':0}); r.raise_for_status()
        set_setting('active_model',''); return {'ok':True}
    except Exception: raise HTTPException(502,'Could not unload model')
@router.post('/ollama/delete')
async def delete_model(body:Pull):
    if queue.locked(): raise HTTPException(409,'Stop the current generation first.')
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r=await c.request('DELETE',OLLAMA+'/api/delete',json={'model':body.model}); r.raise_for_status()
        return {'ok':True}
    except Exception: raise HTTPException(502,'Could not delete model')
@router.post('/ollama/pull')
async def pull(body:Pull):
    if not re.fullmatch(r'[\w.:-]+(?:/[\w.:-]+)?',body.model): raise HTTPException(400,'Invalid model name')
    async def stream():
        try:
            async with httpx.AsyncClient(timeout=None) as c:
                async with c.stream('POST',OLLAMA+'/api/pull',json={'model':body.model,'stream':True}) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if line: yield 'data: '+line+'\n\n'
        except Exception: yield 'data: '+json.dumps({'error':'Pull failed. Check Ollama and network connection.'})+'\n\n'
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

init()

def event(kind,**kwargs): return 'data: '+json.dumps({'type':kind,**kwargs},ensure_ascii=False)+'\n\n'

def provider_key(provider):
    # Share server-side credentials configured through the Agency Office UI.
    try:
        saved = agency_db.kv_get(f'token_{provider}')
    except Exception:
        saved = None
    return saved if saved is not None else os.getenv(PROVIDERS[provider][1] or '', '')

def candidates():
    selected=get_setting('provider',os.getenv('PROVIDER','ollama')); model=get_setting('model',DEFAULT)
    out=[]
    if selected in PROVIDERS:
        if selected=='ollama' or provider_key(selected): out.append((selected,model))
    for k in ('ollama','openrouter','groq','gemini'):
        if k==selected: continue
        if k=='ollama': out.append((k,DEFAULT))
        elif provider_key(k): out.append((k,DEFAULT_CLOUD[k]))
    return out

async def model_reply(provider,model,system,user):
    timeout=httpx.Timeout(900,connect=12)
    if provider=='ollama':
        old=get_setting('active_model','')
        async with httpx.AsyncClient(timeout=timeout) as client:
            if old and old!=model:
                r=await client.post(OLLAMA+'/api/generate',json={'model':old,'keep_alive':0}); r.raise_for_status()
            payload={'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':user}],'stream':True,'format':'json','keep_alive':'30m','options':{'num_ctx':4096,'temperature':0.3,'num_predict':1800}}
            async with client.stream('POST',OLLAMA+'/api/chat',json=payload) as r:
                r.raise_for_status(); set_setting('active_model',model)
                async for line in r.aiter_lines():
                    if not line: continue
                    d=json.loads(line)
                    if d.get('error'): raise ValueError('Ollama generation failed')
                    token=d.get('message',{}).get('content','')
                    if token: yield token
    else:
        key=provider_key(provider)
        if not key: raise ValueError('Provider key not configured')
        if provider=='openrouter' and not model.endswith(':free'): raise ValueError('Only free OpenRouter models allowed')
        bases={'openrouter':'https://openrouter.ai/api/v1','groq':'https://api.groq.com/openai/v1','gemini':'https://generativelanguage.googleapis.com/v1beta/openai'}
        payload={'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':user}],'temperature':0.3,'stream':True,'max_tokens':1800}
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream('POST',bases[provider]+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if line.startswith('data: ') and line[6:]!='[DONE]':
                        d=json.loads(line[6:]); delta=d.get('choices',[{}])[0].get('delta',{}).get('content','')
                        if delta: yield delta

@router.post('/projects/{pid}/generate')
async def generate(pid:str,body:Generate):
    p=project(pid); save_message(pid,'user',body.prompt)
    async def stream():
        start=time.monotonic(); yield event('step',step='Queued',message='Waiting for the generation queue…')
        async with queue:
            mode=body.mode if body.mode in ('build','edit','marketing') else 'build'
            promptfile='planner.txt' if mode=='build' else 'edit.txt' if mode=='edit' else 'marketing.txt'
            system=(PROMPTS/promptfile).read_text()
            if mode=='edit':
                combined=json.dumps(p['files'],ensure_ascii=False)
                if len(combined)>12000:
                    yield event('error',message='This edit exceeds the 4096-token context budget. Edit a file manually or shorten it first.'); return
                user=f'Change request: {body.prompt}\nCurrent files: {combined}'
            else: user=f'Language: {body.language}. Project: {p["name"]}. Brief: {body.prompt}'
            yield event('step',step='Planning' if mode=='build' else 'Writing code' if mode=='edit' else 'Marketing',message='Nora is preparing your request.')
            errors=[]
            for i,(provider,model) in enumerate(candidates()):
                if i: yield event('step',step='Fallback',message=f'Switched to {model} ({provider}) after a provider error.')
                for attempt in range(3):
                    try:
                        raw=''; begin=time.monotonic()
                        retry_user=user if attempt==0 else user+'\nYour previous response was invalid JSON. Output valid JSON only, with every field properly quoted.'
                        async for chunk in model_reply(provider,model,system,retry_user):
                            raw+=chunk
                            if len(raw)>350000: raise ValueError('Output too large')
                            yield event('token',text=chunk)
                        result=repair_json(raw)
                        if not isinstance(result,dict): raise ValueError('Expected object')
                        if mode=='build':
                            if not result.get('headline') or not isinstance(result.get('services'),list): raise ValueError('Missing plan fields')
                            result['language']=body.language if body.language in ('en','fr','ar') else 'en'
                            yield event('step',step='Designing',message='Lina is assembling the visual direction.')
                            files=render_site(result); validate_files(files)
                            yield event('step',step='Reviewing',message='Rami is checking the file structure.')
                            report=qa(files)
                            snapshot(pid,files,'AI-generated website'); summary='Your site is ready. Review the content and replace placeholders before publishing.'
                        elif mode=='edit':
                            path=result.get('path'); content=result.get('content')
                            if path not in ALLOWED or not isinstance(content,str): raise ValueError('Invalid edited file')
                            files={**p['files'],path:content}; validate_files(files); report=qa(files)
                            snapshot(pid,files,'AI edit'); summary=str(result.get('summary','Changes applied.'))[:1000]
                        else:
                            report={}; summary=json.dumps(result,ensure_ascii=False,indent=2)[:12000]
                        save_message(pid,'assistant',summary)
                        elapsed=max(time.monotonic()-begin,0.01)
                        yield event('done',summary=summary,report=report,provider=provider,model=model,elapsed=round(time.monotonic()-start,1),characters_per_second=round(len(raw)/elapsed,1))
                        return
                    except asyncio.CancelledError: raise
                    except (json.JSONDecodeError,ValueError) as e:
                        if attempt<2:
                            yield event('step',step='Repairing',message='Invalid response; asking for valid JSON again.'); continue
                        errors.append('Invalid model response'); break
                    except Exception:
                        errors.append('Provider unavailable or request failed'); break
            msg='No configured provider produced a valid response. Check the selected model, connection and server-side keys, then retry.'
            save_message(pid,'assistant',msg); yield event('error',message=msg)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

def qa(files):
    s=files.get('index.html',''); css=files.get('styles.css',''); checks=[
      ('One main heading',len(re.findall(r'<h1\b',s,re.I))==1),('Page title',bool(re.search(r'<title>.+?</title>',s,re.I|re.S))),
      ('Meta description','name="description"' in s),('Viewport', 'name="viewport"' in s),('Responsive styles','@media' in css),
      ('Visible focus styles',':focus-visible' in css),('No lorem ipsum or TODO',not re.search(r'lorem ipsum|\bTODO\b',s,re.I)),
      ('Images have alt text', all(re.search(r'\balt\s*=',i,re.I) for i in re.findall(r'<img\b[^>]*>',s,re.I))),
      ('CSS and JS files present','styles.css' in files and 'script.js' in files),
    ]
    return {'checks':[{'name':n,'passed':b} for n,b in checks], 'note':'Static checks only. Responsive rendering, contrast, link integrity and accessibility require manual review.'}
@router.get('/projects/{pid}/qa')
def project_qa(pid:str): return qa(project(pid)['files'])
class Note(BaseModel): content:str=Field(min_length=1,max_length=10000)
@router.post('/projects/{pid}/handoffs')
def save_handoff(pid:str,body:Note):
    project(pid); save_message(pid,'handoff',body.content); return {'ok':True}

@router.post('/providers/{provider}/test')
async def test_provider(provider:str):
    if provider not in PROVIDERS: raise HTTPException(404,'Unknown provider')
    if provider=='ollama':
        d=await ollama_models(); return {'ok':d['online'],'message':'Ollama reachable' if d['online'] else 'Ollama is offline'}
    key=provider_key(provider)
    if not key: return {'ok':False,'message':'No server-side key configured'}
    bases={'openrouter':'https://openrouter.ai/api/v1','groq':'https://api.groq.com/openai/v1','gemini':'https://generativelanguage.googleapis.com/v1beta/openai'}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r=await c.get(bases[provider]+'/models',headers={'Authorization':'Bearer '+key}); r.raise_for_status()
        return {'ok':True,'message':'Connection and key accepted; model availability and free-tier quota are not verified.'}
    except Exception: return {'ok':False,'message':'Provider test failed; check the server key and internet connection.'}
