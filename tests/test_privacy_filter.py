import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from privacy_filter import preview


class RedactionTests(unittest.TestCase):
    def test_fictional_office_text_preserves_amounts_dates(self):
        value=preview({'text':'林晓 linxiao@example.com 13812345678 api_key=abc-xyz。预算1280元，截止2026-10-31。','policy':{'words':['林晓']}})
        for token in ('林晓 ','linxiao@example.com','13812345678','abc-xyz'):self.assertNotIn(token,value['text'])
        self.assertIn('预算1280元',value['text']);self.assertIn('2026-10-31',value['text'])
        self.assertEqual(value['count'],4);self.assertTrue(value['local_only']);self.assertFalse(value['saved'])
        self.assertNotIn('abc-xyz',json.dumps(value['findings']))
    def test_allowlist_is_whole_value_not_substring(self):
        result=preview({'text':'OPS@example.com xOPS@example.com','policy':{'allow':['ops@example.com']}})
        self.assertIn('OPS@example.com',result['text']);self.assertNotIn('xOPS@example.com',result['text']);self.assertEqual(result['count'],1)
    def test_custom_words_case_insensitive_and_repeat_same_token(self):
        result=preview({'text':'Nightjar NIGHTJAR nightjar','policy':{'words':['nightjar']}})
        self.assertEqual(result['count'],3);self.assertEqual(len({v['replacement'] for v in result['findings']}),1)
    def test_placeholders_are_scoped_to_each_preview(self):
        self.assertNotEqual(preview({'text':'a@example.com'})['text'],preview({'text':'a@example.com'})['text'])
    def test_overlap_masks_union_without_secret_tail(self):
        result=preview({'text':'api_key="ABCDEF GHIJK"','policy':{'words':['GHIJK']}})
        self.assertNotIn('ABCDEF',result['text']);self.assertNotIn('GHIJK',result['text']);self.assertEqual(result['count'],1)
    def test_custom_prefix_is_literal_and_requires_secret_switch(self):
        self.assertEqual(preview({'text':'oc_sk_abcdef','policy':{'prefixes':['oc_sk_']}})['count'],1)
        self.assertEqual(preview({'text':'oc_sk_abcdef','policy':{'prefixes':['oc_sk_'],'secrets':False}})['count'],0)
        self.assertEqual(preview({'text':'a+b秘密','policy':{'prefixes':['a+b']}})['count'],1)
    def test_multiline_private_key_fully_removed(self):
        text='start\n-----BEGIN PRIVATE KEY-----\nABCD\nEFGH\n-----END PRIVATE KEY-----\nend'
        result=preview({'text':text});self.assertEqual(result['count'],1);self.assertNotIn('ABCD',result['text']);self.assertIn('end',result['text'])
    def test_personal_toggle_preserves_email_and_phone(self):
        value='x@example.com 13812345678'
        self.assertEqual(preview({'text':value,'policy':{'personal':False}})['text'],value)
    def test_validated_cards_and_identity_not_generic_order_numbers(self):
        result=preview({'text':'卡号 4532015112830366，身份证11010519491231002X，订单202409301234567890。'})
        self.assertEqual(result['count'],2);self.assertIn('202409301234567890',result['text'])
    def test_unknown_names_not_claimed_as_detected(self):
        self.assertEqual(preview({'text':'联系张小明，到中关村大街。'})['count'],0)
    def test_unbounded_text_and_rules_rejected(self):
        for value in ({'text':'a'*24001},{'text':'a','policy':{'words':['x']*81}},{'text':'a','policy':{'prefixes':['x y']}}):
            with self.assertRaises(ValueError):preview(value)
    def test_cli_has_no_model_or_history_dependency(self):
        path=Path(__file__).resolve().parents[1]/'backend/privacy_filter.py'
        result=subprocess.run([sys.executable,'-I',str(path)],input=json.dumps({'text':'a@example.com'}),capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0);self.assertTrue(json.loads(result.stdout)['local_only']);self.assertEqual(result.stderr,'')


if __name__=='__main__':unittest.main()
