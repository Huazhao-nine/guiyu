import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import worker as core
from office_agent import OfficeAgent,compute_statistics,numeric_value
from local_query import apply_query,compile_query,grouped_statistics,search_documents,search_query,validate_query
from model_info import describe_model

TABLE={'columns':['项目','金额（元）','经办人','状态','日期'],'rows':[
 ['资料','128.50','林晓','已垫付，待报销','2026-10-20'],
 ['场地','260.00','陈雨','待付款','2026-10-21'],
 ['交通','43.20','周宁','已垫付，待报销','2026-10-21'],
 ['打印','35.00','林晓','已报销','2026-10-19'],
 ['设备','180.00','陈雨','已垫付，待报销','2026-10-22'],
 ['茶水','62.30','林晓','已垫付，待报销','2026-10-22']]}

class QueryTests(unittest.TestCase):
 def run_query(self,prompt,inherited=None):
  q=compile_query(prompt,TABLE,inherited);return q,apply_query(TABLE,q,numeric_value)
 def test_name_and_numeric_predicates_with_grouping(self):
  q,t=self.run_query('只统计状态包含待报销且金额大于100元，按经办人分组统计。')
  self.assertEqual(len(t['rows']),2)
  m=grouped_statistics(t,q,compute_statistics)
  self.assertEqual([r[3] for r in m['rows']],['128.5','180'])
 def test_followup_replaces_name_and_preserves_other_filters(self):
  q,t=self.run_query('只看林晓且金额大于100元。')
  self.assertEqual(len(t['rows']),1)
  q,t=self.run_query('那陈雨呢？',q)
  self.assertEqual([r[0] for r in t['rows']],['场地','设备'])
  self.assertEqual(len(q['filters']),2)
 def test_clear_conditions_recovers_original_rows(self):
  q,_=self.run_query('只看林晓且金额大于100元。')
  q,t=self.run_query('清除筛选，统计全部记录。',q)
  self.assertEqual(len(t['rows']),6);self.assertEqual(q['filters'],[])
 def test_zero_matches_are_not_replaced_by_full_data(self):
  q,t=self.run_query('只统计金额大于9999元。')
  self.assertEqual(t['rows'],[]);self.assertEqual(grouped_statistics(t,q,compute_statistics)['rows'],[])
 def test_drafting_length_does_not_become_a_filter(self):
  q,_=self.run_query('只看林晓。')
  next_query,_=self.run_query('把结果写成不超过200字的说明。',q)
  self.assertEqual(next_query,q)
  next_query,_=self.run_query('把本轮筛选与统计结果写成一段简短说明，引用资料出处。',q)
  self.assertEqual(next_query,q)
 def test_filter_checks_units_from_column_header(self):
  q={'filters':[{'column':'金额','operator':'gt','value':'$100'}]}
  with self.assertRaisesRegex(ValueError,'单位'):apply_query(TABLE,q,numeric_value)
 def test_unknown_conditions_require_clarification(self):
  for prompt in ('只看聪明的项目','只统计昨天的费用','只看林晓且小于100元','只看林晓且凭证齐全'):
   with self.subTest(prompt=prompt):
    with self.assertRaises(ValueError):self.run_query(prompt)
 def test_explicit_panel_query_supports_or_and_dates(self):
  q=validate_query({'match':'any','filters':[{'column':'经办人','operator':'eq','value':'周宁'},{'column':'日期','operator':'gte','value':'2026-10-22'}]},TABLE['columns'])
  self.assertEqual(len(apply_query(TABLE,q,numeric_value)['rows']),3)
 def test_comparison_does_not_evaluate_expressions(self):
  q={'filters':[{'column':'金额','operator':'gt','value':'__import__("os")'}]}
  with self.assertRaises(ValueError):apply_query(TABLE,q,numeric_value)
 def test_query_cannot_inject_code_or_unknown_columns(self):
  for q in ({'filters':[],'shell':'ls'},{'filters':[{'column':'秘密','operator':'eq','value':'1'}]},{'filters':[{'column':'金额','operator':'eval','value':'1'}]}):
   with self.assertRaises(ValueError):validate_query(q,TABLE['columns'])
 def test_search_returns_only_matching_sources_and_line_context(self):
  docs=[{'id':'S1','name':'费用.txt','path':'a','text':'开始\n交通费用43.20元\n结束'},{'id':'S2','name':'场地.txt','path':'b','text':'金额260元'}]
  hits=search_documents(docs,search_query('查找“交通”相关资料，统计费用。'))
  self.assertEqual([h['id'] for h in hits],['S1']);self.assertEqual(hits[0]['line'],2)
  self.assertEqual(search_documents(docs,'不存在的关键词'),[])
 def test_multi_turn_dataset_is_reused_without_model_math(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);csv=base/'费用.csv'
   import csv as csvlib
   with csv.open('w') as f:
    writer=csvlib.writer(f);writer.writerow(TABLE['columns']);writer.writerows(TABLE['rows'])
   class Model:
    info={'key':'test','name':'test'}
    def generate(self,*a,**kw):raise AssertionError('No model call for deterministic statistics')
   agent=core.Agent(Model(),base/'data');office=OfficeAgent(agent,core)
   with redirect_stdout(io.StringIO()):
    first=office.draft({'prompt':'只统计状态包含待报销且金额大于100元，按经办人分组统计。','paths':[str(csv)]})
    first=office.execute({'plan_id':first['id'],'paths':first['paths']})
    second=office.draft({'prompt':'那陈雨呢？','parent_id':first['id'],'paths':[str(csv)]})
    self.assertTrue(second['reused_table'])
    second=office.execute({'plan_id':second['id'],'paths':second['paths']})
    third=office.draft({'prompt':'清除筛选，取消分组，统计全部记录。','parent_id':second['id'],'paths':[str(csv)]})
    third=office.execute({'plan_id':third['id'],'paths':third['paths']})
   self.assertEqual(second['thread_id'],first['thread_id'])
   self.assertIn('180',second['text']);self.assertIn('709',third['text'])
   self.assertEqual(len(third['plan']['query_state']['base_table']['rows']),6)
 def test_model_switch_cannot_resume_unfinished_plan(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);csv=base/'费用.csv';csv.write_text('金额\n1\n')
   class Model:info={'key':'first','name':'first'}
   model=Model();office=OfficeAgent(core.Agent(model,base/'data'),core)
   with redirect_stdout(io.StringIO()):p=office.draft({'prompt':'统计金额','paths':[str(csv)]})
   model.info={'key':'second','name':'second'}
   with self.assertRaisesRegex(ValueError,'模型已切换'):office.execute({'plan_id':p['id'],'paths':p['paths']})
 def test_custom_model_code_is_rejected_before_load(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp);(p/'config.json').write_text(json.dumps({'model_type':'custom','auto_map':{'AutoModel':'run.py'}}))
   with self.assertRaisesRegex(ValueError,'自定义代码'):describe_model(p)
 def test_empty_search_cannot_expand_scope_on_followup(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);file=base/'资料.txt';file.write_text('交通费用43.20元。')
   class Model:
    def generate(self,*a,**kw):raise AssertionError('Should stop before generation')
   office=OfficeAgent(core.Agent(Model(),base/'data'),core)
   with redirect_stdout(io.StringIO()):
    plan=office.draft({'prompt':'查找“没有的词”','kind':'search','paths':[str(file)]})
    result=office.execute({'plan_id':plan['id'],'paths':plan['paths']})
    following=office.draft({'prompt':'写一段说明','kind':'write','parent_id':result['id'],'paths':plan['paths']})
    with self.assertRaisesRegex(ValueError,'上一轮没有匹配'):
     office.execute({'plan_id':following['id'],'paths':plan['paths']})
 def test_search_does_not_apply_statistics_row_limit(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);file=base/'大表.csv';file.write_text('项目,金额\n'+'交通,1\n'*1001)
   class Model:
    def generate(self,*a,**kw):raise AssertionError('Literal search does not need a model')
   office=OfficeAgent(core.Agent(Model(),base/'data'),core)
   with redirect_stdout(io.StringIO()):
    plan=office.draft({'prompt':'查找“交通”','kind':'search','paths':[str(file)]})
    result=office.execute({'plan_id':plan['id'],'paths':plan['paths']})
   self.assertEqual(len(result['search_hits']),1)
 def test_unstructured_filter_cannot_be_disabled_before_schema_exists(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);file=base/'资料.txt';file.write_text('交通费用43.20元。')
   class Model:
    def generate(self,*a,**kw):raise AssertionError('Should reject before model use')
   office=OfficeAgent(core.Agent(Model(),base/'data'),core)
   with redirect_stdout(io.StringIO()):plan=office.draft({'prompt':'只统计金额大于100元的费用。','paths':[str(file)]})
   step=next(s for s in plan['steps'] if s['tool']=='filter')
   with self.assertRaisesRegex(ValueError,'保留筛选步骤'):
    office.execute({'plan_id':plan['id'],'paths':plan['paths'],'steps':[{'id':step['id'],'enabled':False}]})

if __name__=='__main__':unittest.main()
