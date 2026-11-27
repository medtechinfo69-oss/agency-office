"""Provider protocol contracts. Mock transport only; not live inference."""
import asyncio
import httpx
from app import provider


def test_anthropic_discovery_uses_native_headers(monkeypatch):
    real=httpx.AsyncClient
    def handle(request):
        assert str(request.url)=='https://api.anthropic.com/v1/models'
        assert request.headers['x-api-key']=='test-only'
        assert request.headers['anthropic-version']=='2023-06-01'
        assert 'authorization' not in request.headers
        return httpx.Response(200,json={'data':[{'id':'claude-test','display_name':'Claude Test'}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(handle),**kwargs))
    data=asyncio.run(provider.fetch_models('anthropic','https://api.anthropic.com','test-only'))
    assert data['valid'] and data['models'][0]['id']=='claude-test'


def test_ollama_cloud_falls_back_to_openai_catalog_not_local_free(monkeypatch):
    real=httpx.AsyncClient
    def handle(request):
        if request.url.path=='/api/tags':return httpx.Response(404)
        assert request.url.path=='/v1/models'
        assert request.headers['authorization']=='Bearer test-only'
        return httpx.Response(200,json={'data':[{'id':'cloud-test'}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(handle),**kwargs))
    data=asyncio.run(provider.fetch_models('ollama_cloud','https://ollama.com/api','test-only'))
    assert data['valid'] and not data['models'][0]['free']


def test_anthropic_chat_native_messages_and_usage(monkeypatch):
    async def request(self,method,path,payload):
        assert path=='/messages'
        assert payload['system']=='Follow agency rules'
        assert payload['messages']==[{'role':'user','content':'Write a caption'}]
        assert 'Authorization' not in self._headers()
        return {'content':[{'type':'text','text':'Useful caption'}],'usage':{'input_tokens':12,'output_tokens':4}}
    monkeypatch.setattr(provider.OpenAIProvider,'_request',request)
    transport=provider.OpenAIProvider(provider.ProviderConfig('anthropic','Claude','https://api.anthropic.com/v1','test-only','claude-test'))
    result=asyncio.run(transport.chat([{'role':'system','content':'Follow agency rules'},{'role':'user','content':'Write a caption'}]))
    assert result.text=='Useful caption' and result.usage.tokens_in==12 and result.usage.tokens_out==4


def test_arena_preset_and_legacy_env_identification():
    from app.config import PROVIDER_PRESETS, match_preset, provider_base_url
    assert PROVIDER_PRESETS['arena']['base_url']=='https://api.arena.ai/v1'
    for base in ['https://platform.arena.ai/v1/','https://platform.arena.ai','https://api.arena.ai/']:
        assert provider_base_url('arena',base)=='https://api.arena.ai/v1'
        assert match_preset(base)=='arena'
    # Do not silently change custom gateways or another provider's endpoint.
    assert provider_base_url('arena','https://gateway.example/arena/v1/')=='https://gateway.example/arena/v1'
    assert provider_base_url('arena','https://platform.arena.ai/custom')=='https://platform.arena.ai/custom'
    assert provider_base_url('openai','https://platform.arena.ai/v1')=='https://platform.arena.ai/v1'


def test_arena_discovery_repairs_old_dashboard_address_with_bearer_auth(monkeypatch):
    real=httpx.AsyncClient
    calls=[]
    def handle(request):
        calls.append(str(request.url))
        assert str(request.url)=='https://api.arena.ai/v1/models'
        assert request.headers['authorization']=='Bearer test-arena-key'
        return httpx.Response(200,json={'data':[{'id':'coding-router-preview'}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(handle),**kwargs))
    for base in ['https://platform.arena.ai/v1','https://api.arena.ai','https://api.arena.ai/v1/']:
        data=asyncio.run(provider.fetch_models('arena',base,'test-arena-key'))
        assert data['valid'] and data['models']==[{'id':'coding-router-preview','free':False,'image':False}]
        assert 'test-arena-key' not in str(data)
    assert len(calls)==3


def test_arena_saved_endpoint_normalized_without_changing_key_or_database(monkeypatch):
    from app import db,hosted_settings,ai_hub
    from app.config import settings
    monkeypatch.setattr(settings,'provider_creds',{'arena':{'token':'test-stored-key','base_url':'https://platform.arena.ai/v1','model':'coding-router-preview'}})
    monkeypatch.setattr(settings,'active_provider','arena')
    for field in ['api_token','api_base_url','text_model']:
        monkeypatch.setattr(settings,field,getattr(settings,field))
    saved=[{'key':'base_arena','value':'https://platform.arena.ai/v1'},{'key':'model_arena','value':'coding-router-preview'}]
    monkeypatch.setattr(db,'query',lambda _:saved)
    def no_write(*args,**kwargs):raise AssertionError('Normalization must not rewrite saved config or keys')
    monkeypatch.setattr(db,'kv_set',no_write)
    hosted_settings.refresh()
    assert settings.api_base_url=='https://api.arena.ai/v1'
    assert ai_hub.config('arena')==('https://api.arena.ai/v1','test-stored-key','coding-router-preview')
    assert saved[0]['value']=='https://platform.arena.ai/v1'


def test_arena_inference_repairs_old_endpoint(monkeypatch):
    async def request(self,method,path,payload):
        assert self.base=='https://api.arena.ai/v1'
        assert path=='/chat/completions'
        assert self._headers()['Authorization']=='Bearer test-only'
        return {'choices':[{'message':{'content':'Hello'}}],'usage':{'prompt_tokens':2,'completion_tokens':1}}
    monkeypatch.setattr(provider.OpenAIProvider,'_request',request)
    transport=provider.OpenAIProvider(provider.ProviderConfig('arena','Arena','https://platform.arena.ai/v1','test-only','coding-router-preview'))
    assert asyncio.run(transport.chat([{'role':'user','content':'Hello'}])).text=='Hello'


def test_arena_errors_are_actionable_and_do_not_echo_upstream_secrets(monkeypatch):
    real=httpx.AsyncClient
    status=404
    def handle(request):return httpx.Response(status,text='sensitive upstream text test-only-key')
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(handle),**kwargs))
    data=asyncio.run(provider.fetch_models('arena','https://api.arena.ai/v1','test-only-key'))
    assert not data['valid'] and 'https://api.arena.ai/v1' in data['error'] and '404' in data['error']
    status=403
    data=asyncio.run(provider.fetch_models('arena','https://api.arena.ai/v1','test-only-key'))
    assert not data['valid'] and 'permissions' in data['error'] and '403' in data['error']
    assert 'sensitive upstream' not in str(data) and 'test-only-key' not in str(data)
