import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from table_program import run_program,TableError

TABLE={'columns':['编号','部门','状态','应付（元）','已付（元）','到期日','邮箱'], 'rows':[
 ['001','研发','待付款','1200','0','2026-10-20','a@example.com'],
 ['002','行政','部分付款','1000','400','2026-10-28',''],
 ['003','研发','已付款','800','800','2026-10-15','b@example.com'],
 ['004','销售','待付款','2000','0','2026-11-02','a@example.com'],
 ['005','行政','待付款','300','0','2026-10-30','c@example.com']]}

class ProgramTests(unittest.TestCase):
 def run_ops(self,*ops):return run_program(TABLE,list(ops))
 def test_nested_boolean_and_negation(self):
  result=self.run_ops({'op':'filter','where':{'all':[{'column':'部门','operator':'in','value':['研发','行政']},{'any':[{'column':'状态','operator':'eq','value':'待付款'},{'column':'状态','operator':'eq','value':'部分付款'}]},{'not':{'column':'应付（元）','operator':'lt','value':'500','type':'number'}}]}})
  self.assertEqual([r[0] for r in result['rows']],['001','002'])
 def test_derive_filter_numeric_sort_and_projection(self):
  result=self.run_ops({'op':'derive','name':'未付（元）','expression':{'subtract':[{'column':'应付（元）'},{'column':'已付（元）'}]}},
   {'op':'filter','where':{'column':'未付（元）','operator':'gt','value':'0','type':'number'}},
   {'op':'sort','by':[{'column':'未付（元）','type':'number','direction':'desc'}]}, {'op':'limit','count':2}, {'op':'select','columns':['编号','未付（元）']})
  self.assertEqual(result['rows'],[['004','2000'],['001','1200']]);self.assertEqual(result['provenance'],[[3],[0]])
 def test_group_count_sum_then_sort(self):
  result=self.run_ops({'op':'group','by':['部门'],'metrics':[{'function':'sum','column':'应付（元）','as':'应付合计（元）'},{'function':'count','as':'笔数'}]}, {'op':'sort','by':[{'column':'应付合计（元）','direction':'desc','type':'number'},{'column':'部门','direction':'asc'}]})
  self.assertEqual(result['rows'],[['研发','2000','2'],['销售','2000','1'],['行政','1300','2']]);self.assertEqual(result['provenance'][0],[0,2])
 def test_date_range_and_blank(self):
  result=self.run_ops({'op':'filter','where':{'all':[{'column':'到期日','operator':'lt','value':'2026-10-29','type':'date'},{'column':'邮箱','operator':'is_empty'}]}})
  self.assertEqual([r[0] for r in result['rows']],['002'])
 def test_no_implicit_dedup(self):
  self.assertEqual(len(self.run_ops()['rows']),5)
  r=self.run_ops({'op':'distinct','columns':['邮箱']});self.assertEqual(len(r['rows']),4);self.assertEqual(r['provenance'][0],[0,3])
 def test_source_not_mutated(self):
  self.run_ops({'op':'select','columns':['编号']});self.assertEqual(len(TABLE['columns']),7)
 def test_empty_result_keeps_schema_and_count(self):
  r=self.run_ops({'op':'filter','where':{'column':'部门','operator':'eq','value':'不存在'}},{'op':'group','by':[],'metrics':[{'function':'count','as':'笔数'}]});self.assertEqual(r['rows'],[['0']])
 def test_decimal_arithmetic(self):
  r=run_program({'columns':['金额（元）'],'rows':[['0.1'],['0.2']]},[{'op':'group','by':[],'metrics':[{'function':'sum','column':'金额（元）','as':'合计（元）'}]}]);self.assertEqual(r['rows'],[['0.3']])
 def test_header_units_and_explicit_cell_units(self):
  table={'columns':['金额（万元）'],'rows':[['1.2'],['8000元'],['0.5']]}
  r=run_program(table,[{'op':'filter','where':{'column':'金额（万元）','operator':'gte','value':'1万元','type':'number'}}]);self.assertEqual(r['rows'],[['1.2']])
  r=run_program(table,[{'op':'group','by':[],'metrics':[{'function':'sum','column':'金额（万元）','as':'合计（万元）'}]}]);self.assertEqual(r['rows'],[['2.5']])
 def test_percent_means_and_zero_is_not_blank(self):
  r=run_program({'columns':['完成率（%）'],'rows':[['80'],['50%'],['0']]},[{'op':'group','by':[],'metrics':[{'function':'mean','column':'完成率（%）','as':'平均完成率（%）'}]}]);self.assertEqual(r['rows'],[['43.33']])
 def test_blanks_last_in_descending_order(self):
  r=run_program({'columns':['金额'],'rows':[[''],['2'],['10']]},[{'op':'sort','by':[{'column':'金额','type':'number','direction':'desc'}]}]);self.assertEqual(r['rows'],[['10'],['2'],['']])
 def test_missing_values_reported_not_silently_zeroed(self):
  r=run_program({'columns':['金额'],'rows':[[''],['']]},[{'op':'group','by':[],'metrics':[{'function':'sum','column':'金额','as':'合计'}]}]);self.assertEqual(r['rows'],[['']]);self.assertTrue(r['notes'])
 def test_bad_numeric_cells_stop(self):
  with self.assertRaises(TableError):run_program({'columns':['金额'],'rows':[['待确认'],['100']]},[{'op':'group','by':[],'metrics':[{'function':'sum','column':'金额','as':'合计'}]}])
 def test_identifiers_cannot_be_summed(self):
  with self.assertRaises(TableError):self.run_ops({'op':'group','by':[],'metrics':[{'function':'sum','column':'编号','as':'合计'}]})
 def test_mixed_currency_rejected_for_sum_and_derive(self):
  with self.assertRaises(TableError):run_program({'columns':['金额'],'rows':[['$5'],['5元']]},[{'op':'group','by':[],'metrics':[{'function':'sum','column':'金额','as':'合计'}]}])
  with self.assertRaises(TableError):run_program({'columns':['甲USD','乙元'],'rows':[['5','5']]},[{'op':'derive','name':'差额','expression':{'subtract':[{'column':'甲USD'},{'column':'乙元'}]}}])
 def test_zero_division_and_unknown_operations_are_rejected(self):
  for op in ({'op':'shell','command':'ls'},{'op':'derive','name':'x','expression':{'divide':[{'column':'应付（元）'},{'constant':0}]}}):
   with self.subTest(op=op),self.assertRaises(TableError):self.run_ops(op)
 def test_unknown_field_and_empty_input_still_validate(self):
  with self.assertRaises(TableError):run_program({'columns':['金额'],'rows':[]},[{'op':'filter','where':{'column':'不存在','operator':'eq','value':'a'}}])
 def test_condition_budget_and_no_short_circuit_on_invalid_branch(self):
  with self.assertRaises(TableError):self.run_ops({'op':'filter','where':{'any':[{'column':'部门','operator':'eq','value':'研发'},{'column':'秘密','operator':'eq','value':'x'}]}})
 def test_distinct_count_and_offset(self):
  r=self.run_ops({'op':'group','by':[],'metrics':[{'function':'count_distinct','column':'邮箱','as':'邮箱数'}]});self.assertEqual(r['rows'],[['3']])
  r=self.run_ops({'op':'limit','count':1,'offset':1});self.assertEqual(r['rows'][0][0],'002')
 def test_bad_date_does_not_compare_lexicographically(self):
  with self.assertRaises(TableError):self.run_ops({'op':'filter','where':{'column':'到期日','operator':'gte','value':'2026-02-30','type':'date'}})
 def test_compare_columns_and_explicit_percent_threshold(self):
  r=self.run_ops({'op':'filter','where':{'column':'应付（元）','operator':'gt','value_column':'已付（元）','type':'number'}});self.assertEqual(len(r['rows']),4)
  with self.assertRaisesRegex(TableError,'%'):run_program({'columns':['比例'],'rows':[['80%']]},[{'op':'filter','where':{'column':'比例','operator':'lt','value':'90','type':'number'}}])
 def test_numeric_type_annotation_is_harmless_but_code_is_not_allowed(self):
  r=self.run_ops({'op':'derive','name':'余额','expression':{'subtract':[{'column':'应付（元）','type':'number'},{'column':'已付（元）'}]}});self.assertEqual(r['rows'][0][-1],'1200')
  with self.assertRaises(TableError):self.run_ops({'op':'derive','name':'执行','expression':{'exec':'anything'}})
 def test_summary_preserves_details_and_followup_clears_stale_summary(self):
  r=self.run_ops({'op':'summary','by':[],'metrics':[{'function':'sum','column':'应付（元）','as':'合计（元）'}]})
  self.assertEqual(len(r['rows']),5);self.assertEqual(r['summaries'][0]['rows'],[['5300']])
  next_result=run_program(r,[{'op':'limit','count':1}]);self.assertNotIn('summaries',next_result)
 def test_group_then_lost_field_has_actionable_feedback(self):
  with self.assertRaisesRegex(TableError,'summary'):self.run_ops({'op':'group','by':[],'metrics':[{'function':'count','as':'数量'}]},{'op':'select','columns':['部门']})
 def test_failed_operation_reports_its_original_index_for_repair(self):
  events=[]
  with self.assertRaisesRegex(TableError,'index=1') as caught:
   run_program({'columns':['日期'],'rows':[['2026-10-01']]},[{'op':'limit','count':1},{'op':'derive','name':'键','expression':{'column':'日期','type':'date'}}],lambda i,e:events.append(i))
  self.assertEqual(events,[0]);self.assertEqual(caught.exception.operation_index,1);self.assertEqual(caught.exception.operation,'derive')

if __name__=='__main__':unittest.main()
