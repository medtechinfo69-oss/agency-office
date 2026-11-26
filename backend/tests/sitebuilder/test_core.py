import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unittest.mock import patch
from app import sitebuilder as main
from app.sitebuilder import repair_json, validate_files, render_site, qa, ALLOWED
class CoreTests(unittest.TestCase):
    def test_json_repair(self): self.assertEqual(repair_json('```json\n{"answer": 1,}\n```'),{'answer':1})
    def test_invalid_json(self):
        with self.assertRaises(ValueError): repair_json('not json')
    def test_file_traversal(self):
        with self.assertRaises(ValueError): validate_files({'../.env':'steal'})
    def test_block_network(self):
        with self.assertRaises(ValueError): validate_files({'script.js':'fetch("https://example.com")'})
    def test_block_remote_script(self):
        with self.assertRaises(ValueError): validate_files({'index.html':'<script src="https://bad.example/x.js"></script>'})
    def test_oversize(self):
        with self.assertRaises(ValueError): validate_files({'index.html':'x'*250001})
    def test_router_uses_shared_global_provider_chain(self):
        from app.provider import ProviderConfig
        configured=[ProviderConfig(key='ollama',label='Local',base_url='http://localhost:11434/v1',token='server-only',model='small'), ProviderConfig(key='openrouter',label='Cloud',base_url='https://openrouter.ai/api/v1',token='server-only',model='next:free')]
        with patch('app.provider.configured_configs',return_value=configured):
            self.assertEqual(main.candidates(), [('ollama','small'),('openrouter','next:free')])
            self.assertNotIn('server-only',repr(main.candidates()))
    def test_static_qa_requires_parsed_html5_structure(self):
        result=qa({'index.html':'<!-- <!doctype html><html><head><body><main> -->'})
        self.assertFalse(next(c['passed'] for c in result['checks'] if c['name']=='HTML5 document structure'))
    def test_builder(self):
        f=render_site({'business':'<script>x</script>','headline':'Hello','services':[],'faq':[]})
        self.assertEqual(set(f),ALLOWED);validate_files(f);self.assertNotIn('<script>x</script>',f['index.html']);self.assertTrue(all(c['passed'] for c in qa(f)['checks']))
if __name__=='__main__': unittest.main()
