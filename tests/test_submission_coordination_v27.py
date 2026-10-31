"""Workflow handoff checks independent from the submitted demonstration data."""
import hashlib,io,json,sys,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import worker as core
import agent_control as control
import fact_guard
from office_agent import OfficeAgent,plain_office_math
from general_assistant import GeneralAssistant

class Model:
    info={'name':'local unit','key':'unit'}
    def __init__(self,actions):self.actions=list(actions);self.calls=[]
    def generate(self,system,user,**kw):
        self.calls.append((system,user))
        if system.startswith('你是归屿的本地交付核对器'):return '{"state":"complete"}',{}
        return json.dumps(self.actions.pop(0),ensure_ascii=False),{}

class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.model=Model([]);self.office=OfficeAgent(core.Agent(self.model,self.root/'data'),core)
        path=self.root/'变更.txt';path.write_text('版本2031-03-02。预算2700元，资料单价37元，共22份，交通250元。活动日期2031-05-16，提前3天确认。')
        self.docs=[{'id':'S1','name':path.name,'path':str(path),'text':path.read_text()}]
        self.plan={'id':'plan','paths':[str(path)],'prompt':'结合最新变更整理费用和确认日期说明。','clock':{'today':'2026-10-31'}}
        self.context={'docs':self.docs,'scope_docs':self.docs,'table':None,'query':{},'results':[]}
    def test_extraction_keeps_same_document_paragraphs_without_claiming_complete_rows(self):
        extracted={'columns':['单项金额（元）'],'rows':[['250']],'sources':[{'id':'S1'}],'partial':False,'skipped':[]}
        with patch.object(self.office.agent,'run',return_value=deepcopy(extracted)),redirect_stdout(io.StringIO()):
            result=self.office.tool({'tool':'table','instruction':'提取费用'},self.context,self.plan,'extract')
        table={k:result[k] for k in ('columns','rows')};results=[('table',result)]
        docs,_=fact_guard.current_evidence(self.docs,table,results)
        self.assertTrue(any('37元' in d['text'] and '2031-05-16' in d['text'] for d in docs))
        filtered=deepcopy(table);filtered['rows']=[]
        self.assertFalse(fact_guard.extraction_scope_documents(self.docs,filtered,results))
        changed=deepcopy(self.docs);changed[0]['text']='另一版本，999元'
        self.assertFalse(fact_guard.extraction_scope_documents(changed,table,results))
    def test_extraction_scope_not_added_to_a_filtered_or_partial_result(self):
        result={'columns':['金额（元）'],'rows':[['250']],'partial':False}
        for query,partial in [({'filters':[{'column':'金额（元）','operator':'gt','value':'100'}]},False),({},True)]:
            with self.subTest(query=query,partial=partial):
                self.context['query']=query
                with patch.object(self.office.agent,'run',return_value=dict(result,partial=partial)),redirect_stdout(io.StringIO()):
                    r=self.office.tool({'tool':'table','instruction':'提取费用'},self.context,self.plan,'extract')
                self.assertNotIn('unfiltered_document_scope',r)
    def test_planner_hint_and_step_text_cannot_authorize_invented_operands(self):
        m=Model([{'action':'call','tool':'calculate','arguments':{'expression':'999+17'}},
                 {'action':'call','tool':'calculate','arguments':{'expression':'17+9'}},
                 {'action':'answer','text':'已核对。'}])
        a=core.Agent(m,self.root/'hints')
        with redirect_stdout(io.StringIO()):
            r=GeneralAssistant(a,core).run({'prompt':'按999修正费用。'},grounded_facts='用户要求核对总额。原文费用17元和9元。',planner_hint='999+17',allowed_tools={'calculate'})
        self.assertEqual([c['state'] for c in r['tool_calls']],['failed','completed']);self.assertIn('26',r['text'])
        self.assertIn('planner_hint',json.loads(m.calls[0][1]));self.assertEqual(r['completion_check']['state'],'passed')
    def test_calendar_does_not_replace_source_date_with_machine_clock(self):
        self.model.actions=[{'action':'call','tool':'calendar','arguments':{'operation':'date_shift','date':'2026-10-31','days':-3}},
                            {'action':'call','tool':'calendar','arguments':{'operation':'date_shift','date':'2031-05-16','days':-3}},
                            {'action':'answer','text':'已核对。'}]
        with redirect_stdout(io.StringIO()):r=self.office.tool({'tool':'calendar','instruction':'核对活动提前3天的确认日期。'},self.context,self.plan,'calendar')
        self.assertEqual(r['tool_calls'][0]['state'],'failed');self.assertIn('2031-05-13',r['text'])
    def test_natural_day_clause_is_not_replaced_by_repair_result_wording(self):
        self.model.actions=[{'action':'call','tool':'calendar','arguments':{'operation':'date_shift','date':'2032-11-18','days':-6}},
                            {'action':'answer','text':'已核对。'}]
        with redirect_stdout(io.StringIO()):
            r=GeneralAssistant(self.office.agent,core).run({'prompt':'核对最晚确认日期。\n上次输出未通过检查：2032-11-18移动-6天后是2032-11-12。'},grounded_facts='活动2032-11-18，需提前六个自然日确认。',allowed_tools={'calendar'},allow_clock_dates=False)
        self.assertEqual(r['completion_check']['state'],'passed');self.assertIn('2032-11-12',r['text'])
        payload=json.loads(self.model.calls[0][1]);self.assertEqual(payload['current_request'],'核对最晚确认日期。');self.assertIn('previous_error',payload)
    def test_wrong_natural_day_shift_remains_a_failed_call(self):
        self.model.actions=[{'action':'call','tool':'calendar','arguments':{'operation':'date_shift','date':'2032-11-18','days':6}},
                            {'action':'call','tool':'calendar','arguments':{'operation':'date_shift','date':'2032-11-18','days':-6}},
                            {'action':'answer','text':'已核对。'}]
        with redirect_stdout(io.StringIO()):
            r=GeneralAssistant(self.office.agent,core).run({'prompt':'核对确认日期。'},grounded_facts='活动2032-11-18，提前6个自然日确认。',allowed_tools={'calendar'},allow_clock_dates=False)
        self.assertEqual([c['state'] for c in r['tool_calls']],['failed','completed'])
    def test_office_math_delimiters_do_not_change_actual_dollar_amounts(self):
        self.assertEqual(plain_office_math(r'小计$8 \times 17 = 136$元。'), '小计8 × 17 = 136元。')
        self.assertEqual(plain_office_math(r'$$2300-136=2164 \text{元}$$'), '2300-136=2164 元')
        for text in ('$5 + $10','费用$120，预算$300',r'$未知=2$'):
            self.assertEqual(plain_office_math(text),text)
    def test_weekday_agrees_with_its_own_adjacent_date(self):
        self.assertFalse(fact_guard.calendar_and_refund_issues('交接2033年6月2日（星期四），申请2033-06-05（周日）。'))
        self.assertTrue(fact_guard.calendar_and_refund_issues('交接2033-06-05（星期四）。'))
        self.assertTrue(fact_guard.calendar_and_refund_issues('日期2033-02-30（周三）。'))
    def test_refundable_deposit_does_not_authorize_a_new_event_condition(self):
        source='培训费用1200元，可退押金150元，尚未支付。活动结束后整理记录。'
        self.assertTrue(fact_guard.calendar_and_refund_issues('押金仅在培训结束后退还。',source))
        self.assertFalse(fact_guard.calendar_and_refund_issues('押金可退，退还时间待确认。',source))
        self.assertFalse(fact_guard.calendar_and_refund_issues('请确认是否在培训结束后退还押金。',source))
        self.assertFalse(fact_guard.calendar_and_refund_issues('押金在培训结束后退还。',source+'押金在培训结束后退还。'))
    def test_pending_calculation_keeps_feedback_without_duplicate_step(self):
        first={'id':'step-1','tool':'answer','state':'completed','enabled':True,'instruction':'读变更'}
        pending={'id':'step-2','tool':'calculate','state':'pending','enabled':True,'instruction':'核对费用'}
        self.plan['steps']=[first,pending]
        feedback={'action':'insert','tool':'calculate','instruction':'资料单价37元，数量22，交通250元，按最新变更核算。','reason':'已有新版本'}
        with patch.object(control,'review_next',return_value=feedback),redirect_stdout(io.StringIO()):self.office.adapt_after_result(self.plan,first,{'text':'变更已找到'},self.context)
        self.assertEqual(len(self.plan['steps']),2);self.assertEqual(pending['planning_hint'],feedback['instruction'])
    def test_pending_extraction_is_not_inserted_twice(self):
        first={'id':'step-1','tool':'answer','state':'completed','enabled':True,'instruction':'读方案'}
        pending={'id':'step-2','tool':'table','state':'pending','enabled':True,'instruction':'提取费用'};self.plan['steps']=[first,pending]
        feedback={'action':'insert','tool':'table','instruction':'保留版本与费用出处。','reason':'需要结构化资料'}
        with patch.object(control,'review_next',return_value=feedback),redirect_stdout(io.StringIO()):self.office.adapt_after_result(self.plan,first,{'text':'已找到'},self.context)
        self.assertEqual(len(self.plan['steps']),2)

if __name__=='__main__':unittest.main()
