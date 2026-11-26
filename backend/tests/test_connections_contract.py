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
