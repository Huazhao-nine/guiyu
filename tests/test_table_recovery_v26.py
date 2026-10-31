"""Recovery invariants, using data independent of the model evaluation files."""
import sys,unittest
import json
from types import SimpleNamespace
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from workbook_flow import TableFlow
from workbook_intent import check_predicate
from table_program import TableError

class RecoveryTests(unittest.TestCase):
    def test_rejects_interval_contradiction_but_does_not_flatten_or(self):
        def atom(op,value,kind='number'):return {'column':'指标','operator':op,'value':value,'type':kind}
        for a,b in [(atom('eq',7),atom('gt',7)),(atom('gte',10),atom('lt',8)),
                    (atom('gte','2029-06-05','date'),atom('lt','2029-06-04','date'))]:
            with self.subTest(a=a,b=b),self.assertRaises(TableError):check_predicate({'all':[a,b]})
        check_predicate({'all':[atom('gte',8),atom('lte',8)]})
        check_predicate({'any':[atom('eq',7),atom('gt',7)]})
        check_predicate({'all':[atom('gte',8),{'any':[atom('lt',8),atom('gt',10)]}]})

    def test_wrong_subset_returns_retry_input_without_destroying_views(self):
        f=TableFlow({'columns':['分数'],'rows':[['0'],['8'],['15']]},'排除零分，其他规则不变。')
        f.apply({'tool':'filter','where':{'field':'分数','op':'eq','value':0}})
        before=deepcopy(f.views)
        with self.assertRaisesRegex(TableError,'退回.*V0'):
            f.apply({'tool':'filter','where':{'field':'分数','op':'gt','value':0}})
        self.assertEqual(f.views,before)
        result=f.apply({'tool':'filter','input':'V0','where':{'field':'分数','op':'gt','value':0}})
        self.assertEqual(f.views[result['view']]['rows'],[['8'],['15']])

    def test_ancestry_facts_stop_at_replaced_field_and_group(self):
        f=TableFlow({'columns':['指标'],'rows':[['0'],['3']]},'重新计算指标，指标加10，汇总后大于5。')
        f.record('V0',{'op':'filter','where':{'column':'指标','operator':'eq','value':0,'type':'number'}})
        f.apply({'tool':'derive','name':'指标','formula':{'add':[{'column':'指标'},{'constant':10}]}})
        e=f.apply({'tool':'filter','where':{'field':'指标','op':'gt','value':0}})
        self.assertEqual(f.views[e['view']]['rows'],[['10']])
        f.apply({'tool':'group','by':[],'metrics':[{'function':'sum','field':'指标','name':'指标'}]})
        f.apply({'tool':'filter','where':{'field':'指标','op':'gt','value':5}})

    def test_recomputes_stale_numeric_column_only_in_authorized_copy(self):
        source={'columns':['项目','份数','单价（元）','金额（元）'],'rows':[['X','7','13','999'],['Y','2','8','999']]}
        before=deepcopy(source);f=TableFlow(source,'重新计算金额，按份数乘单价，保留所有明细。')
        action={'tool':'derive','name':'金额','formula':{'multiply':[{'column':'份数'},{'column':'单价（元）'}]}}
        e=f.apply(action);computed=deepcopy(f.views[e['view']]);self.assertEqual(computed['rows'],[['X','7','13','91'],['Y','2','8','16']])
        self.assertEqual(source,before);self.assertEqual(f.views['V0']['rows'],before['rows'])
        repeat=f.apply(dict(action,input=e['view']));self.assertTrue(repeat['already_done']);self.assertEqual(f.views[repeat['view']],computed)
        no=TableFlow(source,'计算一个金额作为参考')
        with self.assertRaises(TableError):no.apply(deepcopy(action))
        forbidden=TableFlow(source,'不要重新计算金额')
        with self.assertRaises(TableError):forbidden.apply(deepcopy(action))

    def test_aggregate_followup_filters_groups_not_homonymous_detail(self):
        source={'columns':['团队','累计重量（g）'],'rows':[['甲','750'],['甲','900'],['乙','2200']]}
        previous={'columns':['团队','累计重量（g）'],'rows':[['甲','1650'],['乙','2200']]}
        f=TableFlow(source,'那累计重量至少2kg的组呢？',previous,previous_shape='aggregate')
        with self.assertRaisesRegex(TableError,'P0'):
            f.apply({'tool':'filter','input':'V0','where':{'field':'累计重量（g）','op':'gte','value':'2kg'}})
        e=f.apply({'tool':'filter','input':'P0','where':{'field':'累计重量（g）','op':'gte','value':'2kg'}})
        self.assertEqual(f.views[e['view']]['rows'],[['乙','2200']])
        # An explicit per-row requirement has a different grain.
        row=TableFlow(source,'每条明细记录累计重量至少2kg',previous,previous_shape='aggregate')
        row.apply({'tool':'filter','input':'V0','where':{'field':'累计重量（g）','op':'gte','value':'2kg'}})

    def test_preserved_global_summary_recomputed_from_current_detail(self):
        from workbook_recovery import restore_global_summaries,global_summary_recipes
        f=TableFlow({'columns':['项目','余额（元）'],'rows':[['甲','25'],['乙','60']]},'余额大于30元')
        f.apply({'tool':'filter','where':{'field':'余额（元）','op':'gt','value':'30元'}})
        recipe={'op':'group','by':[],'metrics':[{'function':'sum','column':'余额（元）','as':'总额'},{'function':'count','as':'条数'}]}
        contract={'global_summary':True,'retained_summary_recipes':[recipe]};action={'result':'V1','summaries':['V99']}
        self.assertTrue(restore_global_summaries(f,contract,action));self.assertEqual(f.views[action['summaries'][0]]['rows'],[['60','1']])
        self.assertEqual(global_summary_recipes(f.graph,action),[recipe]);self.assertFalse(restore_global_summaries(f,contract,action))

    def test_verified_aggregate_followup_can_proceed_to_delivery_without_regrouping(self):
        source={'columns':['部门','累计时长（分钟）'],'rows':[['甲','100'],['甲','100'],['乙','50']]}
        previous={'columns':['部门','累计时长（分钟）'],'rows':[['甲','200'],['乙','50']]}
        f=TableFlow(source,'那累计时长至少2小时的组呢？其他规则不变。',previous,previous_shape='aggregate')
        f.verified_previous_scope=True
        e=f.apply({'tool':'filter','input':'P0','where':{'field':'累计时长（分钟）','op':'gte','value':'2小时'}})
        c=f.delivery_candidate({'deliver':'aggregate'},'上轮：按部门分组汇总\n'+f.current_goal)
        self.assertEqual(c['result'],e['view']);self.assertEqual(c['summaries'],[])
        f.verified_previous_scope=False
        self.assertIsNone(f.delivery_candidate({'deliver':'aggregate'},'按部门分组汇总'))

    def test_focused_followup_and_proof_survive_execution_replay(self):
        from workbook_recovery import interpret_followup_delta,previous_scope_proof
        from workbook_flow import replay,fingerprint
        source={'columns':['员工号','小组','累计重量（g）'],'rows':[['11','甲','750'],['12','甲','900'],['13','乙','2200']]}
        prior={'columns':['小组','累计重量（g）'],'rows':[['甲','1650'],['乙','2200']],'provenance':[[0,1],[2]]}
        f=TableFlow(source,'只保留累计重量至少2kg的组，其他条件不变。',prior,previous_shape='aggregate');f.verified_previous_scope=True;f.previous_distinct_keys=['员工号']
        class Model:
            def generate(self,*a,**kw):return json.dumps({'quote':'累计重量至少2kg的组','actions':[{'tool':'filter','where':{'field':'累计重量（g）','op':'gte','value':'2kg'}}]},ensure_ascii=False),{}
        office=SimpleNamespace(agent=SimpleNamespace(model=Model()),workbook_metrics={'tokens':0,'peak_memory_gb':0})
        contract={'deliver':'aggregate','retained_scope':{'mode':'subset','origins':[0,1,2],'input':'P0'},'initial_distinct_keys':['员工号']}
        action=interpret_followup_delta(office,f,contract);result=f.finish(action,contract)
        config={'previous_result':prior,'previous_shape':'aggregate','flow':{'graph':f.graph,'finish':action,'contract':contract,'expected':fingerprint(result),'previous_scope_proof':previous_scope_proof(f)}}
        self.assertEqual(replay(source,config)['rows'],[['乙','2200']])
        config['previous_result']=deepcopy(prior);config['previous_result']['rows'][0][1]='2000'
        with self.assertRaisesRegex(TableError,'依据不一致'):replay(source,config)

    def test_invalid_followup_delta_rolls_back_all_new_actions(self):
        from workbook_recovery import interpret_followup_delta
        prior={'columns':['余额'],'rows':[['5'],['12']]};f=TableFlow(prior,'余额至少10，其他条件不变',prior);f.verified_previous_scope=True
        class Model:
            def generate(self,*a,**kw):return json.dumps({'quote':'余额至少10','actions':[{'tool':'filter','where':{'field':'余额','op':'gte','value':10}},{'tool':'select','fields':['不存在']}]},ensure_ascii=False),{}
        office=SimpleNamespace(agent=SimpleNamespace(model=Model()),workbook_metrics={'tokens':0,'peak_memory_gb':0});before=deepcopy(f.__dict__)
        with self.assertRaises(TableError):interpret_followup_delta(office,f,{'retained_scope':{'mode':'subset'}},)
        self.assertEqual(f.__dict__,before)

    def test_table_only_followup_disables_inherited_word_request(self):
        from workbook_intent import writing_intent
        self.assertTrue(writing_intent('单价至少1200元的再列出来，其他规则不变，只要表格。')[2])
        self.assertFalse(writing_intent('只要表格，另外生成Word说明。')[2])

    def test_recalculation_dependency_change_invalidates_previous_success(self):
        source={'columns':['件数','单价（元）','金额（元）'],'rows':[['3','7.5','999']]}
        f=TableFlow(source,'重新计算金额，件数乘单价；重新计算单价，按单价乘2；再重新计算金额。')
        amount={'tool':'derive','name':'金额','formula':{'multiply':[{'column':'件数'},{'column':'单价（元）'}]}}
        f.apply(deepcopy(amount));f.apply({'tool':'derive','name':'单价','formula':{'multiply':[{'column':'单价（元）'},{'constant':2}]}})
        e=f.apply(deepcopy(amount));self.assertFalse(e.get('already_done',False));self.assertEqual(f.views[e['view']]['rows'],[['3','15','45']])
        repeat=f.apply(deepcopy(amount));self.assertTrue(repeat['already_done']);self.assertEqual(f.views[repeat['view']]['rows'],[['3','15','45']])

    def test_output_fields_end_before_separate_delivery_instructions(self):
        from workbook_agent import output_contract
        table={'columns':['渠道','总距离（g）','数额（元）','笔数'],'rows':[]}
        for directive in ['生成Word','提供一份DOCX','制作一个PDF','保存简短的文档','交付报告','给我一份Word，标题“记录”']:
            with self.subTest(directive=directive):
                names=output_contract(None,'只保留渠道、总距离、数额和笔数四列，'+directive+'。',table,{})
                self.assertEqual(names,table['columns'])

    def test_a_real_column_named_like_a_delivery_remains_selectable(self):
        from workbook_agent import output_contract
        table={'columns':['岗位','生成Word'],'rows':[]}
        self.assertEqual(output_contract(None,'只保留岗位，生成Word。',table,{}),table['columns'])
        # Unknown output fields still fail instead of being silently removed.
        class Model:
            def generate(self,*a,**kw):return json.dumps({'bindings':[{'requested':'岗位','column':'岗位'}]},ensure_ascii=False),{}
        office=SimpleNamespace(agent=SimpleNamespace(model=Model()),core=SimpleNamespace(parse_json=json.loads))
        with self.assertRaisesRegex(TableError,'输出字段尚未完整'):output_contract(office,'只保留岗位、不存在的列，生成Word。',table,{})

    def test_source_requiring_followup_can_declare_narrowing_without_mutating_rows(self):
        from workbook_recovery import interpret_followup_delta
        source={'columns':['结束日期','部门','总额'],'rows':[['2030-01-02','甲','30']]}
        previous={'columns':['部门','总额'],'rows':[['甲','30']]};f=TableFlow(source,'仅留下月结束的，其他条件不变',previous,previous_shape='aggregate');f.verified_previous_scope=True
        class Model:
            def generate(self,*a,**kw):return json.dumps({'not_applicable':True,'narrows':True,'quote':'仅留下月结束的'},ensure_ascii=False),{}
        o=SimpleNamespace(agent=SimpleNamespace(model=Model()),workbook_metrics={'tokens':0,'peak_memory_gb':0});contract={'retained_scope':{'mode':'equal'}};before=deepcopy(f.views)
        self.assertIsNone(interpret_followup_delta(o,f,contract));self.assertEqual(contract['retained_scope']['mode'],'subset');self.assertEqual(f.views,before)

    def test_rank_requests_are_not_fictitious_output_columns(self):
        from workbook_agent import output_contract
        table={'columns':['团队','合计'],'rows':[]}
        for phrase in ['只要第一名','只保留前3行','仅留第2条']:
            self.assertIsNone(output_contract(None,phrase+'，其他条件和列不变。',table,{}))
        actual={'columns':['团队','第一名'],'rows':[]}
        self.assertEqual(output_contract(None,'只保留团队、第一名。',actual,{}),actual['columns'])

    def test_executed_date_constraint_does_not_become_an_aggregate_output_column(self):
        from workbook_agent import output_contract
        source={'columns':['完成日期','归档日期','组别','费用'],'rows':[['2031-02-02','2031-03-01','甲','30'],['2031-04-02','2031-02-02','乙','50']]}
        f=TableFlow(source,'只保留完成日期在2031年2月整月的，其他要求不变，只要表格。')
        f.record('V0',{'op':'filter','where':{'all':[{'column':'完成日期','operator':'gte','value':'2031-02-01','type':'date'},{'column':'完成日期','operator':'lte','value':'2031-02-28','type':'date'}]}})
        f.record(f.last,{'op':'group','by':['组别'],'metrics':[{'function':'sum','column':'费用','as':'合计'}]})
        scope=(f.views['V0'],lambda p:f.source_constraint_enforced([f.last],p))
        self.assertIsNone(output_contract(None,f.current_goal,f.views[f.last],{},source_scope=scope))
        self.assertEqual(f.views[f.last]['rows'],[['甲','30']])
        from workbook_intent import verified_calendar_row_clause
        self.assertFalse(verified_calendar_row_clause('完成日期在2031年2月整月的',(f.views['V0'],lambda p:False)))
        actual={'columns':['完成日期在2031年2月整月的'],'rows':[]}
        self.assertEqual(output_contract(None,'只保留完成日期在2031年2月整月的。',actual,{},source_scope=scope),actual['columns'])

if __name__=='__main__':unittest.main()
