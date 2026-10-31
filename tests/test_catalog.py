"""Offline constraints for the only catalog accepted by the download service."""
import json
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]
class CatalogChecks(unittest.TestCase):
 def setUp(self):self.models=json.loads((ROOT/'packaging/model-catalog.json').read_text())
 def test_pinned_models_are_bounded_and_have_complete_integrity_metadata(self):
  self.assertEqual({m['id'] for m in self.models},{'qwen3.6-35b-a3b','bge-small-zh-v1.5','astrlink-guard','openai-privacy-filter'})
  self.assertEqual([m['id'] for m in self.models if m.get('recommended')],['qwen3.6-35b-a3b'])
  for model in self.models:
   self.assertRegex(model['id'],r'^(qwen(?:3(?:\.[56])?|2\.5)-[a-z0-9.-]+|gemma4-e4b|gpt-oss-20b|bge-small-zh-v1.5|astrlink-guard|openai-privacy-filter)$')
   self.assertRegex(model['repository'],r'^(mlx-community/[A-Za-z0-9_.-]+|BAAI/bge-small-zh-v1.5|QuantumNous/astrlink-guard|openai/privacy-filter)$')
   self.assertRegex(model['revision'],r'^[a-f0-9]{40}$')
   self.assertLess(sum(f['bytes'] for f in model['files']),24_000_000_000)
   names={f['name'] for f in model['files']}
   if model.get('purpose')=='privacy':
    self.assertTrue({'config.json','tokenizer.json'}<=names)
    self.assertTrue(any(n.endswith('.onnx') for n in names))
   else:
    self.assertTrue({'config.json','tokenizer_config.json'}<=names)
    self.assertTrue(any(n.endswith('.safetensors') for n in names))
   self.assertEqual(len(names),len(model['files']))
   for file in model['files']:
    self.assertRegex(file['name'],r'^[A-Za-z0-9_-][A-Za-z0-9_.-]*$')
    self.assertNotIn(Path(file['name']).suffix,{'.py','.so','.dylib','.sh'})
    self.assertRegex(file['sha256'],r'^[a-f0-9]{64}$')
    self.assertGreater(file['bytes'],0)
    if 'remotePath' in file:
     self.assertFalse(file['remotePath'].startswith('/'));self.assertNotIn('..',file['remotePath'].split('/'))
    if 'url' in file:
     self.assertTrue(file['url'].startswith('https://files.pythonhosted.org/packages/'));self.assertTrue(file['url'].endswith('cp313-cp313-macosx_14_0_arm64.whl'))
 def test_default_catalog_keeps_existing_verified_model_revision(self):
  default=next(m for m in self.models if m['id']=='qwen3.6-35b-a3b')
  old=json.loads((ROOT/'packaging/model-manifest.json').read_text())
  self.assertEqual(default['revision'],old['revision'])
  self.assertEqual(default['files'],old['files'])
