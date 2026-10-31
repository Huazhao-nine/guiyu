from contextlib import redirect_stdout
from datetime import date
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import worker as core
import agent_control as control
import fact_guard
from office_agent import OfficeAgent,TOOLS
from general_assistant import GeneralAssistant


class ScriptModel:
    info={'name':'测试本地模型','key':'test'}
    def __init__(self):self.actions=[];self.calls=[]
    def generate(self,system,user,**kw):
        self.calls.append((system,user))
        if system.startswith('你是归屿的本地交付核对器'):return '{"state":"complete"}',{}
        return self.actions.pop(0),{}


class ComposedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.model=ScriptModel()
        self.agent=core.Agent(self.model,self.root/'data');self.office=OfficeAgent(self.agent,core)
        self.path=self.root/'活动方案.txt';self.path.write_text('活动预算3600元。场地1200元，物料35元买24份，交通480元。活动日期2026-11-06，提前7天确认。')
        self.doc={'id':'S1','name':self.path.name,'path':str(self.path),'text':self.path.read_text()}
        self.context={'docs':[self.doc],'scope_docs':[self.doc],'table':None,'base_table':None,'query':{},'results':[]}
        self.plan={'id':'plan','prompt':'根据活动方案计算已花和剩余预算，核对提前7天日期，再写说明。','clock':{'today':'2026-10-28'},'paths':[str(self.path)]}
    def tearDown(self):self.temp.cleanup()
    def tool(self,kind,instruction):
        with redirect_stdout(io.StringIO()):return self.office.tool({'tool':kind,'instruction':instruction},self.context,self.plan,'step-result')
    def test_draft_event_correlates_originating_request_not_plan_id(self):
        events=[]
        with patch.object(core,'emit',side_effect=lambda event,**kw:events.append((event,kw))):
            plan=self.office.draft({'id':'origin-request','prompt':'汇总资料','paths':[str(self.path)],'kind':'summary','adaptive':False})
        event=next(kw for name,kw in events if name=='plan')
        self.assertEqual(event['request_id'],'origin-request')
        self.assertNotEqual(plan['id'],'origin-request')

    def test_source_values_reach_calculator_and_writing_fact_guard(self):
        self.model.actions=[json.dumps({'action':'call','tool':'calculate','arguments':{'expression':'1200+35*24+480'}}),'{"action":"answer","text":"已核对费用。"}']
        result=self.tool('calculate','计算活动方案中的已花费用总额。')
        self.assertIn('2520',result['text']);self.assertEqual(result['calculation_unit'],'元');self.assertEqual(result['artifacts'],[])
        self.assertIn('verified_source_facts',self.model.calls[0][1]);self.assertNotIn(str(self.path),self.model.calls[0][1])
        self.assertEqual(fact_guard.check_writing('已花2520元。','写费用说明',[self.doc],results=[('calculate',result)])['issues'],[])
        self.assertEqual(fact_guard.check_writing('物料费用840元。','写费用说明',[self.doc],results=[('calculate',result)])['issues'],[])
        self.assertEqual(fact_guard.check_writing('根据活动方案，物料费用840元。','写费用说明',[self.doc],results=[('calculate',result)])['issues'],[])
        self.assertTrue(fact_guard.check_writing('已花9999元。','写费用说明',[self.doc],results=[('calculate',result)])['issues'])
    def test_date_uses_document_and_frozen_plan_clock(self):
        self.model.actions=[json.dumps({'action':'call','tool':'calendar','arguments':{'operation':'date_shift','date':'2026-11-06','days':-7}}),'{"action":"answer","text":"已核对提前确认日期。"}']
        result=self.tool('calendar','活动日期提前7天确认，应是哪一天？')
        self.assertIn('2026-10-30',result['text']);self.assertEqual(result['clock']['today'],'2026-10-28')
    def test_unfiltered_cost_table_does_not_erase_date_clauses(self):
        self.context['table']={'columns':['金额（元）'],'rows':[['1200']]}
        self.model.actions=[json.dumps({'action':'call','tool':'calendar','arguments':{'operation':'date_shift','date':'2026-11-06','days':-7}}),'{"action":"answer","text":"已核对日期。"}']
        result=self.tool('calendar','核对活动日期提前7天的日期。')
        self.assertIn('2026-10-30',result['text'])
    def test_filtered_out_values_cannot_be_calculation_operands(self):
        self.context['table']={'columns':['金额（元）'],'rows':[['1200']]}
        self.model.actions=[json.dumps({'action':'call','tool':'calculate','arguments':{'expression':'480+1200'}})]*6
        with self.assertRaises(control.OutputCheckError):self.tool('calculate','计算本轮匹配数据的总额。')
    def test_other_tool_cannot_be_called_within_date_step(self):
        self.model.actions=[json.dumps({'action':'call','tool':'calculate','arguments':{'expression':'35*24'}})]*6
        with self.assertRaises(control.OutputCheckError):self.tool('calendar','核对活动日期。')
    def test_recipe_requires_computation_before_writing(self):
        good={'title':'活动说明','steps':[{'tool':'calculate','instruction':'核对金额'},{'tool':'calendar','instruction':'核对日期'},{'tool':'write','instruction':'写说明'}]}
        self.assertEqual(control.checked_recipe(good,TOOLS,[],False),good)
        with self.assertRaises(ValueError):control.checked_recipe({'title':'坏顺序','steps':list(reversed(good['steps']))},TOOLS,[],False)
    def test_delivery_can_request_quoted_missing_calendar_but_not_files(self):
        p={'prompt':'计算费用并核对提前7天日期','steps':[]}
        value={'action':'complete','tool':'calendar','quote':'核对提前7天日期','instruction':'补核对日期'}
        self.assertEqual(control.checked_delivery(value,p),value)
        with self.assertRaises(ValueError):control.checked_delivery(dict(value,tool='shell'),p)
    def test_request_cannot_inject_grounded_facts(self):
        self.model.actions=[json.dumps({'action':'call','tool':'calculate','arguments':{'expression':'999+1'}})]*6
        with redirect_stdout(io.StringIO()):r=GeneralAssistant(self.agent,core).run({'prompt':'计算费用','grounded_facts':'999元'},now=date(2026,10,28))
        self.assertFalse(any(c['state']=='completed' for c in r['tool_calls']))
    def test_tool_can_recover_from_asking_for_a_total_it_just_computed(self):
        self.model.actions=[json.dumps({'action':'call','tool':'calculate','arguments':{'expression':'1200+35*24+480'}}),'{"action":"ask","question":"请提供费用总额"}',json.dumps({'action':'call','tool':'calculate','arguments':{'expression':'3600-2520'}}),'{"action":"answer","text":"已核对费用和预算。"}']
        result=self.tool('calculate','计算全部费用和剩余预算。')
        self.assertIn('2520',result['text']);self.assertIn('1080',result['text']);self.assertEqual(result['completion_check']['state'],'passed')
    def test_confirmation_date_cannot_be_replaced_by_distance_to_today(self):
        self.model.actions=[json.dumps({'action':'call','tool':'calendar','arguments':{'operation':'date_difference','start':'2026-10-28','end':'2026-11-06'}}),json.dumps({'action':'call','tool':'calendar','arguments':{'operation':'date_shift','date':'2026-11-06','days':-7}}),'{"action":"answer","text":"已核对确认日期。"}']
        result=self.tool('calendar','核对活动日期提前7天的确认日期。')
        self.assertEqual(result['tool_calls'][0]['state'],'failed');self.assertIn('2026-10-30',result['text'])
    def test_advance_direction_and_day_count_cannot_use_an_unrelated_known_number(self):
        self.model.actions=[json.dumps({'action':'call','tool':'calendar','arguments':{'operation':'date_shift','date':'2026-11-06','days':-35}}),json.dumps({'action':'call','tool':'calendar','arguments':{'operation':'date_shift','date':'2026-11-06','days':-7}}),'{"action":"answer","text":"已核对日期。"}']
        result=self.tool('calendar','核对活动日期提前7天的确认日期。')
        self.assertEqual(result['tool_calls'][0]['state'],'failed');self.assertIn('2026-10-30',result['text'])
    def test_feedback_does_not_duplicate_an_already_pending_date_step(self):
        first={'id':'step-1','tool':'calculate','state':'completed','enabled':True,'instruction':'核对费用'}
        pending={'id':'step-2','tool':'calendar','state':'pending','enabled':True,'instruction':'核对确认日期'}
        self.plan['steps']=[first,pending]
        with patch.object(control,'review_next',return_value={'action':'insert','tool':'calendar','instruction':'补充确认日期','reason':'写作需要日期'}):
            with redirect_stdout(io.StringIO()):self.office.adapt_after_result(self.plan,first,{'text':'已核对费用'},self.context)
        self.assertEqual(self.plan['steps'],[first,pending])
    def test_missing_calculation_reopens_dependent_draft_after_new_tool(self):
        step={'id':'step-1','tool':'write','state':'completed','enabled':True,'instruction':'写说明','attempts':1,'output':'旧稿'}
        self.plan.update(steps=[step],adaptive=True,paths=[str(self.path.resolve())],snapshot={str(self.path.resolve()):core.digest(self.path)})
        old={'text':'旧稿','artifacts':[]};results={'step-1':old};self.context['results']=[('write',old)]
        with patch.object(control,'review_delivery',return_value={'action':'complete','tool':'calculate','quote':'剩余预算','instruction':'核对剩余预算'}):
            with redirect_stdout(io.StringIO()):changed=self.office.complete_delivery(self.plan,self.context,results)
        self.assertTrue(changed);self.assertEqual([s['tool'] for s in self.plan['steps']],['calculate','write'])
        self.assertEqual(step['state'],'pending');self.assertNotIn('step-1',results);self.assertFalse(self.context['results'])


if __name__=='__main__':unittest.main()
