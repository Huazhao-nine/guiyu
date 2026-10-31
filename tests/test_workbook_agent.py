from contextlib import redirect_stdout
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from openpyxl import Workbook,load_workbook
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import worker as core
from office_agent import OfficeAgent
from workbook_data import inspect_documents,prepare_table,profile
from workbook_agent import patch_program,check_grounding,preflight,normalize_delivery,output_contract,project_result

class Model:
 info={'key':'qa','name':'QA'}
 def __init__(self,answers):self.answers=list(answers);self.calls=[]
 def generate(self,system,user,**kw):
  self.calls.append((system,user));value=self.answers.pop(0)
  return json.dumps(value,ensure_ascii=False),{'tokens':12,'seconds':.01}

CHOICE={'tables':[{'id':'T2','header_rows':[3,4],'exclude_summary':True}]}
PROGRAM={'title':'销售汇总','base':'source','operations':[{'op':'group','by':['区域'],'metrics':[{'function':'sum','column':'10月 / 实际（元）','as':'实际合计（元）'}]}],'write':''}
ACCEPT={'action':'accept','reason':''}

class WorkbookTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.file=self.root/'经营报表.xlsx'
  book=Workbook();sheet=book.active;sheet.title='库存';sheet.append(['物料','库存']);sheet.append(['纸张',40])
  sheet=book.create_sheet('销售');sheet.append(['经营数据']);sheet.append([]);sheet.append(['区域','10月','']);sheet.append(['区域','目标（元）','实际（元）']);sheet.merge_cells('A3:A4');sheet.merge_cells('B3:C3')
  sheet.append(['北区',1000,800]);sheet.append(['南区',2000,1600]);sheet.append(['北区',500,400]);sheet.append(['合计',3500,2800]);book.save(self.file);book.close()
  self.before=core.digest(self.file)
 def tearDown(self):self.temp.cleanup()
 def docs(self):return core.collect(core.Scope([str(self.file)]))[0]
 def inspect(self):return inspect_documents(self.docs(),core)
 def run_task(self,office,prompt,parent=None):
  with redirect_stdout(io.StringIO()):
   plan=office.draft({'id':'request1','prompt':prompt,'paths':[str(self.file)],'kind':'auto','adaptive':True,'parent_id':parent})
   return office.execute({'plan_id':plan['id'],'paths':plan['paths']})
 def test_heterogeneous_sheets_and_multilevel_headers(self):
  tables=self.inspect();result=prepare_table(tables,CHOICE['tables'])
  self.assertEqual(result['columns'],['区域','10月 / 目标（元）','10月 / 实际（元）'])
  self.assertEqual(len(result['rows']),3);self.assertIn('8',result['notes'][0]);self.assertEqual(result['locations'][0]['row'],5)
 def test_schema_types_empty_counts_and_identifiers(self):
  result=profile({'columns':['学号','金额','日期'],'rows':[['001','0','2026-10-01'],['002','','2026/10/02']]})
  self.assertEqual([f['type'] for f in result['fields']],['text','number','date']);self.assertEqual(result['fields'][1]['empty'],1)
 def test_actual_agent_exports_aggregate_and_cell_provenance(self):
  office=OfficeAgent(core.Agent(Model([CHOICE,PROGRAM,ACCEPT]),self.root/'data'),core)
  result=self.run_task(office,'统计经营报表中销售页10月各区域的实际收入。')
  self.assertEqual(result['rows'],[['北区','1200'],['南区','1600']]);self.assertEqual(result['plan']['completion_check']['state'],'passed');self.assertEqual(core.digest(self.file),self.before)
  path=next(a['path'] for a in result['artifacts'] if a['type']=='xlsx');book=load_workbook(path,read_only=True)
  audit=list(book['来源核对'].iter_rows(values_only=True));book.close()
  self.assertEqual([r[-1] for r in audit[1:]],['5','7','6'])
  self.assertFalse(result['transaction'])
 def test_unknown_column_is_repaired_before_export(self):
  wrong=deepcopy(PROGRAM);wrong['operations'][0]['metrics'][0]['column']='虚构收入'
  model=Model([CHOICE,wrong,{'edits':[{'index':0,'replace':PROGRAM['operations']}]},ACCEPT]);office=OfficeAgent(core.Agent(model,self.root/'data'),core)
  result=self.run_task(office,'按区域汇总实际收入。')
  self.assertEqual(len(result['plan']['workbook']['repairs']),1);self.assertEqual(result['rows'][0][1],'1200')
 def test_failed_local_edits_can_replan_once_with_all_checks_retained(self):
  wrong=deepcopy(PROGRAM);wrong['operations'][0]['metrics'][0]['column']='虚构收入'
  model=Model([CHOICE,wrong,{'edits':[]},{'edits':[]},PROGRAM,ACCEPT]);office=OfficeAgent(core.Agent(model,self.root/'data'),core)
  result=self.run_task(office,'按区域汇总实际收入。')
  self.assertEqual(len(result['plan']['workbook']['repairs']),3);self.assertEqual(result['rows'][0][1],'1200')
  self.assertIn('恢复方式',json.loads(model.calls[4][1]));self.assertNotIn('待修正计划',json.loads(model.calls[4][1]))
 def test_alternative_plan_does_not_bypass_numeric_grounding(self):
  wrong=deepcopy(PROGRAM);wrong['operations'][0]['metrics'][0]['column']='虚构收入'
  invented={'base':'source','operations':[{'op':'filter','where':{'column':'10月 / 实际（元）','operator':'gt','value':'999','type':'number'}}],'write':''}
  model=Model([CHOICE,wrong,{'edits':[]},{'edits':[]},invented]);office=OfficeAgent(core.Agent(model,self.root/'data'),core)
  with self.assertRaisesRegex(ValueError,'999'):self.run_task(office,'按区域汇总实际收入。')
  self.assertFalse((office.agent.data/'Outputs').exists());self.assertEqual(len(model.calls),5)
 def test_followup_uses_previous_aggregate_without_resumming_raw_data(self):
  second={'title':'收入前一名','base':'previous','operations':[{'op':'sort','by':[{'column':'实际合计（元）','type':'number','direction':'desc'}]},{'op':'limit','count':1}],'write':''}
  model=Model([CHOICE,PROGRAM,ACCEPT,second,ACCEPT]);office=OfficeAgent(core.Agent(model,self.root/'data'),core)
  first=self.run_task(office,'按区域汇总实际收入。');last=self.run_task(office,'保留上轮结果，只要收入最高的一个区域。',first['id'])
  self.assertEqual(last['rows'],[['南区','1600']]);self.assertEqual(last['thread_id'],first['thread_id'])
 def test_completed_structure_work_is_shared_with_planner_and_reviewer(self):
  model=Model([CHOICE,PROGRAM,ACCEPT]);office=OfficeAgent(core.Agent(model,self.root/'data'),core)
  self.run_task(office,'按区域汇总实际收入。')
  for _,user in model.calls[1:]:
   context=json.loads(user)['已完成结构处理']
   self.assertEqual(context['state'],'completed');self.assertEqual(context['input_rows'],3)
   self.assertEqual(context['selected_tables'],1);self.assertTrue(context['header_alignment_completed'])
 def test_repair_receives_exact_failed_index_and_preserves_valid_step(self):
  program={'base':'source','operations':[{'op':'limit','count':3},{'op':'derive','name':'排序键','expression':{'column':'区域','type':'date'}}],'write':''}
  model=Model([CHOICE,program,{'edits':[{'index':1,'replace':[]}]},ACCEPT]);office=OfficeAgent(core.Agent(model,self.root/'data'),core)
  result=self.run_task(office,'列出销售明细前3条，不增加列。')
  issue=json.loads(model.calls[2][1])['前次问题'][-1]
  self.assertEqual(issue['operation_index'],1);self.assertEqual(issue['operation'],'derive')
  self.assertEqual(result['plan']['workbook']['program']['operations'],[{'op':'limit','count':3}]);self.assertEqual(len(result['rows']),3)
 def test_changed_source_requires_fresh_plan(self):
  office=OfficeAgent(core.Agent(Model([CHOICE,PROGRAM,ACCEPT]),self.root/'data'),core)
  with redirect_stdout(io.StringIO()):plan=office.draft({'prompt':'按区域汇总实际收入。','paths':[str(self.file)],'kind':'auto','adaptive':True})
  book=load_workbook(self.file);book['销售']['C5']=999;book.save(self.file);book.close()
  with self.assertRaisesRegex(ValueError,'发生变化'):office.execute({'plan_id':plan['id'],'paths':plan['paths']})
 def test_ambiguous_requirement_does_not_export_a_guess(self):
  office=OfficeAgent(core.Agent(Model([CHOICE,{'clarify':'优秀项目的判断标准是什么？'}]),self.root/'data'),core)
  with self.assertRaisesRegex(ValueError,'判断标准'):self.run_task(office,'挑出优秀项目。')
  self.assertFalse((office.agent.data/'Outputs').exists())
 def test_unrequested_writing_is_not_accepted(self):
  wrong=deepcopy(PROGRAM);wrong['write']='写一封邮件'
  office=OfficeAgent(core.Agent(Model([CHOICE,wrong,{'edits':[],'write':''},ACCEPT]),self.root/'data'),core)
  result=self.run_task(office,'按区域汇总收入。');self.assertEqual([s['tool'] for s in result['plan']['steps']],['workbook'])
 def test_cannot_disable_checked_data_step(self):
  office=OfficeAgent(core.Agent(Model([CHOICE,PROGRAM,ACCEPT]),self.root/'data'),core)
  with redirect_stdout(io.StringIO()):plan=office.draft({'prompt':'汇总收入','paths':[str(self.file)],'kind':'auto','adaptive':True})
  with self.assertRaisesRegex(ValueError,'重新检查'):office.execute({'plan_id':plan['id'],'paths':plan['paths'],'steps':[{'id':'step-1','enabled':False}]})
 def test_unrelated_sheet_with_uncached_formula_does_not_break_selected_table(self):
  book=load_workbook(self.file);book['库存']['B2']='=1+1';book.save(self.file);book.close()
  result=prepare_table(self.inspect(),CHOICE['tables']);self.assertEqual(len(result['rows']),3)
 def test_selected_formula_without_cache_cannot_be_silently_ignored(self):
  book=load_workbook(self.file);book['销售']['C5']='=1+1';book.save(self.file);book.close()
  with self.assertRaisesRegex(ValueError,'缓存'):prepare_table(self.inspect(),CHOICE['tables'])
 def test_picking_incompatible_tables_fails_with_structure_feedback(self):
  with self.assertRaisesRegex(ValueError,'字段不同'):prepare_table(self.inspect(),[{'id':'T1','header_rows':[1]}]+CHOICE['tables'])
 def test_patch_preserves_untouched_operations(self):
  source={'operations':[{'op':'select','columns':['甲']},{'op':'limit','count':2}],'base':'previous'}
  changed=patch_program(source,{'base':'source','edits':[{'index':1,'replace':[{'op':'limit','count':3}]}]})
  self.assertEqual(changed['operations'][0],source['operations'][0]);self.assertEqual(changed['base'],'source');self.assertEqual(source['operations'][1]['count'],2)
  with self.assertRaises(ValueError):patch_program(source,{'edits':[{'index':8,'replace':[]}]})
 def test_invented_threshold_cannot_silently_drop_rows(self):
  with self.assertRaisesRegex(ValueError,'阈值'):check_grounding({'operations':[{'op':'filter','where':{'column':'金额','operator':'gte','value':'999','type':'number'}}]},'只看金额大于100元')
 def test_preflight_reports_all_delivery_scope_errors_together(self):
  with self.assertRaises(ValueError) as caught:preflight({'write':'推测合计150元','operations':[{'op':'summary','metrics':[{'as':'合计'}]},{'op':'select','columns':['合计']},{'op':'write'}]},'附加合计，写简报')
  self.assertIn('write',str(caught.exception));self.assertIn('汇总',str(caught.exception));self.assertIn('operations',str(caught.exception))
 def test_planner_draft_and_paths_never_become_writer_instructions(self):
  program={'base':'source','operations':[{'op':'write','path':'/outside','content':'推测150元'}],'write':'推测150元'}
  normalized=normalize_delivery(program,'整理数据，再写一段说明，不增加交期。')
  self.assertEqual(normalized['write'],'再写一段说明，不增加交期。');self.assertEqual(normalized['operations'],[])
  self.assertEqual(patch_program({'operations':[{'op':'limit','count':2}]},{'edits':[{'index':0,'replace':None}]})['operations'],[])
  with self.assertRaises(ValueError):normalize_delivery(program,'只筛选，不要写文稿。')
  with self.assertRaises(ValueError):normalize_delivery({'operations':{}},'处理表格')
 def test_summary_references_are_delivered_in_the_summary_view(self):
  program={'operations':[{'op':'summary','metrics':[{'function':'sum','column':'金额','as':'合计'}]},{'op':'select','columns':['项目','金额','合计']}]}
  result=normalize_delivery(program,'保留明细并附加合计',['项目','金额'])
  self.assertEqual(result['operations'][1]['columns'],['项目','金额']);self.assertEqual(result['operations'][0],program['operations'][0])
 def test_explicit_output_fields_cannot_leak_filter_columns(self):
  office=OfficeAgent(core.Agent(Model([]),self.root/'data'),core)
  table={'columns':['姓名','邮箱','机构','日期'],'rows':[['甲','a@example.com','研究所','2026-10-01']],'trace':[]}
  fields=output_contract(office,'只保留姓名、邮箱。不去重。',table,{})
  self.assertEqual(fields,['姓名','邮箱']);self.assertEqual(project_result(table,fields)['rows'],[['甲','a@example.com']])
 def test_delivery_mapping_can_resolve_chinese_request_against_english_headers(self):
  office=OfficeAgent(core.Agent(Model([{'bindings':[{'requested':'参与者姓名','column':'Participant'},{'requested':'联系方式','column':'Contact'}]}]),self.root/'data'),core)
  self.assertEqual(output_contract(office,'只保留参与者姓名和联系方式。',{'columns':['Participant','Organization','Contact'],'rows':[]},{}),['Participant','Contact'])
 def test_incomplete_mapping_cannot_silently_disable_projection(self):
  for value in ({'columns':['Participant','Contact']},{'bindings':None},{'bindings':[{'requested':'参与者姓名','column':'Participant'}]}):
   with self.subTest(value=value):
    office=OfficeAgent(core.Agent(Model([value,value]),self.root/'data'),core)
    with self.assertRaises(ValueError):output_contract(office,'只保留参与者姓名和联系方式。',{'columns':['Participant','Organization','Contact'],'rows':[]},{})
 def test_generic_output_request_can_keep_existing_fields(self):
  office=OfficeAgent(core.Agent(Model([{'bindings':None}]),self.root/'data'),core)
  self.assertIsNone(output_contract(office,'只保留必要信息。',{'columns':['Participant','Contact'],'rows':[]},{}))
 def test_output_contract_does_not_treat_row_threshold_as_projection(self):
  office=OfficeAgent(core.Agent(Model([]),self.root/'data'),core)
  self.assertIsNone(output_contract(office,'只要金额不少于600元的订单。',{'columns':['金额'],'rows':[]},{}))
 def test_short_writing_request_is_not_a_global_writing_denial(self):
  normalized=normalize_delivery({'operations':[],'write':'草稿'},'写一段说明，别写太长。')
  self.assertIn('写一段说明',normalized['write'])
 def test_old_filter_context_is_available_after_upgrade(self):
  file=self.root/'费用.csv';file.write_text('部门,状态,金额\n研发,已确认,100\n行政,已确认,200\n行政,待确认,300\n')
  office=OfficeAgent(core.Agent(Model([]),self.root/'data'),core)
  with redirect_stdout(io.StringIO()):
   old=office.draft({'prompt':'只看部门等于研发且状态等于已确认','paths':[str(file)]});old=office.execute({'plan_id':old['id'],'paths':old['paths']})
  program={'base':'source','operations':[{'op':'filter','where':{'all':[{'column':'部门','operator':'eq','value':'行政'},{'column':'状态','operator':'eq','value':'已确认'}]}}],'write':''}
  model=Model([{'tables':[{'id':'T1','header_rows':[1]}]},program,ACCEPT]);office.agent.model=model
  with redirect_stdout(io.StringIO()):
   plan=office.draft({'prompt':'那行政呢？','paths':[str(file)],'parent_id':old['id'],'kind':'auto','adaptive':True});result=office.execute({'plan_id':plan['id'],'paths':plan['paths']})
  self.assertEqual(result['rows'],[['行政','已确认','200']]);self.assertIn('legacy_conditions',model.calls[1][1])

class TypedExportTests(unittest.TestCase):
 def test_editable_excel_preserves_numbers_dates_percent_identifiers_and_literals(self):
  from workbook_export import export_copies
  from datetime import datetime
  with tempfile.TemporaryDirectory() as temp:
   table={'columns':['学号','金额（元）','日期','完成率','备注'],'rows':[['00001','-12.5','2026-10-29','80%','=HYPERLINK("x")']]}
   file=Path(temp)/'result.xlsx';export_copies(file,Path(temp)/'result.csv',table,[],core.spreadsheet_value)
   book=load_workbook(file);sheet=book['处理结果']
   self.assertEqual(sheet['A2'].value,'00001');self.assertEqual(sheet['B2'].data_type,'n');self.assertEqual(sheet['B2'].value,-12.5)
   self.assertIsInstance(sheet['C2'].value,datetime);self.assertEqual(sheet['D2'].value,.8);self.assertIn('%',sheet['D2'].number_format);self.assertNotEqual(sheet['E2'].data_type,'f');book.close()
 def test_large_exact_numbers_are_not_rounded_to_excel_precision(self):
  from workbook_export import export_copies
  with tempfile.TemporaryDirectory() as temp:
   file=Path(temp)/'result.xlsx';export_copies(file,Path(temp)/'result.csv',{'columns':['金额'],'rows':[['12345678901234567890']]},[],core.spreadsheet_value)
   book=load_workbook(file);self.assertEqual(book['处理结果']['A2'].value,'12345678901234567890');book.close()

if __name__=='__main__':unittest.main()
