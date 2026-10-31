import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import worker as core
import agent_control as control
from office_agent import OfficeAgent, TOOLS


class LocalDouble:
    def __init__(self):self.recipe=None;self.decisions=[];self.responses=[];self.review_calls=0;self.draft_checks=[];self.deliveries=[]
    def generate(self,system,user,**kwargs):
        if '本地交付核对器' in system:
            value=self.deliveries.pop(0) if self.deliveries else {'action':'accept'}
            return json.dumps(value,ensure_ascii=False),{}
        if '本地任务规划器' in system:
            if self.recipe is None:raise ValueError('fixture planner unavailable')
            return json.dumps(self.recipe,ensure_ascii=False),{}
        if '执行检查器' in system:
            self.review_calls+=1
            return json.dumps(self.decisions.pop(0) if self.decisions else {'action':'continue'},ensure_ascii=False),{}
        if '文稿复核器' in system:
            check=self.draft_checks.pop(0) if self.draft_checks else {'action':'accept'}
            if check.get('action')=='revise' and 'quote' not in check:check['quote']=json.loads(user)['草稿'][:500]
            return json.dumps(check,ensure_ascii=False),{}
        if '文稿修订器' in system:
            value=self.responses.pop(0) if self.responses else ('依据当前原文写成说明。','stop')
            if isinstance(value,Exception):raise value
            draft=json.loads(user)['待修订草稿']
            return json.dumps({'edits':[{'old':draft,'new':value[0]}]},ensure_ascii=False),{'finish_reason':value[1]}
        value=self.responses.pop(0) if self.responses else ('依据当前资料写成说明。【S1】','stop')
        if isinstance(value,Exception):raise value
        text,finish=value
        return text,{'finish_reason':finish}


class LocalAgent:
    def __init__(self,root):self.data=core.secure_dir(root);self.model=LocalDouble();self.calls=[];self.table_failures=0
    def run(self,request,documents=None):
        self.calls.append(request['kind'])
        if self.table_failures:
            self.table_failures-=1;raise ValueError('本地模型没有返回完整结果，请重试')
        if request['kind']=='table':return {'text':'已提取两行','columns':['项目','金额（元）'],'rows':[['甲','0.1'],['乙','0.2']],'artifacts':[]}
        if request['kind']=='organize':return {'text':'仅整理预览','artifacts':[],'transaction':{'id':'preview','state':'preview','moves':[]}}
        return {'text':'原文要点已整理。','artifacts':[]}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.source=self.base/'交通记录.txt';self.source.write_text('交通：高铁车票128.50元。\n附表：甲0.1元，乙0.2元。\n原始记录。')
        self.agent=LocalAgent(self.base/'data');self.office=OfficeAgent(self.agent,core)
    def tearDown(self):self.temp.cleanup()
    def plan(self,prompt='提取金额成表格，统计合计，再写一份说明。',kind='workflow'):
        with redirect_stdout(io.StringIO()):return self.office.draft({'prompt':prompt,'paths':[str(self.source)],'kind':kind,'adaptive':True})
    def execute(self,plan,edits=None):
        with redirect_stdout(io.StringIO()):return self.office.execute({'plan_id':plan['id'],'paths':plan['paths'],'steps':edits or []})

    def test_local_planner_gives_step_specific_sequence(self):
        self.agent.model.recipe={'title':'整理与成稿','steps':[{'tool':'summary','instruction':'先核对交通资料要点'},{'tool':'write','instruction':'写一份简短说明'}]}
        plan=self.plan('帮我写一份说明。')
        self.assertEqual(plan['planner_source'],'model')
        self.assertEqual([s['tool'] for s in plan['steps']],['summary','write'])
        self.assertEqual(plan['steps'][0]['instruction'],'先核对交通资料要点')

    def test_goal_review_completes_one_missing_delivery_and_keeps_previous_outputs(self):
        self.agent.model.deliveries=[{'action':'complete','tool':'write','quote':'另写一份简短说明','instruction':'只补充简短说明，不重复邮件。'},{'action':'accept'}]
        result=self.execute(self.plan('查找“交通”，写一封邮件，另写一份简短说明。'))
        plan=result['plan']
        self.assertEqual([s['tool'] for s in plan['steps']],['search','write','write'])
        self.assertEqual([s['attempts'] for s in plan['steps']],[1,1,1])
        self.assertEqual(plan['completion_check']['state'],'passed')
        self.assertEqual(plan['delivery_additions'],1)
        self.assertEqual(len(result['artifacts']),4)

    def test_goal_review_cannot_execute_or_invent_user_requirements(self):
        plan=self.plan('写一封邮件，同时列出待办清单。')
        for value in [
            {'action':'complete','tool':'shell','quote':'列出待办清单','instruction':'execute'},
            {'action':'complete','tool':'write','quote':'另外发给所有客户','instruction':'发信'},
            {'action':'complete','tool':'statistics','quote':'列出待办清单','instruction':'统计'},
            {'action':'complete','tool':'write','quote':'写一封邮件','instruction':'补写','path':'/tmp/other'}]:
            with self.assertRaises(ValueError):control.checked_delivery(value,plan)

    def test_goal_review_only_one_addition_even_when_more_is_claimed_missing(self):
        self.agent.model.deliveries=[{'action':'complete','tool':'write','quote':'另写一份说明','instruction':'写说明'},
                                     {'action':'complete','tool':'write','quote':'同时写一封邀请邮件','instruction':'写邀请邮件'}]
        plan=self.plan('查找“交通”，写一封邮件，另写一份说明，同时写一封邀请邮件。')
        result=self.execute(plan)
        self.assertEqual(result['plan']['delivery_additions'],1)
        self.assertEqual(result['plan']['completion_check']['state'],'partial')
        self.assertEqual(len(result['plan']['steps']),3)

    def test_goal_review_respects_disabled_tools_and_direct_answer(self):
        plan={'prompt':'直接回答，不生成文件，写一封邮件。','direct_answer':True,'steps':[]}
        action={'action':'complete','tool':'write','quote':'写一封邮件','instruction':'写邮件'}
        with self.assertRaises(ValueError):control.checked_delivery(action,plan)
        plan['direct_answer']=False;plan['steps']=[{'tool':'write','enabled':False}]
        with self.assertRaises(ValueError):control.checked_delivery(action,plan)

    def test_planning_rejects_writing_before_required_calculation(self):
        value={'title':'先写后算','steps':[{'tool':'write','instruction':'写说明'},{'tool':'table','instruction':'提取表格'},{'tool':'statistics','instruction':'算总额'}]}
        with self.assertRaisesRegex(ValueError,'再起草'):control.checked_recipe(value,TOOLS,['table','statistics','write'],True)

    def test_structured_statistics_never_reextracts_original_rows_with_model(self):
        source=self.base/'台账.csv';source.write_text('项目,金额\n甲,100\n乙,200\n')
        self.agent.model.recipe={'title':'重提取','steps':[{'tool':'table','instruction':'重新提取金额'},{'tool':'statistics','instruction':'统计'}]}
        with redirect_stdout(io.StringIO()):plan=self.office.draft({'prompt':'统计合计金额。','paths':[str(source)],'adaptive':True})
        self.assertEqual([s['tool'] for s in plan['steps']],['statistics'])
        self.assertEqual(plan['planner_source'],'rules')

    def test_unrequested_invoice_omission_cannot_invent_procurement_requirements(self):
        review={'reason':'未提及发票类型，若用户需普票，预算优先策略可能失效。','quote':'建议选更便宜的方案。'}
        self.assertTrue(control.optional_omission(review,'比较价格和上门安装，写一份说明。'))
        self.assertFalse(control.optional_omission(review,'必须提供普通发票，比较价格。'))
        review['quote']='该方案只能提供专用发票。'
        self.assertFalse(control.optional_omission(review,'比较价格和上门安装。'))

    def test_placeholder_in_writing_goal_does_not_trigger_search_for_personal_facts(self):
        plan=self.plan('根据流程起草请假邮件，原因待补充，交接人周宁。')
        step={'id':'step-0','tool':'answer','state':'completed','enabled':True,'instruction':'流程要求','summary':''}
        plan['steps']=[step]+plan['steps']
        self.agent.model.decisions=[{'action':'insert','tool':'search','instruction':'查找周宁请假的原因','reason':'未找到原因'}]
        context={'docs':[{'id':'S1','text':'申请应先审批'}],'scope_docs':[],'table':None,'query':{}}
        self.assertIsNone(self.office.adapt_after_result(plan,step,{'text':'无相关原文','evidence':[]},context))
        self.assertFalse(any(s['tool']=='search' for s in plan['steps']))

    def test_explicit_placeholder_does_not_block_writing_but_other_missing_fields_still_can(self):
        self.assertTrue(control.already_allowed_placeholder('原因待补充，无法继续起草邮件','起草请假申请，原因待补充。'))
        self.assertFalse(control.already_allowed_placeholder('原因和时间未提供','起草请假申请，原因待补充。'))
        plan=self.plan('起草请假申请，原因待补充。')
        step={'id':'step-0','tool':'answer','state':'completed','enabled':True,'instruction':'流程要求','summary':''};plan['steps']=[step]+plan['steps']
        self.agent.model.decisions=[{'action':'ask','reason':'原因待补充，无法起草'}]
        self.assertIsNone(self.office.adapt_after_result(plan,step,{'text':'流程已提供'},{}))

    def test_reviewer_cannot_block_true_comparison_with_pure_editorial_preference(self):
        review={'reason':'3200元高于2800元属实，但建议逻辑应强调虽价格更高但含服务，而非单纯陈述价格高低。','quote':'3200元高于2800元，但含上门服务。'}
        self.assertTrue(control.optional_omission(review,'分别给预算优先和需要上门安装的建议。'))
        review['reason']='虽金额属实，但遗漏提前48小时取消条件。'
        self.assertFalse(control.optional_omission(review,'写取消说明。'))

    def test_reviewer_cannot_attribute_an_absent_field_to_draft(self):
        reason='草稿将原文未确定的参会人数描述为由您补充，编造责任归属。'
        self.assertTrue(control.phantom_field_claim(reason,'会议链接由周宁补充。'))
        self.assertFalse(control.phantom_field_claim(reason,'参会人数由周宁补充。'))
        self.assertFalse(control.phantom_field_claim(reason,'请周宁确认25人参会。'))
        self.assertFalse(control.phantom_field_claim('草稿遗漏参会人数。','会议链接由周宁补充。'))

    def test_personal_writing_without_documents_still_reviews_user_constraints(self):
        self.agent.model.responses=[('每天准备半小时。','stop'),('每天准备半小时，分享时长10分钟。','stop')]
        self.agent.model.draft_checks=[{'action':'revise','reason':'应保留用户给定的10分钟分享时长。'},{'action':'accept'}]
        with redirect_stdout(io.StringIO()):
            plan=self.office.draft({'prompt':'制定五天准备计划，分享时长10分钟。','paths':[],'kind':'write','adaptive':True})
            result=self.office.execute({'plan_id':plan['id'],'paths':[]})
        self.assertIn('10分钟',result['text'])
        self.assertEqual(result['plan']['steps'][0]['attempts'],2)
        self.assertTrue(result['plan']['steps'][0]['check']['facts']['user_requirements_only'])

    def test_source_change_in_final_review_stops_before_supplement(self):
        original=self.agent.model.generate
        def changed(system,user,**kwargs):
            result=original(system,user,**kwargs)
            if '本地交付核对器' in system:self.source.write_text('原文已变化')
            return result
        self.agent.model.generate=changed
        with self.assertRaisesRegex(ValueError,'发生变化'):self.execute(self.plan('查找“交通”，写一份说明。'))

    def test_bad_model_plan_falls_back_without_unknown_tool(self):
        self.agent.model.recipe={'title':'危险规划','steps':[{'tool':'shell','instruction':'delete source'}]}
        plan=self.plan()
        self.assertEqual(plan['planner_source'],'rules')
        self.assertEqual([s['tool'] for s in plan['steps']],['table','statistics','write'])
        self.assertTrue(self.source.exists())

    def test_document_budget_constraints_do_not_become_table_row_filters(self):
        other=self.base/'另一份方案.txt';other.write_text('方案名称：另一个场地\n费用450元。')
        with redirect_stdout(io.StringIO()):
            plan=self.office.draft({'prompt':'对比两份方案，预算不超过500元、至少25人且必须有投影仪，再写一份选择说明。','paths':[str(self.source),str(other)],'adaptive':True})
        self.assertEqual([s['tool'] for s in plan['steps']],['compare','write'])

    def test_model_answer_mislabeled_writing_is_corrected_within_original_goal(self):
        self.agent.model.recipe={'title':'按原目标成稿','steps':[{'tool':'answer','instruction':'根据资料写一份简短说明'}]}
        plan=self.plan('写一份简短说明。')
        self.assertEqual([s['tool'] for s in plan['steps']],['write'])

    def test_planner_cannot_drop_numeric_dependencies_or_add_organize(self):
        for steps in [[{'tool':'write','instruction':'只写结论'}],[{'tool':'organize','instruction':'改名'}]]:
            with self.assertRaises(ValueError):control.checked_recipe({'title':'任务','steps':steps},TOOLS,['table','statistics','write'],True)

    def test_recoverable_output_retries_only_failed_step(self):
        self.agent.table_failures=1;result=self.execute(self.plan())
        self.assertEqual(result['plan']['state'],'completed')
        self.assertEqual([s['attempts'] for s in result['plan']['steps']],[2,1,1])
        self.assertTrue(any(e['kind']=='recovered' for e in result['plan']['events']))
        self.assertTrue(all(s['check']['state']=='passed' for s in result['plan']['steps']))

    def test_partial_draft_is_retried_and_only_complete_result_published(self):
        self.agent.model.responses=[('未完成草稿','length'),('完整文稿。','stop')]
        result=self.execute(self.plan('写一份说明。',kind='write'))
        self.assertEqual(result['text'],'完整文稿。')
        self.assertEqual(result['plan']['steps'][0]['attempts'],2)
        self.assertEqual(len(result['artifacts']),2)

    def test_source_changed_during_generation_stops_without_retry(self):
        plan=self.plan('写一份说明。',kind='write');original=self.office.tool
        def changed(*args):
            result=original(*args);self.source.write_text('changed');return result
        self.office.tool=changed
        with self.assertRaisesRegex(ValueError,'发生变化'):self.execute(plan)
        saved=self.office.get(plan['id'])
        self.assertEqual(saved['steps'][0]['attempts'],1);self.assertFalse(saved.get('results'))

    def test_local_writing_review_can_request_repair(self):
        self.agent.model.responses=[('建议立即批准这笔交通费用。【S1】','stop'),('原文记录了交通费用，批准情况待确认。【S1】','stop')]
        self.agent.model.draft_checks=[{'action':'revise','reason':'原文没有批准依据，请删除立即批准的建议，并标明待确认。'},{'action':'accept'}]
        result=self.execute(self.plan('写一份简短说明。',kind='write'))
        self.assertNotIn('立即批准',result['text'])
        self.assertEqual(result['plan']['steps'][0]['attempts'],2)
        self.assertEqual(result['plan']['steps'][0]['check']['content_review'],'model')
        self.assertNotIn('_review_reference',result)

    def test_invalid_content_review_retries_format_before_accepting(self):
        self.agent.model.draft_checks=[{'action':'execute','path':'outside'}]
        result=self.execute(self.plan('写一份说明。',kind='write'))
        check=result['plan']['steps'][0]['check']
        self.assertEqual(check['content_review'],'model')
        self.assertEqual(result['plan']['steps'][0]['attempts'],1)

    def test_unavailable_review_never_counts_as_verified_final_draft(self):
        self.agent.model.draft_checks=[{'action':'execute','path':'outside'}]*6
        result=self.execute(self.plan('写一份说明。',kind='write'))
        self.assertTrue(result['plan']['grounded_delivery'])
        self.assertEqual(result['plan']['steps'][0]['attempts'],3)

    def test_permission_failure_is_not_automatically_retried(self):
        self.agent.model.responses=[PermissionError('no access')]
        plan=self.plan('写一份说明。',kind='write')
        with self.assertRaises(PermissionError):self.execute(plan)
        self.assertEqual(self.office.get(plan['id'])['steps'][0]['attempts'],1)

    def test_feedback_inserts_tool_before_pending_write(self):
        self.agent.model.decisions=[{'action':'insert','tool':'summary','instruction':'补查原文要点','reason':'成稿前补查要点'},{'action':'continue'}]
        result=self.execute(self.plan('查找“交通”，再写一份说明。'))
        self.assertEqual([s['tool'] for s in result['plan']['steps']],['search','summary','write'])
        self.assertEqual([s['id'] for s in result['plan']['steps']],['step-1','step-3','step-2'])
        self.assertTrue(all(s['state']=='completed' for s in result['plan']['steps']))

    def test_feedback_does_not_duplicate_an_already_pending_write(self):
        self.agent.model.decisions=[{'action':'insert','tool':'write','instruction':'先写说明','reason':'需要一份说明'}]
        result=self.execute(self.plan('查找“交通”，再写一份说明。'))
        self.assertEqual([s['tool'] for s in result['plan']['steps']],['search','write'])
    def test_feedback_cannot_repeat_identical_deterministic_statistics(self):
        self.agent.model.decisions=[{'action':'insert','tool':'statistics','instruction':'再核对一次合计','reason':'确认金额'}]*3
        result=self.execute(self.plan())
        self.assertEqual(sum(s['tool']=='statistics' for s in result['plan']['steps']),1)

    def test_zero_search_can_change_keyword_within_same_scope(self):
        self.agent.model.decisions=[{'action':'insert','tool':'search','instruction':'交通','reason':'换用资料中的短关键词'},{'action':'continue'}]
        result=self.execute(self.plan('查找“差旅”，再写一份说明。'))
        self.assertEqual(len(result['search_hits']),1)
        self.assertEqual(result['plan']['steps'][0]['attempts'],1)
        self.assertEqual([s['tool'] for s in result['plan']['steps']],['search','search','write'])
        self.assertEqual(result['plan']['paths'],[str(self.source.resolve())])

    def test_no_match_stops_before_fabricated_writing(self):
        self.agent.model.decisions=[{'action':'ask','reason':'需要相关资料'}]
        result=self.execute(self.plan('查找“完全不存在”，再写一份说明。'))
        self.assertEqual(result['plan']['state'],'needs_input')
        self.assertEqual(result['plan']['steps'][-1]['attempts'],0)
        self.assertFalse(result['artifacts'])
    def test_exact_record_identifier_does_not_reuse_semantic_hit_as_literal_match(self):
        plan=self.plan('查找“ZXQ654321”相关记录，找到后再写一份说明。')
        plan['retrieval']={'hits':[{'path':str(self.source.resolve()),'snippet':self.source.read_text(),'line':1}]}
        self.office.save(plan)
        result=self.execute(plan)
        self.assertEqual(result['plan']['state'],'needs_input');self.assertFalse(result['artifacts'])

    def test_feedback_cannot_add_unrequested_file_changes(self):
        self.agent.model.decisions=[{'action':'insert','tool':'organize','instruction':'重命名','reason':'随便整理'}]
        result=self.execute(self.plan('查找“完全不存在”，再写一份说明。'))
        self.assertEqual(result['plan']['state'],'needs_input')
        self.assertNotIn('organize',[s['tool'] for s in result['plan']['steps']])

    def test_adaptation_is_bounded(self):
        self.agent.model.decisions=[{'action':'insert','tool':'summary','instruction':'补查','reason':'补查'}]*8
        result=self.execute(self.plan('查找“交通”，再写一份说明。'))
        self.assertLessEqual(len(result['plan']['steps']),control.MAX_STEPS)
        self.assertEqual(sum(e['kind']=='adjusted' for e in result['plan']['events']),2)
        self.assertLessEqual(self.agent.model.review_calls,3)

    def test_retry_failure_keeps_completed_steps_for_resume(self):
        self.agent.model.recipe={'title':'查找并回答','steps':[{'tool':'search','instruction':'交通'},{'tool':'answer','instruction':'交通记录是什么？'}]}
        self.agent.model.responses=[ValueError('本地模型没有返回完整结果')]*2
        plan=self.plan('查找“交通”，再回答资料问题。')
        with self.assertRaises(ValueError):self.execute(plan)
        saved=self.office.get(plan['id']);self.assertEqual(saved['steps'][0]['attempts'],1)
        self.agent.model.responses=[('{"line_ids":["S1:L1:P1"]}','stop')]
        final=self.execute(saved)
        self.assertEqual(final['plan']['steps'][0]['attempts'],1)
        self.assertEqual(final['plan']['steps'][-1]['attempts'],3)

    def test_result_validation_rejects_output_symlink_escape(self):
        outside=self.base/'outside.md';outside.write_text('outside')
        folder=core.secure_dir(self.agent.data/'Outputs');link=folder/'link.md';link.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'存储范围'):
            control.check_result('write',{'text':'正文','artifacts':[{'path':str(link)}]},self.agent.data)

    def test_explicit_organize_stays_preview(self):
        plan=self.plan('整理文件',kind='organize');result=self.execute(plan)
        self.assertEqual(result['transaction']['state'],'preview');self.assertTrue(self.source.exists())

    def test_feedback_cannot_restore_a_user_disabled_compare_step(self):
        other=self.base/'另一份.txt';other.write_text('交通方案')
        with redirect_stdout(io.StringIO()):
            plan=self.office.draft({'prompt':'查找“交通”，对比两份资料，再写一份说明。','paths':[str(self.source),str(other)],'kind':'workflow','adaptive':True})
        self.office.update(plan,[{'id':'step-2','enabled':False}])
        plan['steps'][0]['state']='completed'
        self.agent.model.decisions=[{'action':'insert','tool':'compare','instruction':'重新对比','reason':'再次对比'}]
        docs,_=core.collect(core.Scope(plan['paths']))
        self.office.adapt_after_result(plan,plan['steps'][0],{'text':'已找到两份资料','matched_ids':['S1','S2']},{'docs':docs,'table':None,'query':{}})
        self.assertEqual(len(plan['steps']),3)


if __name__=='__main__':unittest.main()
