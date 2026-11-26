"""One server-side provider catalog, model selection, benchmark and AI proxy.
All credentials are resolved on the server. No arbitrary client-supplied URLs in
chat/image requests. Benchmarks are opt-in, bounded, and may consume quota.
"""
import asyncio
import base64
import ipaddress
import json
import os
import re
import socket
import time
from urllib.parse import urlsplit
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from . import db
from .config import settings, PROVIDER_PRESETS

router = APIRouter(prefix='/api', tags=['AI proxy'])


def validate_endpoint(base, local=False, resolve=False):
    try:
        u = urlsplit(base)
        if u.username or u.password or u.query or u.fragment or not u.hostname: raise ValueError()
        if u.scheme not in ('http','https'): raise ValueError()
        hosted = os.getenv('VERCEL') == '1' or os.getenv('APP_ENV') == 'production'
        if u.scheme != 'https' and (hosted or not local): raise ValueError()
        if u.hostname.lower() in ('metadata.google.internal','instance-data','169.254.169.254'): raise ValueError()
        try: addresses = [ipaddress.ip_address(u.hostname)]
        except ValueError:
            addresses = [ipaddress.ip_address(a[4][0]) for a in socket.getaddrinfo(u.hostname, u.port or 443)] if resolve else []
            if u.hostname.lower() == 'localhost' and (hosted or not local): raise ValueError()
        if (hosted or not local) and any(not a.is_global for a in addresses): raise ValueError()
    except (ValueError, OSError): raise HTTPException(422, 'Use a reachable HTTPS provider endpoint without credentials, queries or private/metadata addresses. Local HTTP runtimes require a local backend.') from None
    return base.rstrip('/')


def refresh():
    from .hosted_settings import refresh as sync
    sync()


def config(key):
    if key not in PROVIDER_PRESETS: raise HTTPException(404, 'Unknown provider.')
    refresh()
    p = PROVIDER_PRESETS[key]
    c = settings.provider_creds.get(key, {})
    return c.get('base_url') or p['base_url'], c.get('token', ''), c.get('model') or p['model']


def selected():
    refresh()
    return {'provider':settings.active_provider, 'model':settings.text_model, 'image_model':settings.image_model}


def choose(key, model):
    if key not in PROVIDER_PRESETS: raise HTTPException(422, 'Unknown provider.')
    if not model.strip(): raise HTTPException(422, 'Select a model.')
    db.kv_set('active_provider', key)
    db.kv_set('model_' + key, model)
    settings.active_provider = key
    settings.provider_creds.setdefault(key,{})['model'] = model
    settings.text_model = model
    base, token, _ = config(key)
    settings.api_base_url = base
    settings.api_token = token
    from .provider import reset_provider
    reset_provider()


def tags(model, key):
    name = model['id'].lower()
    return [tag for tag, condition in [('Free',model.get('free')),('Local',key=='ollama'),('Cloud',key!='ollama'),('Vision', bool(re.search('vision|vl|llava|gemini|gpt-4|llama-4',name))),('Code', bool(re.search('coder|code|devstral',name))),('Fast',bool(re.search('mini|flash|small|3b|1b|nano',name)))] if condition]


async def discover(key):
    from .provider import fetch_models
    base, token, model = config(key)
    start=time.perf_counter()
    if db.kv_get('disconnected_'+key) == '1': return {'valid':False,'models':[],'error':'Disconnected. Reconnect to test.'}
    if key != 'ollama' and not token: return {'valid':False,'models':[],'error':'No server-side key configured.'}
    try:
        validate_endpoint(base, local=key=='ollama', resolve=True)
        result = await fetch_models(key, base, token)
    except HTTPException as e: result = {'valid':False,'models':[],'error':e.detail}
    for item in result.get('models',[]): item['tags'] = tags(item,key)
    result.update(provider=key, label=PROVIDER_PRESETS[key]['label'], checked_at=time.time(), selected=model, latency_ms=round((time.perf_counter()-start)*1000))
    db.kv_set('catalog_'+key,json.dumps(result))
    return result


@router.get('/models')
async def models(refresh_catalog: bool = False):
    refresh()
    results=[]
    for key in PROVIDER_PRESETS:
        cached=db.kv_get('catalog_'+key)
        results.append(json.loads(cached) if cached else {'provider':key,'label':PROVIDER_PRESETS[key]['label'],'models':[],'valid':False,'error':'Not checked yet.'})
    if refresh_catalog:
        results=await asyncio.gather(*(discover(key) for key in PROVIDER_PRESETS))
    return {'selection':selected(),'providers':results,'checked_at':time.time()}


class Selection(BaseModel):
    provider: str = Field(max_length=40)
    model: str = Field(min_length=1,max_length=200)
    image_model: str | None = Field(default=None,max_length=200)


@router.put('/models/selection')
def selection(body: Selection):
    if db.kv_get('disconnected_'+body.provider)=='1':raise HTTPException(409,'Reconnect and test this provider first.')
    cached=json.loads(db.kv_get('catalog_'+body.provider,'{}'))
    if not cached.get('valid') or body.model not in [m['id'] for m in cached.get('models',[])]: raise HTTPException(422,'Test the connection and select a verified model first.')
    choose(body.provider,body.model)
    if body.image_model is not None:
        if body.image_model not in ('pollinations-free','hf-flux-schnell','local-sd','none'): raise HTTPException(422,'Unknown image model.')
        db.kv_set('image_model',body.image_model); settings.image_model=body.image_model
    return selected()


class Disconnect(BaseModel):
    disconnected: bool


@router.put('/providers/{key}/connection')
def connection(key: str, body: Disconnect):
    config(key)
    db.kv_set('disconnected_'+key,'1' if body.disconnected else '0')
    if body.disconnected:db.kv_set('catalog_'+key,json.dumps({'provider':key,'label':PROVIDER_PRESETS[key]['label'],'valid':False,'models':[],'error':'Disconnected','checked_at':time.time()}))
    from .provider import reset_provider
    reset_provider()
    return {'ok':True}


@router.delete('/providers/{key}/credential')
def delete_credential(key: str):
    config(key)
    db.kv_set('token_'+key,'')
    settings.provider_creds.setdefault(key,{})['token']=''
    db.kv_set('disconnected_'+key,'1')
    db.kv_set('catalog_'+key,json.dumps({'provider':key,'label':PROVIDER_PRESETS[key]['label'],'valid':False,'models':[],'error':'Credential removed','checked_at':time.time()}))
    if settings.active_provider==key: settings.api_token=''
    from .provider import reset_provider
    reset_provider()
    return {'ok':True}


class Message(BaseModel):
    role: str = Field(pattern='^(user|assistant|system)$')
    content: str = Field(min_length=1,max_length=30000)


class Chat(BaseModel):
    messages: list[Message] = Field(min_length=1,max_length=30)
    image: str | None = Field(default=None,max_length=1_400_000)
    json_output: bool = False


async def complete(key, model, messages, image=None, json_output=False):
    base, token, _ = config(key)
    validate_endpoint(base,local=key=='ollama',resolve=True)
    if db.kv_get('disconnected_'+key)=='1': raise ValueError('Provider disconnected')
    if key!='ollama' and not token: raise ValueError('No server-side credential')
    outgoing=[dict(m) for m in messages]
    if image:
        if not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+',image): raise HTTPException(422,'Use a PNG, JPEG or WebP reference image up to 1 MB.')
        raw=base64.b64decode(image.split(',')[1],validate=True)
        if len(raw)>1_000_000: raise HTTPException(413,'Reference image exceeds 1 MB.')
        outgoing[-1]['content']=[{'type':'text','text':outgoing[-1]['content']},{'type':'image_url','image_url':{'url':image}}]
    if key=='ollama_cloud' and base.rstrip('/').endswith('/api'): base=base[:-4]+'/v1'
    if key=='ollama' and not base.endswith('/v1'): base=base.rstrip('/')+'/v1'
    payload={'model':model,'messages':outgoing,'max_tokens':6000,'temperature':0.3}
    if json_output: payload['response_format']={'type':'json_object'}
    async with httpx.AsyncClient(timeout=httpx.Timeout(55,connect=10),follow_redirects=False) as c:
        r=await c.post(base.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+(token or 'ollama')},json=payload)
        r.raise_for_status()
        data=r.json()
        text=data.get('choices',[{}])[0].get('message',{}).get('content')
        if not isinstance(text,str) or not text.strip(): raise ValueError('Empty provider output')
        return text


async def stream_complete(key, model, messages, image=None):
    base,token,_=config(key)
    validate_endpoint(base,local=key=='ollama',resolve=True)
    if db.kv_get('disconnected_'+key)=='1' or (key!='ollama' and not token): raise ValueError('Provider unavailable')
    if image:
        if not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+',image): raise ValueError('Invalid reference image')
        if len(base64.b64decode(image.split(',')[1],validate=True))>1000000: raise ValueError('Reference too large')
        messages[-1]['content']=[{'type':'text','text':messages[-1]['content']},{'type':'image_url','image_url':{'url':image}}]
    if key=='ollama_cloud' and base.endswith('/api'): base=base[:-4]+'/v1'
    if key=='ollama' and not base.endswith('/v1'): base=base.rstrip('/')+'/v1'
    payload={'model':model,'messages':messages,'stream':True,'max_tokens':6000,'temperature':0.3,'response_format':{'type':'json_object'}}
    async with httpx.AsyncClient(timeout=httpx.Timeout(55,connect=10),follow_redirects=False) as client:
        async with client.stream('POST',base.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+(token or 'ollama')},json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith('data: ') or line[6:]=='[DONE]': continue
                item=json.loads(line[6:])
                if item.get('error'): raise ValueError('Provider stream failed')
                text=item.get('choices',[{}])[0].get('delta',{}).get('content')
                if text: yield text


@router.post('/chat')
async def chat(body:Chat):
    current=selected(); key,model=current['provider'],current['model']
    if body.image:
        catalog=await models()
        vision=[(p['provider'],m['id']) for p in catalog['providers'] if p.get('valid') for m in p.get('models',[]) if 'Vision' in m.get('tags',[])]
        if (key,model) not in vision:
            if not vision: raise HTTPException(409,'No verified Vision model. Test a vision-capable provider in Connections first.')
            key,model=vision[0]
    try: text=await complete(key,model,[m.model_dump() for m in body.messages],body.image,body.json_output)
    except HTTPException: raise
    except Exception: raise HTTPException(502,'Selected model unavailable. Test Connections and retry.') from None
    return {'content':text,'provider':key,'model':model}


class Benchmark(BaseModel):
    candidates: list[Selection] = Field(min_length=1,max_length=8)
    role: str = Field(default='Manager',pattern='^(Manager|Designer|Developer|Vision)$')


@router.post('/models/benchmark')
async def benchmark(body:Benchmark):
    async def measure(candidate):
        result={'provider':candidate.provider,'model':candidate.model,'valid':False,'json':False,'latency_ms':None}
        catalog=json.loads(db.kv_get('catalog_'+candidate.provider,'{}'))
        match=next((m for m in catalog.get('models',[]) if m['id']==candidate.model),None)
        if not catalog.get('valid') or not match: return {**result,'why':'Not in a verified provider catalog.'}
        started=time.perf_counter()
        task={'Manager':'Give one reasoning step for prioritizing a blocked task.','Designer':'Suggest a distinctive accessible hero design.','Developer':'Write a JavaScript sum function.','Vision':'Describe your image-understanding capabilities; this text probe does not verify vision.'}[body.role]
        try:
            text=await complete(candidate.provider,candidate.model,[{'role':'user','content':task+' Return JSON with a nonempty answer string.'}],json_output=True)
            result.update(valid=bool(text.strip()),latency_ms=round((time.perf_counter()-started)*1000))
            try: result['json']=bool(json.loads(text).get('answer'))
            except (ValueError,AttributeError): pass
        except Exception: pass
        preferred=match.get('free') or candidate.provider=='ollama'
        result['score']=(100 if result['json'] else 0)+(20 if preferred else 0)-(result['latency_ms'] or 60000)/10000
        result['why']=('Valid JSON; ' if result['json'] else 'Invalid JSON or unavailable; ')+('free/local preference; ' if preferred else 'may consume paid quota; ')+'measured text probe, not a full capability evaluation.'
        return result
    # Two probes at a time to avoid saturating local runtimes or upstream quotas.
    semaphore=asyncio.Semaphore(2)
    async def bounded(c):
        async with semaphore: return await measure(c)
    rows=await asyncio.gather(*(bounded(c) for c in body.candidates))
    healthy=sorted([r for r in rows if r['json']],key=lambda r:r['score'],reverse=True)
    return {'results':rows,'recommended':healthy[0] if healthy else None,'role':body.role,'applied':False}


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1,max_length=2000)


@router.post('/image')
async def image(body:ImageRequest):
    from fastapi.responses import Response
    from urllib.parse import quote
    model=selected()['image_model']
    try:
        async with httpx.AsyncClient(timeout=55,follow_redirects=False) as c:
            if model=='pollinations-free':
                r=await c.get('https://image.pollinations.ai/prompt/'+quote(body.prompt,safe=''),params={'width':768,'height':512,'nologo':'true'})
            elif model=='hf-flux-schnell':
                token=db.kv_get('image_token') or os.getenv('HF_TOKEN','')
                if not token: raise HTTPException(409,'Configure the server HF_TOKEN or an encrypted image credential first.')
                r=await c.post('https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell',headers={'Authorization':'Bearer '+token},json={'inputs':body.prompt})
            elif model=='local-sd':
                endpoint=db.kv_get('image_endpoint','')
                validate_endpoint(endpoint,local=True,resolve=True)
                r=await c.post(endpoint+'/sdapi/v1/txt2img',json={'prompt':body.prompt,'steps':4,'width':768,'height':512})
                r.raise_for_status()
                return Response(base64.b64decode(r.json()['images'][0]),media_type='image/png')
            else: raise HTTPException(409,'Select an image provider in Connections.')
            r.raise_for_status()
            if not r.headers.get('content-type','').startswith('image/') or len(r.content)>10_000_000: raise ValueError()
            return Response(r.content,media_type=r.headers['content-type'],headers={'Cache-Control':'no-store'})
    except HTTPException: raise
    except Exception: raise HTTPException(502,'Image provider unavailable, quota exhausted, or response invalid. No placeholder was substituted.') from None


class ImageConfig(BaseModel):
    endpoint: str | None = Field(default=None,max_length=500)
    token: str | None = Field(default=None,max_length=4096)


@router.put('/providers/image/config')
def image_config(body: ImageConfig):
    if body.endpoint is not None: db.kv_set('image_endpoint',validate_endpoint(body.endpoint,local=True))
    if body.token is not None: db.kv_set('image_token',body.token)
    return {'ok':True}


class Fallback(BaseModel):
    provider: str = Field(max_length=40)
    model: str = Field(max_length=200)


@router.post('/models/fallback')
def fallback(body:Fallback):
    current=selected()
    if (body.provider,body.model)!=(current['provider'],current['model']):return {'changed':False,'selection':current}
    old=json.loads(db.kv_get('catalog_'+body.provider,'{}'))
    if not old.get('checked_at') or (old.get('valid') and any(m['id']==body.model for m in old.get('models',[]))):return {'changed':False,'selection':current}
    healthy=[]
    for key in PROVIDER_PRESETS:
        cached=json.loads(db.kv_get('catalog_'+key,'{}'))
        if cached.get('valid') and db.kv_get('disconnected_'+key)!='1':
            healthy.extend((0 if key=='ollama' else 1 if m.get('free') else 2,key,m['id']) for m in cached.get('models',[]) if not m.get('image'))
    if not healthy:return {'changed':False,'selection':current,'warning':'No verified healthy fallback.'}
    _,key,model=sorted(healthy)[0]
    choose(key,model)
    return {'changed':True,'selection':selected(),'warning':'The selected model is unavailable. Switched to a verified healthy model; local/free preference applies.'}
