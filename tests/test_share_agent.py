import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import io
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import worker as core
from office_agent import OfficeAgent
from share_agent import wants_share,run_share,_numbers
from privacy_filter import preview

class Model:
    info={'key':'test','name':'test'}
    def __init__(self,*outputs):self.outputs=list(outputs);self.calls=[]
    def generate(self,system,user,**kw):self.calls.append((system,user));return self.outputs.pop(0),{}

def scanner(text,spec):
    def detector(t,id):
        spans=[]
        for word,kind in [('张伟','person'),('北京市海淀区中关村大街27号','address')]:
            start=0
            while (i:=t.find(word,start))>=0:spans.append((i,i+len(word),kind));start=i+len(word)
        return spans,{'name':'测试组件','id':id}
    return preview(dict(spec,text=text),detector=detector)

class ShareAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.file=self.root/'张伟的纪要.md';self.raw='联系人张伟，邮箱zhangwei@example.com。地址北京市海淀区中关村大街27号。预算1280元，日期2026-10-31。尚未付款。密码=2026-10-31'
        self.file.write_text(self.raw);self.docs=[{'id':'S1','path':str(self.file),'name':self.file.name,'text':self.raw}];self.spec={'detector':'astrlink-guard'}
    def tearDown(self):self.tmp.cleanup()
    def run_share(self,goal='整理成可分享版本',model=None,scan=scanner):
        with redirect_stdout(io.StringIO()):return run_share(self.docs,goal,self.spec,model or Model(),core,scan=scan)
    def test_full_copy_and_no_raw_filename(self):
        r=self.run_share();self.assertEqual(r['share_check']['source_count'],1)
        for raw in ['张伟','zhangwei@example.com','北京市海淀区中关村大街27号']:self.assertNotIn(raw,r['text'])
        for keep in ['1280元','2026-10-31','尚未付款']:self.assertIn(keep,r['text'])
        self.assertEqual(self.file.read_text(),self.raw)
    def test_fail_closed_scan(self):
        with self.assertRaises(RuntimeError):self.run_share(scan=lambda *a:(_ for _ in ()).throw(RuntimeError('fake')))
    def test_complete_read_not_truncated_retrieval_preview(self):
        self.docs[0]['text']='很短的检索片段';self.assertIn('1280元',self.run_share()['text'])
    def test_long_source_rejects_instead_of_partial(self):
        self.file.write_text('完整资料'*6000)
        with self.assertRaisesRegex(ValueError,'20,000'):self.run_share()
    def test_unread_sheet_tail_rejected(self):
        self.file.write_text('记录\n[其余行未读取]')
        with self.assertRaisesRegex(ValueError,'完整读取'):self.run_share()
    def test_editor_receives_only_redacted_sources(self):
        m=Model('预算1280元，日期2026-10-31。尚未付款。','{"complete":true}')
        r=self.run_share('整理成可分享版本，写一份说明',m)
        for _,data in m.calls:
            for value in ['张伟','zhangwei@example.com','北京市海淀区中关村大街27号']:self.assertNotIn(value,data)
        self.assertEqual(r['share_check']['writing'],'edited')
    def test_editor_failure_no_faithful_copy_as_false_success(self):
        m=Model('预算9999元。','预算8888元。')
        with self.assertRaisesRegex(ValueError,'未通过完整性'):self.run_share('写一份可分享说明',m)
    def test_residual_scan_repairs_before_export(self):
        calls=[]
        def fake(text,spec):
            calls.append(text)
            if len(calls)==2:return dict(text='已修复正文',count=1,counts={'邮箱':1},detector='test',findings=[])
            return dict(text=text,count=0,counts={},detector='test',findings=[])
        self.assertEqual(self.run_share(scan=fake)['text'],'已修复正文');self.assertEqual(len(calls),3)
    def test_unstable_scan_blocks(self):
        def unstable(t,s):return dict(text=t+'⟪新标记⟫',count=1,counts={'姓名':1},detector='test',findings=[])
        with self.assertRaisesRegex(ValueError,'复查仍发现'):self.run_share(scan=unstable)
    def test_numbers_next_to_chinese_and_placeholder(self):
        self.assertEqual(_numbers('预算1280元，日期2026-10-31，⟪姓名_a123b456_1⟫'),{'1280':1,'2026-10-31':1})
    def test_intent_concept_stays_chat(self):
        self.assertTrue(wants_share('把这份资料整理成可分享版本'))
        self.assertFalse(wants_share('什么是隐私脱敏'))
    def test_office_contract_export_redacted_only(self):
        m=Model();office=OfficeAgent(core.Agent(m,self.root/'data'),core)
        with redirect_stdout(io.StringIO()):
            plan=office.draft({'id':'request','prompt':'把这份资料整理成可分享版本','paths':[str(self.file)],'adaptive':True})
            self.assertEqual([s['tool'] for s in plan['steps']],['share'])
            with patch('share_agent.scan_local',scanner),patch('share_agent.run_share',wraps=lambda *a,**kw:run_share(*a,**kw,scan=scanner)):
                r=office.execute({'plan_id':plan['id'],'paths':plan['paths']})
        self.assertEqual(r['plan']['state'],'completed');self.assertEqual(r['share_check']['state'],'passed')
        self.assertEqual(len(r['artifacts']),3);self.assertNotIn('张伟',r['text']);self.assertIsNone(r['transaction'])
        from docx import Document
        for a in r['artifacts']:
            body='\n'.join(p.text for p in Document(a['path']).paragraphs) if a['type']=='docx' else Path(a['path']).read_text()
            self.assertNotIn('张伟',body);self.assertNotIn('zhangwei@example.com',body);self.assertIn('1280',body)
    def test_whole_workspace_request_cannot_use_partial_candidates(self):
        from share_agent import share_plan
        with self.assertRaisesRegex(ValueError,'完整处理范围'):
            share_plan({'prompt':'把全部资料整理成可分享版本','retrieval':{'matched_documents':3}},[self.file],core,Model())
    def test_unreadable_source_never_exports_partial_copy(self):
        bad=self.root/'损坏.docx';bad.write_bytes(b'not a document')
        office=OfficeAgent(core.Agent(Model(),self.root/'data'),core)
        with redirect_stdout(io.StringIO()):plan=office.draft({'prompt':'把这些资料整理成可分享版本','paths':[str(self.file),str(bad)]})
        with self.assertRaisesRegex(ValueError,'没有完整读取'):office.execute({'plan_id':plan['id'],'paths':plan['paths']})
        self.assertFalse(list((self.root/'data').glob('Outputs/**/*.docx')))
    def test_cannot_disable_or_mix_share_contract(self):
        office=OfficeAgent(core.Agent(Model(),self.root/'data'),core)
        with redirect_stdout(io.StringIO()):plan=office.draft({'prompt':'脱敏这份资料','paths':[str(self.file)]})
        with self.assertRaises(ValueError):office.execute({'plan_id':plan['id'],'paths':plan['paths'],'steps':[{'id':'step-1','enabled':False}]})
        with self.assertRaises(ValueError):office._validate_sequence([{'tool':'share'},{'tool':'write'}],[str(self.file)])
if __name__=='__main__':unittest.main()
