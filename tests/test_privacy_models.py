import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'backend'))
import privacy_filter as pf
import privacy_models as pm

class PrivacyModelsTests(unittest.TestCase):
    def detect(self,text,id):
        return [(0,len(text),'address')],{'id':id,'name':'测试'}
    def test_office_values_protected(self):
        t='张伟预算3600元，截止2026-10-31。'
        r=pf.preview({'text':t,'detector':'astrlink-guard'},detector=self.detect)
        self.assertIn('预算3600元',r['text']);self.assertIn('2026-10-31',r['text']);self.assertNotIn('张伟',r['text'])
    def test_secret_priority_even_numeric_date(self):
        t='密码=2026-10-31，password=1280元'
        r=pf.preview({'text':t,'detector':'astrlink-guard'},detector=self.detect)
        self.assertNotIn('2026-10-31',r['text']);self.assertNotIn('1280元',r['text'])
    def test_categories_and_allowlist(self):
        t='林晓';d=lambda t,id:([(0,2,'person')],{'id':id,'name':'测试'})
        for policy in [{'categories':{'person':False}},{'allow':['林晓']}]:
            self.assertEqual(pf.preview({'text':t,'detector':'astrlink-guard','policy':policy},detector=d)['text'],t)
    def test_dates_opt_in(self):
        t='1992年7月8日';d=lambda t,id:([(0,len(t),'date')],{'id':id,'name':'测试'})
        self.assertEqual(pf.preview({'text':t,'detector':'astrlink-guard'},detector=d)['text'],t)
        self.assertNotEqual(pf.preview({'text':t,'detector':'astrlink-guard','policy':{'categories':{'date':True}}},detector=d)['text'],t)
    def test_fail_closed(self):
        with self.assertRaises(ValueError):pf.preview({'text':'林晓','detector':'unknown'})
        with self.assertRaises(RuntimeError):pf.preview({'text':'林晓','detector':'astrlink-guard'},detector=lambda *a:(_ for _ in ()).throw(RuntimeError()))
    def test_unknown_category_rejected(self):
        with self.assertRaises(ValueError):pf.preview({'text':'文字','policy':{'categories':{'invalid':True}}})
    def test_merge_overlapping_rule_and_model(self):
        t='林晓lin@example.com';d=lambda t,id:([(0,9,'person')],{'id':id,'name':'测试'})
        r=pf.preview({'text':t,'detector':'astrlink-guard'},detector=d)
        self.assertEqual(r['count'],1);self.assertNotIn('example.com',r['text'])
    def test_invalid_model_positions(self):
        with self.assertRaises(ValueError):pf.preview({'text':'abc','detector':'astrlink-guard'},detector=lambda *a:([(-1,2,'person')],{'name':'x'}))
    def test_component_catalog(self):
        cat=pm.catalog();self.assertEqual(set(cat),pm.IDS)
        for m in cat.values():
            self.assertEqual(len(m['revision']),40)
            self.assertEqual(len([f for f in m['files'] if f['name'].endswith('.whl')]),1)
    def test_missing_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):pm.verify_component('astrlink-guard',pathlib.Path(tmp).resolve())
    def test_tamper_and_symlink_rejected(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp).resolve();folder=root/'Installed/astrlink-guard';folder.mkdir(parents=True)
            (folder/'guiyu-install.json').write_text(json.dumps({'revision':'a'*40}))
            (folder/'config.json').write_bytes(b'bad')
            item={'revision':'a'*40,'files':[{'name':'config.json','bytes':3,'sha256':hashlib.sha256(b'yes').hexdigest()}]}
            with patch.object(pm,'catalog',return_value={'astrlink-guard':item}):
                with self.assertRaises(ValueError):pm.verify_component('astrlink-guard',root)
                (folder/'config.json').unlink();outside=root/'outside';outside.write_bytes(b'yes');(folder/'config.json').symlink_to(outside)
                with self.assertRaises(ValueError):pm.verify_component('astrlink-guard',root)

    def test_categories_independent_of_contacts(self):
        t='身份证11010519491231002X，邮箱a@example.com'
        r=pf.preview({'text':t,'policy':{'personal':False,'categories':{'identity':True}}})
        self.assertNotIn('11010519491231002X',r['text']);self.assertIn('a@example.com',r['text'])

    def test_viterbi_constraints(self):
        import numpy as np
        labels={'0':'O','1':'B-person','2':'I-person','3':'E-person','4':'S-person'}
        x=np.array([[0,3,20,0,0],[0,0,0,5,0]],dtype=np.float32)
        b={key:0 for key in ['transition_bias_'+v for v in ['background_stay','background_to_start','end_to_background','end_to_start','inside_to_continue','inside_to_end']]}
        self.assertEqual(pm.viterbi(x,labels,b),[1,3])
    def test_offset_consistency(self):
        labels={'0':'B-private_person','1':'I-private_person'}
        spans=pm.token_spans('林晓，张伟',[(0,1),(1,2),(3,4),(4,5)],[0,1,1,1],[.99]*4,labels)
        self.assertEqual([(s[0],s[1]) for s in spans],[(0,2),(3,5)])

if __name__=='__main__':unittest.main()
