import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
import io

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import worker as core
from office_agent import OfficeAgent,compute_statistics,numeric_value,read_structured,review_draft


class FakeModel:
    failure=None
    calls=0
    finish_reason='stop'
    def generate(self,*args,**kwargs):
        self.calls+=1
        if self.failure:
            failure,self.failure=self.failure,None
            raise failure
        return '# 本地文稿\n合计 0.30 元。',{'seconds':.01,'tokens':10,'peak_memory_gb':0,'finish_reason':self.finish_reason}


class FakeAgent:
    def __init__(self,path):
        self.data=core.secure_dir(path);self.model=FakeModel();self.table_calls=0
    def run(self,request,documents=None):
        self.table_calls+=1
        return {'text':'已提取两行。','columns':['项目','金额（元）'],'rows':[['甲','0.10'],['乙','0.20']],'artifacts':[], 'stats':{'seconds':.01},'sources':[]}


class OfficeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.selected=self.base/'selected';self.selected.mkdir()
        self.file=self.selected/'记录.txt';self.file.write_text('项目甲金额0.10元，项目乙金额0.20元。')
        self.agent=FakeAgent(self.base/'data');self.office=OfficeAgent(self.agent,core)
    def tearDown(self):self.temp.cleanup()
    def draft(self,prompt='提取金额成表格，统计金额，再写一份说明。',paths=None,kind='workflow'):
        with redirect_stdout(io.StringIO()):return self.office.draft({'prompt':prompt,'paths':paths or [str(self.selected)],'kind':kind})
    def execute(self,plan,edits=None):
        with redirect_stdout(io.StringIO()):return self.office.execute({'plan_id':plan['id'],'paths':plan['paths'],'steps':edits or []})

    def test_decimal_sum_is_exact_and_identifiers_are_excluded(self):
        stats=compute_statistics({'columns':['金额（元）','日期','编号'],'rows':[['0.1','2026-10-21','001'],['0.2','2026-10-22','002']]})
        self.assertEqual(stats['rows'][0][2],'0.3');self.assertEqual(stats['rows'][0][3],'0.15')
        self.assertEqual(stats['rows'][0][6],'元');self.assertEqual(len(stats['rows']),1)

    def test_values_are_never_evaluated(self):
        for value in ['=WEBSERVICE("x")','__import__("os").system("x")','2026-10-21','20%','12元+3元']:
            self.assertIsNone(numeric_value(value))
        self.assertEqual(numeric_value('¥1,234.50'),(__import__('decimal').Decimal('1234.50'),'元'))

    def test_mixed_units_are_not_summed(self):
        stats=compute_statistics({'columns':['金额','数量'],'rows':[['12元','1'],['$3','2']]})
        self.assertEqual([r[0] for r in stats['rows']],['数量']);self.assertIn('不同单位',stats['notes'][0])

    def test_draft_does_not_invent_date_sender_or_assurance(self):
        text=review_draft('邀请同事周五开会。\n数据准确无误。\n归屿\n2024年4月5日','', '写一封邮件邀请同事参加沟通会。')
        self.assertNotIn('2024年4月5日',text);self.assertNotIn('准确无误',text)
        self.assertIn('发信人待补充',text);self.assertIn('时间待补充',text);self.assertIn('地点待补充',text)
        self.assertIn('2026年10月21日',review_draft('日期：2026年10月21日','日期：2026年10月21日','起草文稿'))
        self.assertEqual(review_draft('需于2026年10月23日前确认。','待办：10月23日前确认。','起草简报'),'需于10月23日前确认。')
        self.assertIn('各位同事',review_draft('亲爱的【发信人待补充】：','', '写一封邮件邀请同事参加会议。'))
        self.assertEqual(review_draft('经核实，该数据来源于【S1】。','', '起草说明'),'该数据来源于【S1】。')

    def test_plan_never_executes_tools(self):
        plan=self.draft();self.assertEqual(self.agent.table_calls,0);self.assertEqual(plan['state'],'draft')
        self.assertFalse((self.agent.data/'Outputs').exists())
        self.assertEqual([s['tool'] for s in plan['steps']],['table','statistics','write'])

    def test_incomplete_generation_is_identified_in_result_and_export(self):
        self.agent.model.finish_reason='length'
        plan=self.draft('写一份说明',kind='write')
        result=self.execute(plan)
        self.assertIn('尚未写完',result['text'])
        markdown=next(a for a in result['artifacts'] if a['type']=='md')
        self.assertIn('尚未写完',Path(markdown['path']).read_text())
        self.assertIn('部分内容',result['plan']['steps'][0]['summary'])

    def test_changed_files_stop_before_any_tool(self):
        plan=self.draft();self.file.write_text('已修改的内容')
        with self.assertRaisesRegex(ValueError,'发生变化'):self.execute(plan)
        self.assertEqual(self.agent.table_calls,0)

    def test_new_file_in_scope_requires_new_plan(self):
        plan=self.draft();(self.selected/'新增.txt').write_text('不应被自动加入')
        with self.assertRaisesRegex(ValueError,'发生变化'):self.execute(plan)
        self.assertEqual(self.agent.table_calls,0)

    def test_user_cannot_inject_tool_or_change_permission(self):
        plan=self.draft()
        with self.assertRaisesRegex(ValueError,'只能调整'):
            self.execute(plan,[{'id':'step-1','tool':'shell','instruction':'执行代码'}])
        self.assertEqual(self.agent.table_calls,0)

    def test_corrupt_tool_journal_is_rejected(self):
        plan=self.draft();plan['steps'][0]['tool']='shell';self.office.save(plan)
        with self.assertRaisesRegex(ValueError,'不支持的工具'):self.execute(plan)
        self.assertEqual(self.agent.table_calls,0)

    def test_disabling_dependency_is_rejected(self):
        plan=self.draft()
        with self.assertRaisesRegex(ValueError,'统计需要表格'):
            self.execute(plan,[{'id':'step-1','enabled':False}])
        self.assertEqual(self.agent.table_calls,0)

    def test_crash_resume_reuses_completed_steps(self):
        plan=self.draft();self.agent.model.failure=KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.execute(plan)
        self.assertEqual(self.agent.table_calls,1)
        first=self.office.get(plan['id']);self.assertEqual(first['state'],'running')
        completed=[s['id'] for s in first['steps'] if s['state']=='completed']
        self.assertEqual(len(completed),2)
        self.office=OfficeAgent(self.agent,core)
        paused=self.office.get(plan['id']);self.assertEqual(paused['state'],'paused')
        final=self.execute(paused)
        self.assertEqual(final['plan']['state'],'completed');self.assertEqual(self.agent.table_calls,1)
        self.assertEqual(len(final['artifacts']),3)
        self.assertTrue(all(Path(a['path']).is_file() for a in final['artifacts']))
        with self.assertRaisesRegex(ValueError,'已经完成'):self.execute(paused)

    def test_failed_step_can_be_edited_and_retried(self):
        plan=self.draft();self.agent.model.failure=ValueError('模型暂时失败')
        with self.assertRaisesRegex(ValueError,'模型暂时失败'):self.execute(plan)
        failed=self.office.get(plan['id']);self.assertEqual(failed['state'],'failed')
        final=self.execute(failed,[{'id':'step-3','instruction':'写一段简短说明。'}])
        self.assertEqual(final['plan']['state'],'completed');self.assertEqual(self.agent.table_calls,1)
        self.assertEqual(final['plan']['steps'][2]['instruction'],'写一段简短说明。')

    def test_structured_statistics_does_not_call_model(self):
        csv=self.selected/'费用.csv';csv.write_text('项目,金额（元）\n甲,0.10\n乙,0.20\n')
        plan=self.draft('统计表格中的金额合计。',paths=[str(csv)])
        self.assertEqual([s['tool'] for s in plan['steps']],['statistics'])
        result=self.execute(plan)
        self.assertEqual(self.agent.model.calls,0);self.assertEqual(self.agent.table_calls,0)
        self.assertEqual(result['rows'][0][2],'0.3')

    def test_csv_schema_mismatch_is_explicit(self):
        (self.selected/'一.csv').write_text('名称,金额\n甲,1\n')
        (self.selected/'二.csv').write_text('名称,人数\n乙,2\n')
        docs,_=core.collect(core.Scope([str(self.selected)]))
        with self.assertRaisesRegex(ValueError,'表头不同'):read_structured(docs,core)

    def test_csv_row_limit_is_explicit(self):
        self.file.unlink();(self.selected/'大表.csv').write_text('金额\n'+'1\n'*1001)
        docs,_=core.collect(core.Scope([str(self.selected)]))
        with self.assertRaisesRegex(ValueError,'1,000'):read_structured(docs,core)

    def test_selected_scope_cannot_be_changed_on_resume(self):
        plan=self.draft()
        with redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError,'范围已经改变'):
                self.office.execute({'plan_id':plan['id'],'paths':[str(self.file)]})
        self.assertEqual(self.agent.table_calls,0)


if __name__=='__main__':unittest.main()
