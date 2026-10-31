"""Pinned bootstrap reuses verified weights; no old default or implicit network."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('prepare_primary',Path(__file__).resolve().parents[1]/'scripts/prepare_model.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class PrimaryPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.storage=self.root/'models';(self.root/'packaging').mkdir()
        self.payload=b'fictional-weight'
        self.manifest={'id':'primary','repository':'example/pinned','revision':'a'*40,
                       'files':[{'name':'model.safetensors','bytes':len(self.payload),'sha256':hashlib.sha256(self.payload).hexdigest()}]}
        (self.root/'packaging/model-manifest.json').write_text(json.dumps(self.manifest))

    def no_download(self,**kwargs):self.fail('Verified existing weights must not download or copy.')

    def test_verified_research_model_is_reused_without_copy(self):
        model=self.storage/'Research/primary';model.mkdir(parents=True)
        (model/'model.safetensors').write_bytes(self.payload)
        result,reused=module.prepare(self.root,self.storage,self.no_download)
        self.assertEqual(result,model);self.assertTrue(reused)
        self.assertFalse((self.storage/'Installed/primary').exists())
        self.assertEqual(json.loads((model/'guiyu-install.json').read_text())['revision'],'a'*40)

    def test_same_size_corrupt_file_is_not_marked_ready(self):
        model=self.storage/'Installed/primary';model.mkdir(parents=True)
        (model/'model.safetensors').write_bytes(b'x'*len(self.payload))
        with self.assertRaisesRegex(ValueError,'校验未通过'):module.prepare(self.root,self.storage,self.no_download)
        self.assertFalse((model/'guiyu-install.json').exists())

    def test_new_download_is_only_pinned_primary(self):
        def download(**kwargs):
            self.assertEqual(kwargs['revision'],'a'*40);self.assertFalse(kwargs['token'])
            self.assertEqual(kwargs['allow_patterns'],['model.safetensors'])
            (kwargs['local_dir']/'model.safetensors').write_bytes(self.payload)
        result,reused=module.prepare(self.root,self.storage,download)
        self.assertEqual(result,self.storage/'Installed/primary');self.assertFalse(reused)

    def test_symlink_weights_are_rejected(self):
        model=self.storage/'Installed/primary';model.mkdir(parents=True)
        original=self.root/'original';original.write_bytes(self.payload)
        (model/'model.safetensors').symlink_to(original)
        self.assertFalse(module.verify(model,self.manifest))
        with self.assertRaises(ValueError):module.prepare(self.root,self.storage,self.no_download)


if __name__=='__main__':unittest.main()
