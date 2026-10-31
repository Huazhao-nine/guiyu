import io,json,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from table_semantics import canonical_table,quantity,describe
from table_program import TableError
from workbook_flow import TableFlow,formula,plan_actions,replay,fingerprint,freeze_finish,row_derivations
import worker as core
from office_agent import OfficeAgent


def table(columns,rows):
 return {'columns':columns,'rows':rows,'provenance':[[i] for i in range(len(rows))],'locations':[{'file':'虚构.csv','sheet':'','row':i+2} for i in range(len(rows))],'inputs':['虚构.csv'],'notes':[]}


class Model:
 info={'key':'qa','name':'QA'}
 def __init__(self,answers):self.answers=list(answers);self.calls=[];self.kwargs=[]
 def generate(self,system,user,**kw):
  try:payload=json.loads(user)
  except json.JSONDecodeError:payload=user
  self.calls.append(payload);self.kwargs.append(kw);v=self.answers.pop(0)
  return v if isinstance(v,str) else json.dumps(v,ensure_ascii=False),{'tokens':10,'seconds':.01}


class SemanticsTests(unittest.TestCase):
 def test_unit_normalization_is_idempotent_and_keeps_identifiers(self):
  source=table(['单号','合同额（万元）','到账额（元）'],[['0001','1.2','2000'],['0002','2','0']])
  c=canonical_table(source)
  self.assertEqual(c['rows'],[['0001','12000','2000'],['0002','20000','0']]);self.assertEqual(c['columns'][1],'合同额（元）')
  self.assertEqual(canonical_table(c)['rows'],c['rows']);self.assertEqual(canonical_table(c)['columns'],c['columns'])
  self.assertEqual(source['rows'][0][1],'1.2');self.assertEqual(c['field_types']['单号'],'identifier')
 def test_explicit_cell_unit_overrides_header_and_percent_roundtrip(self):
  c=canonical_table(table(['费用（万元）','进度（%）'],[['8000元','80'],['1万元','95%']]))
  self.assertEqual(c['rows'],[['8000','80%'],['10000','95%']]);self.assertEqual(canonical_table(c)['rows'],c['rows'])
 def test_english_paid_column_is_not_an_identifier(self):
  c=canonical_table(table(['OrderID','Paid','Amount (CNY 10k)'],[['901','0.2','1.2']]))
  self.assertEqual(c['field_types']['OrderID'],'identifier');self.assertEqual(c['field_types']['Paid'],'number');self.assertEqual(c['rows'][0][2],'12000')
 def test_conflicting_unit_column_stays_visible_but_not_computable(self):
  c=canonical_table(table(['姓名','金额（元）'],[['甲','100'],['乙','$50']]))
  self.assertEqual(c['rows'][1][1],'$50');self.assertEqual(c['field_types']['金额（元）'],'text');self.assertTrue(c['field_issues'])
  f=TableFlow(c,'整理姓名')
  with self.assertRaises(TableError):f.apply({'tool':'group','input':'V0','by':[],'metrics':[{'function':'sum','field':'F2','name':'合计'}]})
  f.apply({'tool':'select','input':'V0','fields':['F1']});self.assertEqual(f.views['V1']['rows'],[['甲'],['乙']])
 def test_same_canonical_title_does_not_merge_distinct_columns(self):
  c=canonical_table(table(['金额（万元）','金额（元）'],[['1','9000']]))
  self.assertEqual(len(set(c['columns'])),2);self.assertEqual(c['rows'],[['10000','9000']]);self.assertEqual(canonical_table(c)['columns'],c['columns'])
 def test_boolean_does_not_become_number(self):
  with self.assertRaises(TableError):quantity(True)
  c=canonical_table(table(['Enabled'],[['True'],['False']]))
  self.assertEqual(c['field_types']['Enabled'],'boolean');self.assertEqual(c['rows'],[['true'],['false']])
 def test_physical_quantities_convert_without_model_arithmetic(self):
  c=canonical_table(table(['重量（kg）','时长（小时）'],[['1.5','2']]))
  self.assertEqual(c['rows'],[['1500','120']]);self.assertEqual(c['columns'],['重量（g）','时长（分钟）'])


class FlowTests(unittest.TestCase):
 def setUp(self):
  self.source=table(['编号','部门','应付（元）','已付（元）','邮箱'],[['001','甲组','1200','200','a@example.com'],['002','甲组','500','0','a@example.com'],['003','乙组','400','100','b@example.com']])
 def test_formulas_cannot_call_python_or_read_attributes(self):
  for expr in ['__import__("os")','F1.__class__','F1**2','[F1][0]','True']:
   with self.subTest(expr=expr),self.assertRaises(TableError):formula(expr,lambda s:s)
 def test_branch_summary_retains_details_and_source_immutability(self):
  f=TableFlow(self.source,'计算差额并保留明细和合计')
  f.apply({'tool':'derive','input':'V0','name':'差额','formula':'F3 - F4'})
  f.apply({'tool':'group','input':'V1','by':[],'metrics':[{'function':'sum','field':'F6','name':'合计'},{'function':'count','name':'笔数'}]})
  result=f.finish({'result':'V1','summaries':['V2'],'fields':['F1','F6']},{'deliver':'both'})
  self.assertEqual(len(result['rows']),3);self.assertEqual(result['summaries'][0]['rows'],[['1800','3']]);self.assertEqual(f.views['V0']['rows'],self.source['rows'])
  with self.assertRaises(TableError):f.finish({'result':'V2','summaries':[]},{'deliver':'both'})
 def test_type_feedback_repairs_text_enums_without_numeric_guessing(self):
  f=TableFlow(table(['Person','Flag'],[['甲','OK'],['乙','PENDING']]),'找已确认的人')
  with self.assertRaisesRegex(TableError,'实际值'):f.apply({'tool':'filter','input':'V0','where':{'field':'F2','op':'eq','value':True}})
  self.assertEqual(len(f.views),1)
  f.apply({'tool':'filter','input':'V0','where':{'field':'F2','op':'eq','value':'OK'}})
  self.assertEqual(f.views['V1']['rows'],[['甲','OK']])
 def test_repeated_successful_calculation_reuses_existing_field(self):
  f=TableFlow(self.source,'计算差额');action={'tool':'derive','input':'V0','name':'差额','formula':'F3-F4'}
  f.apply(action);event=f.apply(dict(action,input='V1'));self.assertTrue(event['already_done']);self.assertEqual(len(f.graph),1)
  event=f.apply(dict(action,input='V1',name='F6'));self.assertTrue(event['already_done']);self.assertEqual(len(f.graph),1)
 def test_field_reference_comparison_does_not_parse_an_id_as_a_number(self):
  f=TableFlow(self.source,'应付高于已付')
  f.apply({'tool':'filter','input':'V0','where':{'field':'F3','op':'gt','value':'F4'}})
  self.assertEqual(len(f.views['V1']['rows']),3)
 def test_natural_column_names_default_input_and_typed_formula_are_equivalent(self):
  f=TableFlow(self.source,'计算差额')
  f.apply({'tool':'derive','name':'差额','formula':'[应付（元）]-[已付（元）]'})
  f.apply({'tool':'filter','where':{'field':'差额','op':'gt','value':0}})
  self.assertEqual(len(f.views['V2']['rows']),3)
  g=TableFlow(self.source,'计算差额');g.apply({'tool':'derive','name':'差额','formula':{'subtract':[{'column':'应付（元）'},{'column':'已付（元）'}]}})
  self.assertEqual(g.views['V1']['rows'],f.views['V1']['rows'])
 def test_numeric_reference_objects_and_missing_fields_are_validated(self):
  f=TableFlow(self.source,'应付高于已付')
  f.apply({'tool':'filter','where':{'field':'应付（元）','op':'gt','value':{'field':'已付（元）'}}})
  self.assertEqual(len(f.views['V1']['rows']),3)
  with self.assertRaises(TableError):f.resolve(f.views['V0'],None)
 def test_equivalent_condition_trees_compile_to_same_rows(self):
  forms=[{'all':[{'field':'部门','op':'eq','value':'甲组'},{'field':'应付（元）','op':'>','value':600}]},
   {'op':'and','children':[{'column':'部门','operator':'==','value':'甲组','type':'text'},{'field':'应付（元）','op':'gt','value':600}]}]
  outputs=[]
  for predicate in forms:
   f=TableFlow(self.source,'甲组且应付超过600元');f.apply({'tool':'filter','where':predicate});outputs.append(f.views['V1']['rows'])
  self.assertEqual(outputs[0],outputs[1]);self.assertEqual(len(outputs[0]),1)
 def test_metric_and_formula_aliases_remain_typed(self):
  f=TableFlow(self.source,'计算差额并统计笔数')
  f.apply({'tool':'derive','name':'差额','expression':{'op':'-','args':['应付（元）','已付（元）']}})
  f.apply({'tool':'group','by':'部门','metrics':[{'op':'count','column':'*','as':'笔数'}]})
  self.assertEqual(f.views['V2']['rows'],[['甲组','2'],['乙组','1']])
  with self.assertRaises(TableError):f.apply({'tool':'derive','name':'执行','formula':{'op':'exec','args':['x','y']}})
 def test_scalar_count_label_does_not_recalculate_values(self):
  f=TableFlow(self.source,'按部门统计人数')
  f.apply({'tool':'group','by':['部门'],'metrics':[{'function':'count','name':'人数'}]})
  r=f.finish({'display_units':{'人数':'人'}},{'deliver':'aggregate'})
  self.assertEqual(r['rows'],[['甲组','2'],['乙组','1']])
 def test_unit_bearing_threshold_uses_base_quantity_and_user_evidence(self):
  f=TableFlow(self.source,'只看应付超过0.8千元的记录')
  f.apply({'tool':'filter','input':'V0','where':{'field':'F3','op':'gt','value':'0.8千元'}})
  self.assertEqual(f.views['V1']['rows'][0][0],'001');self.assertEqual(len(f.views['V1']['rows']),1)
 def test_boolean_predicate_infers_type(self):
  f=TableFlow(table(['Active','姓名'],[['True','甲'],['False','乙']]),'找启用的记录')
  f.apply({'tool':'filter','input':'V0','where':{'field':'F1','op':'eq','value':True}})
  self.assertEqual(f.views['V1']['rows'],[['true','甲']])
 def test_units_need_no_model_conversion_factor(self):
  f=TableFlow(table(['单号','合同额（万元）','到账额（万元）'],[['A','1.2','0.2'],['B','0.6','0.1']]),'计算未结算金额，至少8000元')
  f.apply({'tool':'derive','input':'V0','name':'未结算金额','formula':'F2-F3'})
  f.apply({'tool':'filter','input':'V1','where':{'field':'F4','op':'gte','value':8000}})
  self.assertEqual(f.views['V2']['rows'][0][-1],'10000');self.assertEqual(len(f.views['V2']['rows']),1)
  with self.assertRaises(TableError):f.apply({'tool':'derive','input':'V0','name':'错误换算','formula':'F2*10000'})
 def test_dedup_first_and_group_count_use_real_rows(self):
  f=TableFlow(self.source,'按邮箱保留首次，再分组计数')
  f.apply({'tool':'distinct','input':'V0','fields':['F5']})
  f.apply({'tool':'group','input':'V1','by':['F2'],'metrics':[{'function':'count','name':'人数'}]})
  self.assertEqual(f.views['V2']['rows'],[['甲组','1'],['乙组','1']]);self.assertEqual(f.views['V1']['rows'][0][0],'001')
 def test_dedup_key_does_not_silently_include_grouping_dimension(self):
  f=TableFlow(table(['批次','登记码'],[['北','007'],['南','007'],['南','008']]),'按登记码去重，按批次统计。')
  event=f.apply({'tool':'distinct','fields':['批次','登记码']})
  self.assertEqual(event['intent_corrections'][0]['after'],['登记码'])
  f.apply({'tool':'group','by':['批次'],'metrics':[{'function':'count','name':'数量'}]})
  self.assertEqual(f.views['V2']['rows'],[['北','1'],['南','1']])
 def test_contradictory_generated_filter_keeps_source_for_repair(self):
  f=TableFlow(table(['Status'],[['ACTIVE'],['VOID']]),'排除作废记录。')
  with self.assertRaisesRegex(TableError,'互相矛盾'):f.apply({'tool':'filter','where':{'all':[{'field':'Status','op':'eq','value':'VOID'},{'field':'Status','op':'ne','value':'VOID'}]}})
  self.assertEqual(f.views['V0']['rows'],[['ACTIVE'],['VOID']]);self.assertEqual(len(f.graph),0)
  f.apply({'tool':'filter','where':{'field':'Status','op':'ne','value':'VOID'}})
  self.assertEqual(f.views['V1']['rows'],[['ACTIVE']])
 def test_literal_boundary_includes_equal_row_and_allows_independent_predicate(self):
  f=TableFlow(table(['时长（分钟）'],[['60'],['61'],['20']]),'时长不少于60分钟。')
  with self.assertRaisesRegex(TableError,'边界'):f.apply({'tool':'filter','where':{'field':'时长（分钟）','op':'gt','value':60}})
  f.apply({'tool':'filter','where':{'field':'时长（分钟）','op':'gte','value':60}})
  self.assertEqual(f.views['V1']['rows'],[['60'],['61']])
 def test_relaxed_followup_does_not_enforce_old_explicit_boundary(self):
  f=TableFlow(table(['费用（元）'],[['80'],['100']]),'改为至少80元\n费用不少于100元',current_goal='改为至少80元')
  f.apply({'tool':'filter','where':{'field':'费用（元）','op':'gte','value':80}})
  self.assertEqual(len(f.views['V1']['rows']),2)
 def test_global_summary_cannot_be_replaced_by_one_group_per_item(self):
  f=TableFlow(self.source,'明细和这批记录的金额合计')
  f.apply({'tool':'group','by':['编号'],'metrics':[{'function':'sum','field':'应付（元）','name':'合计'}]})
  contract={'deliver':'both','global_summary':True}
  with self.assertRaisesRegex(TableError,'整批合计'):f.finish({'result':'V0','summaries':['V1']},contract)
  f.apply({'tool':'group','input':'V0','by':[],'metrics':[{'function':'sum','field':'应付（元）','name':'合计'}]})
  self.assertEqual(f.finish({'result':'V0','summaries':['V2']},contract)['summaries'][0]['rows'],[['2100']])
 def test_logic_condition_alias_has_same_typed_result(self):
  f=TableFlow(self.source,'只看甲组')
  f.apply({'tool':'filter','where':{'logic':'and','conditions':[{'field':'部门','op':'eq','value':'甲组'},{'field':'应付（元）','op':'gt','value':0}]}})
  self.assertEqual(len(f.views['V1']['rows']),2)
 def test_redundant_field_on_negation_is_only_accepted_when_consistent(self):
  f=TableFlow(self.source,'排除甲组')
  f.apply({'tool':'filter','where':{'field':'部门','op':'not','children':[{'field':'部门','op':'eq','value':'甲组'}]}})
  self.assertEqual(f.views['V1']['rows'],[self.source['rows'][2]])
  with self.assertRaisesRegex(TableError,'不一致'):f.apply({'tool':'filter','input':'V0','where':{'field':'部门','op':'not','children':[{'field':'编号','op':'eq','value':'001'}]}})
 def test_empty_results_keep_numeric_and_date_types(self):
  f=TableFlow(table(['日期','数额（元）'],[['2026-10-02','100']]),'只看大于200元')
  f.apply({'tool':'filter','input':'V0','where':{'field':'F2','op':'gt','value':200}})
  f.apply({'tool':'sort','input':'V1','by':[{'field':'F1','direction':'asc'}]})
  f.apply({'tool':'group','input':'V2','by':[],'metrics':[{'function':'count','name':'笔数'}]})
  self.assertEqual(f.views['V3']['rows'],[['0']])
 def test_replay_matches_checked_branch_delivery(self):
  f=TableFlow(self.source,'合计并保留明细')
  f.apply({'tool':'group','input':'V0','by':[],'metrics':[{'function':'sum','field':'F3','name':'合计'}]})
  finish={'result':'V0','summaries':['V1'],'fields':['F1','F3']};contract={'deliver':'both'};result=f.finish(finish,contract)
  config={'flow':{'graph':f.graph,'finish':finish,'contract':contract,'expected':fingerprint(result)}}
  self.assertEqual(replay(self.source,config)['rows'],result['rows'])
  config['flow']['graph'][0]['operation']['metrics'][0]['function']='mean'
  with self.assertRaises(TableError):replay(self.source,config)
 def test_delivery_ir_survives_temporary_field_registry_changes(self):
  f=TableFlow(self.source,'计算差额');f.registry['临时预览字段']='F6'
  f.apply({'tool':'derive','name':'差额','formula':'[应付（元）]-[已付（元）]'})
  fid=f.registry['差额（元）'];finish={'result':'V1','summaries':[],'fields':['F1',fid]};contract={'deliver':'detail'};result=f.finish(finish,contract)
  config={'flow':{'graph':f.graph,'finish':freeze_finish(f,finish),'contract':contract,'expected':fingerprint(result)}}
  self.assertEqual(replay(self.source,config)['rows'],result['rows'])
 def test_output_unit_is_separate_from_arithmetic_and_reusable(self):
  f=TableFlow(table(['金额（元）'],[['1'],['12000']]),'改为万元展示')
  result=f.finish({'result':'V0','summaries':[],'display_units':{'F1':'万元'}},{'deliver':'detail'})
  self.assertEqual(result['rows'],[['0.0001'],['1.2']]);self.assertEqual(f.views['V0']['rows'],[['1'],['12000']])
  self.assertEqual(canonical_table(result)['rows'],[['1'],['12000']])
 def test_percent_mean_retains_percent_semantics(self):
  f=TableFlow(table(['完成率（%）'],[['87'],['88']]),'计算平均完成率')
  f.apply({'tool':'group','input':'V0','by':[],'metrics':[{'function':'mean','field':'F1','name':'平均完成率'}]})
  self.assertEqual(f.views['V1']['rows'],[['87.5%']]);self.assertEqual(f.views['V1']['field_types']['平均完成率（%）'],'percent')
 def test_unknown_top_level_conditions_cannot_be_silently_ignored(self):
  f=TableFlow(self.source,'只看甲组且金额大于1000元')
  with self.assertRaisesRegex(TableError,'不接受参数'):f.apply({'tool':'filter','where':{'field':'部门','op':'eq','value':'甲组'},'unrecognized_condition':[{'field':'应付（元）','op':'gt','value':1000}]})
  self.assertEqual(len(f.views),1)
 def test_delivery_candidate_waits_for_summary_and_preserves_detail(self):
  f=TableFlow(self.source,'按部门汇总应付金额，保留明细');contract={'deliver':'both','preserve_detail':True}
  self.assertIsNone(f.delivery_candidate(contract,f.goal))
  f.apply({'tool':'group','by':['部门'],'metrics':[{'function':'sum','field':'应付（元）','name':'金额合计'}]})
  candidate=f.delivery_candidate(contract,f.goal)
  self.assertEqual(candidate['result'],'V0');self.assertEqual(candidate['summaries'],['V1'])
 def test_display_unit_handoff_and_replay_cover_aggregate_values(self):
  source=table(['站点','时长（小时）'],[['甲','1.5'],['甲','2']]);f=TableFlow(source,'按站点汇总时长，以小时显示。')
  f.apply({'tool':'group','by':['站点'],'metrics':[{'function':'sum','field':'时长（分钟）','name':'时数'}]})
  contract={'deliver':'aggregate'};finish=f.delivery_candidate(contract,f.goal);result=f.finish(finish,contract)
  self.assertEqual(result['rows'],[['甲','3.5']])
  config={'flow':{'graph':f.graph,'finish':freeze_finish(f,finish),'contract':contract,'expected':fingerprint(result)}}
  self.assertEqual(replay(source,config)['rows'],result['rows'])
 def test_summary_display_units_do_not_change_detail_arithmetic(self):
  f=TableFlow(self.source,'保留明细和总计')
  f.apply({'tool':'group','by':[],'metrics':[{'function':'sum','field':'应付（元）','name':'总计'}]})
  result=f.finish({'result':'V0','summaries':['V1'],'display_units':{'总计（元）':'万元'}},{'deliver':'both'})
  self.assertEqual(result['summaries'][0]['rows'],[['0.21']]);self.assertEqual(result['rows'][0][2],'1200')
 def test_followup_rebuilds_dependency_chain_on_all_original_rows(self):
  source=table(['货号','计划数量','已有数量','单价（元）'],[['A','10','8','5'],['B','6','2','8']])
  old=TableFlow(source,'计算缺量和金额，金额不少于30元')
  old.apply({'tool':'derive','name':'缺量','formula':'[计划数量]-[已有数量]'})
  old.apply({'tool':'derive','name':'金额','formula':'[缺量]*[单价（元）]'})
  old.apply({'tool':'filter','where':{'field':'金额','op':'gte','value':30}})
  previous=old.finish({'fields':['货号','金额']},{'deliver':'detail'})
  f=TableFlow(source,'金额不少于10元',previous,recipes=row_derivations(old.graph),previous_shape='detail')
  f.apply({'tool':'filter','input':'V0','where':{'field':'金额','op':'gte','value':10}})
  finish={'result':f.last,'fields':['货号','金额']};result=f.finish(finish,{'deliver':'detail'})
  self.assertEqual(result['rows'],[['A','10'],['B','32']]);self.assertEqual(len(previous['rows']),1)
  self.assertEqual([s['operation']['op'] for s in f.graph],['derive','derive','filter'])
  self.assertTrue(all(s['restored_row_calculation'] for s in f.graph[:2]))
  config={'previous_result':previous,'previous_shape':'detail','flow':{'graph':f.graph,'finish':freeze_finish(f,finish),'contract':{'deliver':'detail'},'expected':fingerprint(result)}}
  self.assertEqual(replay(source,config)['rows'],result['rows']);self.assertEqual(source['rows'][0][-1],'5')
 def test_aggregate_calculations_never_become_row_recipes(self):
  f=TableFlow(self.source,'应付合计再乘2')
  f.apply({'tool':'group','by':[],'metrics':[{'function':'sum','field':'应付（元）','name':'合计'}]})
  f.apply({'tool':'derive','name':'两倍合计','formula':'[合计（元）]*2'})
  self.assertEqual(row_derivations(f.graph),[])
 def test_new_calculation_takes_precedence_over_inherited_recipe(self):
  old=TableFlow(self.source,'计算差额');old.apply({'tool':'derive','name':'差额','formula':'[应付（元）]-[已付（元）]'})
  f=TableFlow(self.source,'公式改成应付加已付',recipes=row_derivations(old.graph))
  f.apply({'tool':'derive','name':'差额','formula':'[应付（元）]+[已付（元）]'})
  self.assertEqual(f.views[f.last]['rows'][0][-1],'1400');self.assertNotIn('restored_row_calculation',f.graph[0])
  self.assertEqual(row_derivations(f.graph,row_derivations(old.graph))[0]['expression'],f.graph[0]['operation']['expression'])
 def test_recipe_cycles_do_not_modify_any_view(self):
  recipes=[{'op':'derive','name':'X','expression':{'column':'Y'},'format':'number'}, {'op':'derive','name':'Y','expression':{'column':'X'},'format':'number'}]
  f=TableFlow(self.source,'X大于0',recipes=recipes)
  with self.assertRaises(TableError):f.apply({'tool':'filter','where':{'field':'X','op':'gt','value':0}})
  self.assertEqual(len(f.views),1);self.assertEqual(len(f.graph),0)
 def test_numeric_percent_scale_uses_explicit_goal_and_keeps_boundary(self):
  source=table(['进度（%）'],[['62'],['63'],['64']])
  for value in [63,.63,'63%']:
   f=TableFlow(source,'进度不少于63%')
   f.apply({'tool':'filter','where':{'field':'进度','op':'gte','value':value}})
   self.assertEqual(f.views[f.last]['rows'],[['63%'],['64%']])
  with self.assertRaisesRegex(TableError,'边界'):f.apply({'tool':'filter','input':'V0','where':{'field':'进度','op':'gt','value':.63}})
  from workbook_intent import explicit_percent
  with self.assertRaises(TableError):explicit_percent(1,'1%或100%')
  with self.assertRaises(TableError):explicit_percent('sNaN','63%')
 def test_parameter_envelopes_remain_typed_and_conflicts_stop(self):
  f=TableFlow(self.source,'计算差额')
  f.apply({'tool':'derive','arguments':{'name':'差额','formula':'[应付（元）]-[已付（元）]'}})
  self.assertEqual(f.views[f.last]['rows'][0][-1],'1000')
  with self.assertRaises(TableError):f.apply({'tool':'filter','parameters':{'tool':'exec','where':{}}})
 def test_equivalent_logical_locations_keep_every_condition(self):
  from workbook_intent import normalize_action
  a={'field':'部门','op':'eq','value':'甲组'};b={'field':'应付（元）','op':'gte','value':1000}
  actions=[{'tool':'filter','where':{'all':[a,b]}},{'tool':'filter','where':a,'and':[b]}, {'tool':'filter','all':[a,b]}, {'tool':'filter','where':dict(a,all=[b])}]
  for action in actions:
   f=TableFlow(self.source,'甲组且应付不少于1000元');f.apply(action)
   self.assertEqual(f.views[f.last]['rows'],[self.source['rows'][0]])
  with self.assertRaises(TableError):normalize_action({'tool':'filter','where':a,'and':[b],'or':[b]})
 def test_explicitly_forbidden_operation_is_not_required_or_executed(self):
  from workbook_intent import required_operations
  self.assertNotIn('distinct',required_operations('按部门筛选，不去重。'))
  f=TableFlow(self.source,'只保留甲组，不去重')
  with self.assertRaisesRegex(TableError,'明确要求'):f.apply({'tool':'distinct','fields':['邮箱']})
  self.assertEqual(len(f.graph),0)
  f=TableFlow(self.source,'不要按部门去重，按邮箱去重。')
  f.apply({'tool':'distinct','fields':['邮箱']});self.assertEqual(len(f.views[f.last]['rows']),2)
 def test_negated_numeric_condition_is_not_bound_as_positive_threshold(self):
  f=TableFlow(table(['费用（元）'],[['50'],['150']]),'排除费用高于100元的记录')
  f.apply({'tool':'filter','where':{'field':'费用（元）','op':'lte','value':100}})
  self.assertEqual(f.views[f.last]['rows'],[['50']])
 def test_view_classification_cannot_block_a_complete_ranked_detail(self):
  f=TableFlow(self.source,'只取前1笔');f.apply({'tool':'limit','count':1})
  candidate=f.delivery_candidate({'deliver':'aggregate'},f.goal)
  self.assertEqual(candidate['result'],'V1');self.assertEqual(candidate['summaries'],[])
 def test_excluding_header_partition_cannot_invent_row_value_conditions(self):
  source=table(['项目','旧方案 / 成本（元）','新方案 / 成本（元）'],[['A','20','40'],['B','0','100']])
  f=TableFlow(source,'只统计新方案成本，不把旧方案数据算进去')
  for predicate in [{'field':'旧方案 / 成本（元）','op':'eq','value':0},{'field':'旧方案 / 成本（元）','op':'is_empty'}]:
   with self.assertRaisesRegex(TableError,'统计列范围'):f.apply({'tool':'filter','where':predicate})
  self.assertEqual(len(f.graph),0)
  f.apply({'tool':'group','by':[],'metrics':[{'function':'sum','field':'新方案 / 成本（元）','name':'合计'}]})
  self.assertEqual(f.views[f.last]['rows'],[['140']])
  g=TableFlow(source,'排除旧方案成本为0的项目，汇总新方案成本')
  g.apply({'tool':'filter','where':{'field':'旧方案 / 成本（元）','op':'ne','value':0}})
  self.assertEqual(g.views[g.last]['rows'],[source['rows'][0]])
 def test_explicit_excluded_values_are_checked_in_detail_and_summary_lineage(self):
  from workbook_intent import literal_exclusions
  source=table(['项目','处理类别','金额（元）'],[['A','有效','20'],['B','关闭','30']])
  f=TableFlow(source,'不含关闭记录，汇总金额')
  contract={'deliver':'aggregate','excluded_values':literal_exclusions(f.goal,f.views['V0'])}
  f.apply({'tool':'group','by':[],'metrics':[{'function':'sum','field':'金额（元）','name':'合计'}]})
  with self.assertRaisesRegex(TableError,'尚未落实'):f.finish({'result':'V1'},contract)
  f.apply({'tool':'filter','input':'V0','where':{'field':'处理类别','op':'ne','value':'关闭'}})
  f.apply({'tool':'group','by':[],'metrics':[{'function':'sum','field':'金额（元）','name':'合计'}]})
  self.assertEqual(f.finish({'result':f.last},contract)['rows'],[['20']])
 def test_exclusion_compiler_does_not_reverse_a_negated_instruction(self):
  from workbook_intent import literal_exclusions
  source=table(['处理类别'],[['关闭'],['未关闭']]);source=__import__('table_semantics').canonical_table(source)
  self.assertEqual(literal_exclusions('不必排除关闭',source),[])
  rules=literal_exclusions('排除未关闭',source);self.assertEqual([r['value'] for r in rules],['未关闭'])
  self.assertEqual(literal_exclusions('把未关闭也算上，其他不变',source,rules),[])
 def test_replanning_current_task_can_reuse_an_already_verified_row_formula(self):
  f=TableFlow(self.source,'计算差额并筛选甲组')
  f.apply({'tool':'derive','name':'差额','formula':'[应付（元）]-[已付（元）]'})
  f.apply({'tool':'filter','input':'V0','where':{'field':'部门','op':'eq','value':'甲组'}})
  f.apply({'tool':'sort','by':[{'field':'差额','direction':'desc'}]})
  self.assertEqual(f.views[f.last]['rows'][0][-1],'1000')
  self.assertTrue(f.graph[-2]['restored_row_calculation'])
 def test_numeric_field_comparison_can_use_the_real_field_name(self):
  f=TableFlow(self.source,'找出应付高于已付的记录')
  f.apply({'tool':'filter','where':{'field':'应付（元）','op':'gt','value':'已付（元）'}})
  self.assertEqual(len(f.views[f.last]['rows']),3)
 def test_aggregate_keeps_its_view_when_source_condition_already_holds(self):
  source=table(['部门','状态','邮箱'],[['甲','启用','a'],['甲','暂停','b'],['乙','启用','c']])
  f=TableFlow(source,'排除暂停和邮箱为空，汇总人数')
  f.apply({'tool':'filter','where':{'all':[{'field':'状态','op':'ne','value':'暂停'},{'field':'邮箱','op':'not_empty'}]}})
  f.apply({'tool':'group','by':['部门'],'metrics':[{'function':'count','name':'人数'}]})
  event=f.apply({'tool':'filter','where':{'field':'状态','op':'ne','value':'暂停'}})
  self.assertTrue(event['already_done']);self.assertEqual(f.last,'V2');self.assertEqual(len(f.graph),2)
 def test_or_condition_cannot_be_mistaken_for_an_individual_conjunct(self):
  source=table(['部门','状态'],[['甲','暂停'],['乙','启用']]);f=TableFlow(source,'按部门统计')
  f.apply({'tool':'filter','where':{'any':[{'field':'部门','op':'eq','value':'甲'},{'field':'状态','op':'ne','value':'暂停'}]}})
  f.apply({'tool':'group','by':['部门'],'metrics':[{'function':'count','name':'人数'}]})
  with self.assertRaises(TableError):f.apply({'tool':'filter','where':{'field':'状态','op':'ne','value':'暂停'}})
  self.assertEqual(f.last,'V2')
 def test_sort_reuses_unique_matching_summary_without_widening_source_rows(self):
  source=table(['部门','状态'],[['A','启用'],['A','暂停'],['B','启用']]);f=TableFlow(source,'排除暂停后按人数排序')
  f.apply({'tool':'filter','where':{'field':'状态','op':'ne','value':'暂停'}})
  f.apply({'tool':'group','by':['部门'],'metrics':[{'function':'count','name':'人数'}]})
  f.apply({'tool':'sort','input':'V1','by':[{'field':'人数','direction':'desc'},{'field':'部门','direction':'asc'}]})
  self.assertEqual(f.graph[-1]['input'],'V2');self.assertEqual(f.views[f.last]['rows'],[['A','1'],['B','1']])
  g=TableFlow(source,'按人数排序');g.apply({'tool':'group','by':['部门'],'metrics':[{'function':'count','name':'人数'}]})
  g.apply({'tool':'filter','input':'V0','where':{'field':'状态','op':'ne','value':'暂停'}})
  with self.assertRaises(TableError):g.apply({'tool':'sort','by':[{'field':'人数','direction':'desc'}]})


class AgentFlowTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def office(self,answers):
  office=OfficeAgent(core.Agent(Model(answers),self.root/'data'),core);office.workbook_metrics={'tokens':0,'peak_memory_gb':0};return office
 def test_review_cannot_add_dedup_requirement_to_a_valid_result(self):
  office=self.office([{'title':'记录','deliver':'detail','detail_request':''},{'tool':'finish','result':'V0'},
    {'state':'missing','requirement_index':0,'next':'按编号去重，只保留一条'},{'state':'passed'}])
  with redirect_stdout(io.StringIO()):flow,_,_,result,_=plan_actions(office,table(['编号','金额'],[['A','10'],['A','20']]),'整理这些记录。')
  self.assertEqual(len(result['rows']),2);self.assertEqual(flow.graph,[])
  self.assertIn('上次复核问题',office.agent.model.calls[-1])
 def test_keep_first_record_is_not_an_output_column_request(self):
  from workbook_agent import output_contract
  self.assertIsNone(output_contract(self.office([]),'按邮箱去重、保留首次记录，再按部门统计。',table(['部门','邮箱'],[['甲','a@example.com']]),{}))
 def test_extra_summary_is_not_misread_as_detail_output_columns(self):
  from workbook_agent import output_contract
  result=table(['品号','数量','费用（元）'],[['X','2','40']])
  self.assertEqual(output_contract(self.office([]),'保留品号、数量、费用，附加这批费用合计和记录数，同时保留明细。',result,{}),result['columns'])
 def test_followup_preserves_requested_columns_with_natural_retention_phrase(self):
  from workbook_agent import output_contract
  previous={'program':{'output_columns':['项目','金额（万元）']}}
  current=table(['项目','状态','金额（元）','内部备注'],[['A','OK','10000','私密']])
  self.assertEqual(output_contract(self.office([]),'把门槛改为2000元，其余要求不变。',current,previous),['项目','金额（元）'])
  self.assertEqual(output_contract(self.office([]),'其他要求不变，只保留项目。',current,previous),['项目'])
 def test_followup_preserves_word_and_detail_contract_but_can_cancel_word(self):
  previous={'deliver':'both','preserve_detail':True,'global_summary':True,'docx':True,'write':'写一段说明并导出Word。'}
  for suffix,docx in [('',True),('不要Word。',False)]:
   office=self.office([{'title':'更新','deliver':'detail','write':''},{'tool':'finish','result':'V0','summaries':['V1']},{'state':'passed'}])
   # Supply a real branch through the tool loop, rather than synthesizing a result.
   office.agent.model.answers.insert(1,{'tool':'group','input':'V0','by':[],'metrics':[{'function':'sum','field':'金额（元）','name':'合计'}]})
   with redirect_stdout(io.StringIO()):_,contract,_,_,_=plan_actions(office,table(['项目','金额（元）'],[['A','40']]),'其他要求不变。'+suffix,previous_goal='保留明细并附加这批金额合计，写一段说明并导出Word。',previous_contract=previous)
   self.assertEqual(contract['deliver'],'both');self.assertTrue(contract['write']);self.assertEqual(contract['docx'],docx)
 def test_duplicate_json_parameters_cannot_overwrite_a_prior_action(self):
  from workbook_intent import strict_action_json,validate_action
  with self.assertRaises(TableError):strict_action_json('{"tool":"derive","name":"余额","name":"合计"}')
  for action in [{'tool':'sort','by':[1]},{'tool':'finish','display_units':[]}]:
   with self.assertRaises(TableError):validate_action(action)
 def test_unparsed_action_is_returned_to_model_for_specific_repair(self):
  invalid='{"tool":"derive","name":"差额","formula":"[收入]-[费用]","name":"比例","formula":"[差额]/[收入]"}'
  office=self.office([{'title':'差额','deliver':'detail','write':''},invalid,{'tool':'derive','name':'差额','formula':'[收入]-[费用]'}, {'tool':'finish','result':'V1'},{'state':'passed'}])
  with redirect_stdout(io.StringIO()):flow,_,_,result,failures=plan_actions(office,table(['收入','费用'],[['90','40']]),'计算差额')
  self.assertEqual(result['rows'],[['90','40','50']]);self.assertEqual(len(failures),1);self.assertEqual(len(flow.graph),1)
  self.assertEqual(office.agent.model.kwargs[2]['history'],[])
  feedback=office.agent.model.calls[2]['待修正动作']
  self.assertEqual(feedback['invalid_action'],invalid);self.assertIn('先算依赖字段',feedback['error'])
 def test_delivery_contract_json_failure_gets_one_bounded_local_retry(self):
  office=self.office(['{"title":"说明"字段","deliver":"detail"}',{'title':'说明','deliver':'detail','detail_request':''},{'tool':'finish','result':'V0'},{'state':'passed'}])
  with redirect_stdout(io.StringIO()):_,_,_,result,_=plan_actions(office,table(['事项'],[['A']]),'整理这份记录')
  self.assertEqual(result['rows'],[['A']]);self.assertIn('前次格式问题',office.agent.model.calls[1])
 def test_local_syntax_repair_preserves_all_field_and_value_tokens(self):
  from workbook_flow import ask
  bad='{"tool":"derive","name":"差额","formula":"[收入]-[费用]"]}'
  good={'tool':'derive','name':'差额','formula':'[收入]-[费用]'}
  office=self.office([bad,good])
  with redirect_stdout(io.StringIO()):result=ask(office,'返回一个动作',{},500)
  self.assertEqual(result,good);self.assertEqual(office.workbook_metrics['format_repairs'],1)
  bad='{"tool":"derive" "name":"差额","formula":"[收入]-[费用]"}'
  office=self.office([bad,dict(good,formula='[收入]+[费用]')])
  with redirect_stdout(io.StringIO()):fixed=ask(office,'返回一个动作',{},500)
  self.assertEqual(fixed,good);self.assertEqual(len(office.agent.model.calls),1)
 def test_format_repair_cannot_add_or_remove_conditions_or_values(self):
  from workbook_intent import json_scalar_sequence
  self.assertEqual(json_scalar_sequence('{"a":0,"b":[true,null]]}'),json_scalar_sequence('{"a":0,"b":[true,null]}'))
  self.assertNotEqual(json_scalar_sequence('{"a":0}'),json_scalar_sequence('{"a":1}'))
  with self.assertRaises((ValueError,TableError)):json_scalar_sequence('{"a":"未转义"内容"}')
 def test_schema_grounded_missing_reference_bracket_is_recoverable(self):
  f=TableFlow(table(['收入','费用'],[['90','40']]),'计算差额')
  f.apply({'tool':'derive','name':'差额','formula':'[收入]-[费用'})
  self.assertEqual(f.views[f.last]['rows'],[['90','40','50']])
  with self.assertRaises(TableError):f.apply({'tool':'derive','input':'V0','name':'未知','formula':'[收入]-[不存在'})
 def test_stray_closer_fix_preserves_real_arrays_and_every_scalar(self):
  from workbook_intent import remove_stray_json_closers,json_scalar_sequence
  raw='{"tool":"filter","where":{"all":[{"field":"A","op":"eq","value":3}]}}]}'
  fixed=remove_stray_json_closers(raw)
  self.assertEqual(json_scalar_sequence(fixed),json_scalar_sequence(raw))
  self.assertEqual(json.loads(fixed)['where']['all'][0]['value'],3)
  with self.assertRaises(TableError):remove_stray_json_closers('{"a":[1}')
 def test_only_one_tool_object_is_executed_and_invented_tail_metadata_is_ignored(self):
  from workbook_intent import strict_action_json
  action={'tool':'filter','where':{'field':'部门','op':'eq','value':'甲组'}}
  raw=json.dumps(action,ensure_ascii=False)+', "input_status": {"rows":999,"notes":["模型自称完成"]}'
  parsed=strict_action_json(raw);self.assertEqual(parsed,action)
  f=TableFlow(table(['部门'],[['甲组'],['乙组']]),'只看甲组');f.apply(parsed)
  self.assertEqual(f.views[f.last]['rows'],[['甲组']])
  with self.assertRaises(TableError):strict_action_json(json.dumps(action)+json.dumps({'tool':'limit','count':1}))
 def test_negative_requirement_is_enforced_rather_than_sent_as_a_missing_step(self):
  office=self.office([{'title':'名单','deliver':'detail','detail_request':''},{'tool':'finish','result':'V0'},{'state':'passed'}])
  with redirect_stdout(io.StringIO()):_,contract,_,result,_=plan_actions(office,table(['人名'],[['甲'],['甲']]),'保留名单。不去重。')
  self.assertEqual(result['rows'],[['甲'],['甲']]);self.assertEqual(contract['requirements'],['保留名单'])
  self.assertIn('distinct',contract['enforced_restrictions'])
 def test_unspecified_business_standard_stops_before_data_actions(self):
  from workbook_agent import Clarification
  path=self.root/'供货记录.csv';path.write_text('承包商,金额\n甲,100\n乙,200\n')
  office=self.office([{'tables':[{'id':'T1','header_rows':[1]}]}])
  with redirect_stdout(io.StringIO()),self.assertRaises(Clarification):office.draft({'prompt':'挑出最佳承包商','paths':[str(path)],'kind':'auto','adaptive':True,'workbook_mode':'flow'})
  self.assertEqual(len(office.agent.model.calls),1);self.assertFalse((self.root/'data/Outputs').exists())
 def test_local_recovery_preserves_successful_views(self):
  contract={'title':'名单','deliver':'detail','write':'','requirements':['查找已确认的记录']}
  office=self.office([contract,{'tool':'filter','input':'V0','where':{'field':'F2','op':'eq','value':True}}, {'tool':'filter','input':'V0','where':{'field':'F2','op':'eq','value':'OK'}},{'tool':'finish','result':'V1','summaries':[],'fields':['F1']},{'state':'passed'}])
  with redirect_stdout(io.StringIO()):flow,_,_,result,failures=plan_actions(office,table(['Person','Flag'],[['甲','OK'],['乙','PENDING']]),'查找已确认的记录')
  self.assertEqual(result['rows'],[['甲']]);self.assertEqual(len(failures),1);self.assertEqual(len(flow.graph),1)
  self.assertIn('实际值',office.agent.model.calls[2]['待修正动作']['error'])
  self.assertEqual(office.agent.model.kwargs[2]['history'],[])
  self.assertEqual(office.agent.model.calls[2]['待修正动作']['action']['where']['value'],True)
 def test_finish_protects_explicit_output_fields(self):
  office=self.office([{'title':'提取','deliver':'detail','write':'','requirements':[]},{'tool':'finish','result':'V0','summaries':[]},{'state':'passed'}])
  with redirect_stdout(io.StringIO()):_,_,finish,result,_=plan_actions(office,table(['姓名','邮箱','内部备注'],[['甲','a@example.com','私密']]),'只保留姓名、邮箱。')
  self.assertEqual(result['columns'],['姓名','邮箱']);self.assertEqual(finish['fields'],['姓名','邮箱'])
 def test_explicit_word_export_is_a_required_delivery(self):
  office=self.office([{'title':'说明','deliver':'detail','write':'','requirements':[]},{'tool':'finish','result':'V0','summaries':[]},{'state':'passed'}])
  with redirect_stdout(io.StringIO()):_,contract,_,_,_=plan_actions(office,table(['姓名'],[['甲']]),'整理这些名单，导出Word。')
  self.assertEqual(contract['write'],'导出Word。')
 def test_short_style_constraint_does_not_cancel_writing(self):
  office=self.office([{'title':'说明','deliver':'detail','write':'简短说明','requirements':[]},{'tool':'finish','result':'V0','summaries':[]},{'state':'passed'}])
  with redirect_stdout(io.StringIO()):_,contract,_,_,_=plan_actions(office,table(['事项'],[['A']]),'写一段说明，别写太长。')
  self.assertIn('写一段说明',contract['write']);self.assertTrue(contract['docx'])
 def test_no_word_keeps_requested_text_without_docx(self):
  office=self.office([{'title':'说明','deliver':'detail','write':'说明','requirements':[]},{'tool':'finish','result':'V0','summaries':[]},{'state':'passed'}])
  with redirect_stdout(io.StringIO()):_,contract,_,_,_=plan_actions(office,table(['事项'],[['A']]),'写一段说明，不要Word。')
  self.assertTrue(contract['write']);self.assertFalse(contract['docx'])
 def test_writer_instructions_are_bound_to_the_user_even_when_model_paraphrases(self):
  office=self.office([{'title':'说明','deliver':'detail','write':'推测合计并立即付款','requirements':[]},{'tool':'finish','result':'V0','summaries':[]},{'state':'passed'}])
  with redirect_stdout(io.StringIO()):_,contract,_,_,_=plan_actions(office,table(['事项'],[['A']]),'写一段简短说明并导出Word，不新增付款结论。')
  self.assertEqual(contract['write'],'写一段简短说明并导出Word，不新增付款结论。')
 def test_office_flow_exports_details_summary_and_word_and_preserves_source(self):
  path=self.root/'结算.csv';path.write_text('项目,费用（万元）,已付（元）\nA,0.2,1000\nB,0.3,1000\n')
  goal='计算未付金额，只保留项目、未付金额，同时保留明细并附加合计，再写一段说明并导出Word。'
  answers=[{'tables':[{'id':'T1','header_rows':[1]}]},
   {'title':'结算核对','deliver':'both','write':'写一段说明并导出Word。','requirements':[]},
   {'tool':'derive','input':'V0','name':'未付金额','formula':'F2-F3'},
   {'tool':'group','input':'V1','by':[],'metrics':[{'function':'sum','field':'F4','name':'合计'}]},
   {'state':'passed'},
   {'title':'结算说明','facts':['COUNT','S1_1']}]
  office=self.office(answers);before=core.digest(path)
  with redirect_stdout(io.StringIO()):
   plan=office.draft({'prompt':goal,'paths':[str(path)],'kind':'auto','adaptive':True,'workbook_mode':'flow'})
   result=office.execute({'plan_id':plan['id'],'paths':plan['paths']})
  self.assertEqual(result['rows'],[['A','1000'],['B','2000']]);self.assertEqual(core.digest(path),before)
  self.assertEqual({a['type'] for a in result['artifacts']},{'xlsx','csv','docx','md'});self.assertEqual(result['plan']['completion_check']['state'],'passed')
  from docx import Document
  word=next(a['path'] for a in result['artifacts'] if a['type']=='docx')
  self.assertIn('3000', '\n'.join(p.text for p in Document(word).paragraphs))
  office.agent.model.answers.extend([{'title':'结算说明','facts':['COUNT','S1_1']}])
  with redirect_stdout(io.StringIO()):
   updated=office.draft({'prompt':'只看未付金额不少于1500元，其他要求不变。','paths':plan['paths'],'parent_id':result['id'],'kind':'auto','adaptive':True,'workbook_mode':'flow'})
   final=office.execute({'plan_id':updated['id'],'paths':updated['paths']})
  self.assertEqual(final['rows'],[['B','2000']]);self.assertEqual(core.digest(path),before)
  self.assertEqual(updated['workbook']['flow']['graph'][0]['operation']['op'],'derive')
  self.assertTrue(updated['workbook']['flow']['contract']['revision']['literal_compiler'])
  self.assertTrue(any(a['type']=='docx' for a in final['artifacts']))


if __name__=='__main__':unittest.main()
