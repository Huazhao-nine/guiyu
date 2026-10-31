import io,json,sys,unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from table_program import TableError
from workbook_flow import TableFlow,fingerprint,freeze_finish
from workbook_revision import build_flow,covered_request,try_revision,update_graph,retained_scope_flow


def source():
    return {'columns':['业务号','收入（元）','支出（元）','分类'],
            'rows':[['009','95','15','正常'],['010','70','20','正常'],['011','40','20','正常'],['012','300','0','关闭']],
            'provenance':[[0],[1],[2],[3]],'locations':[],'inputs':['虚构.csv'],'notes':[]}


def config():
    f=TableFlow(source(),'排除关闭，计算余额，保留明细和合计。')
    f.apply({'tool':'filter','where':{'field':'分类','op':'ne','value':'关闭'}})
    f.apply({'tool':'derive','name':'余额','formula':'[收入（元）]-[支出（元）]'})
    detail=f.last
    f.apply({'tool':'sort','by':[{'field':'余额（元）','direction':'desc'}]});detail=f.last
    f.apply({'tool':'group','input':detail,'by':[],'metrics':[{'function':'sum','field':'余额（元）','name':'合计'},{'function':'count','name':'条数'}]})
    contract={'deliver':'both','preserve_detail':True,'global_summary':True,'write':'写一段说明并导出Word。','docx':True}
    finish=freeze_finish(f,{'tool':'finish','result':detail,'summaries':[f.last],'fields':['业务号','余额（元）']})
    result=f.finish(finish,contract)
    return {'mode':'flow','flow':{'graph':f.graph,'finish':finish,'contract':contract,'expected':fingerprint(result)}},result


class Model:
    def __init__(self,decision):self.decision=decision;self.calls=0
    def generate(self,*a,**kw):self.calls+=1;return json.dumps(self.decision,ensure_ascii=False),{'tokens':10,'seconds':.01}


def office(decision):
    return SimpleNamespace(agent=SimpleNamespace(model=Model(decision)),core=SimpleNamespace(emit=lambda *a,**k:None),workbook_metrics={'tokens':0,'peak_memory_gb':0})


class RevisionTests(unittest.TestCase):
    def test_explicit_keep_filters_replays_verified_scope_and_gates_regrouping(self):
        cfg,prior=config();parent={'id':'scope-parent','workbook':cfg}
        goal='保留上轮筛选条件，从原始明细重算，按分类汇总余额。'
        f,note=retained_scope_flow(source(),goal,parent,prior,'其他要求不变。')
        self.assertEqual(f.origins(f.views[f.last]),{0,1,2});self.assertEqual(note['mode'],'equal')
        self.assertIn('收入（元）',f.views[f.last]['columns']);self.assertIn('余额（元）',f.views[f.last]['columns'])
        contract={'deliver':'aggregate','retained_scope':note}
        f.apply({'tool':'group','by':['分类'],'metrics':[{'function':'sum','field':'余额（元）','name':'余额合计'}]})
        self.assertEqual(f.finish({'result':f.last},contract)['rows'],[['正常','150']])
        f.apply({'tool':'group','input':'V0','by':['分类'],'metrics':[{'function':'count','name':'条数'}]})
        with self.assertRaisesRegex(TableError,'来源行'):f.finish({'result':f.last},contract)

    def test_keep_scope_does_not_silently_narrow_and_additional_filter_is_explicit(self):
        cfg,prior=config();parent={'id':'scope-parent','workbook':cfg}
        f,note=retained_scope_flow(source(),'保留上轮筛选条件，按分类汇总余额。',parent,prior,'')
        f.apply({'tool':'filter','where':{'field':'业务号','op':'eq','value':'009'}})
        with self.assertRaisesRegex(TableError,'来源行'):f.finish({'result':f.last},{'deliver':'detail','retained_scope':note})
        f,note=retained_scope_flow(source(),'保留上轮筛选条件，再只看业务号为009的记录。',parent,prior,'')
        self.assertEqual(note['mode'],'subset')
        f.apply({'tool':'filter','where':{'field':'业务号','op':'eq','value':'009'}})
        self.assertEqual(len(f.finish({'result':f.last},{'deliver':'detail','retained_scope':note})['rows']),1)

    def test_keep_scope_rejects_changed_inputs_and_non_retention_requests(self):
        cfg,prior=config();parent={'id':'scope-parent','workbook':cfg};changed=source();changed['rows'][0][1]='999'
        self.assertIsNone(retained_scope_flow(changed,'保留上轮筛选条件，按分类汇总。',parent,prior,''))
        for goal in ('把金额门槛放宽，保留上轮筛选条件。','取消上轮条件，保留上轮筛选条件。','看看全部记录。'):
            self.assertIsNone(retained_scope_flow(source(),goal,parent,prior,''))

    def revise(self,cfg,goal='把余额门槛改成不少于50元，其他要求不变。',value=50,op='gte'):
        quote=goal.split('，')[0]
        o=office({'mode':'boundaries','edits':[{'field':'余额（元）','op':op,'value':value,'quote':quote}]})
        with redirect_stdout(io.StringIO()),patch('workbook_edits.literal_edits',return_value=None):return try_revision(o,source(),goal,{'id':'prior','prompt':'排除关闭，计算余额并给明细与合计。','workbook':cfg},{'goal':'上轮目标'})

    def test_adding_boundary_updates_detail_and_summary_without_losing_other_conditions(self):
        cfg,old=config();before=deepcopy(cfg);value=self.revise(cfg)
        self.assertIsNotNone(value);f,c,finish,result,_=value
        self.assertEqual(result['rows'],[['009','80'],['010','50']]);self.assertEqual(result['summaries'][0]['rows'],[['130','2']])
        self.assertEqual(cfg,before);self.assertTrue(c['docx']);self.assertEqual(len(f.graph),5)
        self.assertEqual(c['revision']['edits'][0]['kind'],'add_shared_filter')

    def test_relaxing_from_raw_recovers_previously_excluded_row(self):
        cfg,_=config();f,c,finish,result,_=self.revise(cfg)
        next_config={'mode':'flow','flow':{'graph':f.graph,'contract':c,'finish':finish,'expected':fingerprint(result)}}
        f2,c2,fin2,result2,_=self.revise(next_config,'把余额门槛改成不少于20元，其他要求不变。',20)
        self.assertEqual(result2['rows'],[['009','80'],['010','50'],['011','20']]);self.assertEqual(result2['summaries'][0]['rows'],[['150','3']])
        self.assertEqual(len(f2.graph),len(f.graph));self.assertEqual(c2['revision']['edits'][0]['kind'],'replace_boundary')

    def test_chat_return_and_explicit_word_cancellation(self):
        cfg,_=config()
        goal='回到刚才的工作簿，沿用原有条件，从原始记录重算，把余额门槛改成不少于50元，输出列和金额合计、条数保持。这次只需要表格，不要Word。'
        o=office({'mode':'boundaries','edits':[{'field':'余额（元）','op':'gte','value':50,'quote':'把余额门槛改成不少于50元'}]})
        value=try_revision(o,source(),goal,{'id':'source-parent','prompt':'处理资料','workbook':cfg},{'goal':'前序'})
        self.assertIsNotNone(value);self.assertFalse(value[1]['docx']);self.assertEqual(value[1]['write'],'')

    def test_invented_threshold_or_boundary_direction_cannot_pass(self):
        cfg,_=config()
        self.assertIsNone(self.revise(cfg,value=999));self.assertIsNone(self.revise(cfg,op='gt'))
        self.assertIsNone(self.revise(cfg,value=1));self.assertIsNone(self.revise(cfg,value=0))
        cfg['flow']['expected']='modified';self.assertIsNone(self.revise(cfg))

    def test_extra_grouping_or_projection_request_falls_back_to_planner(self):
        self.assertTrue(covered_request('把余额门槛改成不少于50元，其他条件、排序和输出字段不变。',['把余额门槛改成不少于50元']))
        self.assertFalse(covered_request('把余额改成不少于50元，另外按分类汇总。',['把余额改成不少于50元']))
        self.assertFalse(covered_request('把余额改成不少于50元，只保留业务号。',['把余额改成不少于50元']))
        self.assertFalse(covered_request('把余额改成不少于50元并按分类汇总。',['把余额改成不少于50元并按分类汇总']))

    def test_multiple_bounds_or_or_branches_are_not_silently_overwritten(self):
        cfg,_=config();f=build_flow(source(),cfg,'余额不少于50元')
        f.apply({'tool':'filter','input':'V2','where':{'any':[{'field':'余额（元）','op':'gte','value':50},{'field':'分类','op':'eq','value':'正常'}]}})
        finish={'result':f.last,'summaries':[]}
        with self.assertRaisesRegex(TableError,'或/否定'):update_graph(f,finish,{'column':'余额（元）','operator':'gte','type':'number','value':20})

    def test_a_narrow_previous_result_is_not_complete_raw_source(self):
        cfg,prior=config();cfg['previous_result']=prior;cfg['previous_shape']='detail';cfg['flow']['graph']=[{'id':'V1','input':'P0','operation':{'op':'filter','where':{'column':'余额（元）','type':'number','operator':'gte','value':50}}}];cfg['flow']['finish']={'result':'V1','summaries':[]};cfg['flow']['contract']={'deliver':'detail'}
        self.assertIsNone(self.revise(cfg))

    def test_aggregate_threshold_is_never_rebound_to_raw_column(self):
        cfg,_=config();cfg['flow']['finish']={'result':'V4','summaries':[]}
        cfg['flow']['contract']={'deliver':'aggregate'}
        f=build_flow(source(),cfg,'统计余额');prior=f.finish(deepcopy(cfg['flow']['finish']),cfg['flow']['contract'])
        cfg['flow']['expected']=fingerprint(prior)
        o=office({'mode':'boundaries','edits':[]})
        value=try_revision(o,source(),'把合计门槛改成不少于50元，其他要求不变。',{'id':'prior','prompt':'统计余额','workbook':cfg},{'goal':'统计余额'})
        self.assertIsNotNone(value)
        flow=value[0];last=flow.graph[-1]
        self.assertEqual(flow.shapes[last['input']],'aggregate');self.assertEqual(last['operation']['where']['column'],'合计（元）')
        self.assertEqual(o.agent.model.calls,0)


class BatchAndSchemaTests(unittest.TestCase):
    def test_condition_list_is_documented_all_shorthand_with_limits(self):
        f=TableFlow(source(),'收入不少于50元且支出不少于20元。')
        f.apply({'tool':'filter','where':[{'field':'收入（元）','op':'gte','value':50},{'field':'支出（元）','op':'gte','value':20}]})
        self.assertEqual(f.views[f.last]['rows'],[['010','70','20','正常']])
        self.assertIn('all',f.graph[-1]['operation']['where'])
        for value in ([],[{'field':'收入（元）','op':'gt','value':0}]*17):
            with self.assertRaisesRegex(TableError,'1–16'):f.apply({'tool':'filter','where':value})

    def test_delivery_checks_omitted_literal_bound_even_when_model_finish_passes(self):
        f=TableFlow(source(),'收入不少于50元，只保留业务号。')
        with self.assertRaisesRegex(TableError,'交付仍有记录'):f.finish({'result':'V0','fields':['业务号']},{'deliver':'detail'})
        f.apply({'tool':'filter','where':{'field':'收入（元）','op':'gte','value':50}})
        self.assertEqual(f.finish({'result':f.last,'fields':['业务号']},{'deliver':'detail'})['rows'],[['009'],['010'],['012']])

    def test_numeric_gate_respects_or_hypothetical_and_negative_scopes(self):
        f=TableFlow(source(),'收入不少于50元或支出不足10元。')
        self.assertEqual(len(f.finish({'result':'V0'},{'deliver':'detail'})['rows']),4)
        for goal in ('例如收入不少于50元时可以筛选。','排除收入不少于50元的记录。','不要筛选收入不少于50元。'):
            f.current_goal=goal;self.assertEqual(len(f.finish({'result':'V0'},{'deliver':'detail'})['rows']),4)

    def test_numeric_gate_uses_canonical_units_before_hour_display(self):
        f=TableFlow({'columns':['时长（分钟）'],'rows':[['90'],['180']],'provenance':[[0],[1]],'notes':[]},'时长不少于2小时，用小时显示。')
        with self.assertRaisesRegex(TableError,'gte 120'):f.finish({'result':'V0'},{'deliver':'detail'})
        f.apply({'tool':'filter','where':{'field':'时长（分钟）','op':'gte','value':'2小时'}})
        self.assertEqual(f.finish({'result':f.last},{'deliver':'detail'})['rows'],[['3']])

    def test_literal_dedup_keys_correct_full_row_request_and_record_evidence(self):
        for goal in ('按分类去重。','分类相同只留首次记录。','同一分类只保留首次记录。'):
            f=TableFlow(source(),goal)
            event=f.apply({'tool':'distinct','fields':source()['columns']})
            self.assertEqual([r[0] for r in f.views[f.last]['rows']],['009','012'])
            self.assertEqual(f.graph[-1]['operation']['columns'],['分类'])
            self.assertEqual(event['intent_corrections'],f.graph[-1]['intent_corrections'])

    def test_conflicting_literal_dedup_keys_are_not_chosen_arbitrarily(self):
        from workbook_intent import explicit_keys
        with self.assertRaisesRegex(TableError,'不同的去重键'):
            explicit_keys('按分类去重，按业务号去重。',source()['columns'])
        self.assertIsNone(explicit_keys('按人员身份去重。',source()['columns']))

    def test_literal_exclusion_corrects_include_set_but_keeps_other_conditions(self):
        data={'columns':['编号','状态','数额（元）'],'rows':[['A','有效','10'],['B','待复核','20'],['C','退出','30'],['D','待复核','1']],'provenance':[[0],[1],[2],[3]],'notes':[]}
        f=TableFlow(data,'把退出的去掉，数额不少于10元。')
        event=f.apply({'tool':'filter','where':{'all':[{'field':'状态','op':'eq','value':'有效'},{'field':'数额（元）','op':'gte','value':10}]}})
        self.assertEqual([r[0] for r in f.views[f.last]['rows']],['A','B'])
        self.assertEqual(event['intent_corrections'][0]['after']['operator'],'ne')
        self.assertIn('退出',event['intent_corrections'][0]['quotes'][0])
        self.assertEqual(f.graph[-1]['operation']['where']['all'][1]['value'],'10')

    def test_exclusion_does_not_broaden_positive_scope_or_or_not(self):
        data={'columns':['状态'],'rows':[['有效'],['待复核'],['退出']],'provenance':[[0],[1],[2]],'notes':[]}
        f=TableFlow(data,'排除退出，只保留有效记录。')
        event=f.apply({'tool':'filter','where':{'field':'状态','op':'eq','value':'有效'}})
        self.assertEqual(f.views[f.last]['rows'],[['有效']]);self.assertNotIn('intent_corrections',event)
        f=TableFlow(data,'排除退出，只保留待复核。')
        with self.assertRaisesRegex(TableError,'收窄'):f.apply({'tool':'filter','where':{'field':'状态','op':'eq','value':'有效'}})
        f=TableFlow(data,'排除退出。')
        with self.assertRaisesRegex(TableError,'收窄'):f.apply({'tool':'filter','where':{'any':[{'field':'状态','op':'eq','value':'有效'},{'field':'状态','op':'eq','value':'待复核'}]}})
        from workbook_intent import compile_exclusion_scope
        node={'not':{'column':'状态','operator':'eq','value':'有效'}};before=deepcopy(node)
        self.assertEqual(compile_exclusion_scope(node,f.goal,f.views['V0']),[]);self.assertEqual(node,before)

    def test_suffix_exclusion_matches_whole_observed_value(self):
        from workbook_intent import literal_exclusions
        f=TableFlow({'columns':['状态'],'rows':[['关闭'],['未关闭']],'provenance':[[0],[1]],'notes':[]},'')
        for goal in ('把未关闭的去掉。','先将未关闭记录剔除。','未关闭的去掉。'):
            self.assertEqual([r['value'] for r in literal_exclusions(goal,f.views['V0'])],['未关闭'])
        self.assertEqual(literal_exclusions('不排除关闭',f.views['V0']),[])

    def test_display_unit_aliases_are_bound_and_converted_once(self):
        f=TableFlow({'columns':['时长（小时）'],'rows':[['2']],'provenance':[[0]],'notes':[]},'时长用小时显示。')
        out=f.finish({'result':'V0','display_units':{'时长':'小时','时长（分钟）':'小时'}},{'deliver':'detail'})
        self.assertEqual(out['rows'],[['2']]);self.assertEqual(out['columns'],['时长（小时）'])

    def test_row_filter_retention_and_output_hints_cannot_hide_a_projection_or_path(self):
        f=TableFlow(source(),'收入大于50元。')
        f.apply({'tool':'filter','fields':source()['columns'],'output':'V1','where':{'field':'收入（元）','op':'gt','value':50}})
        self.assertEqual(f.views[f.last]['columns'],source()['columns'])
        for extra in ({'fields':['业务号']},{'output':'../../资料'},{'output':'V1'}):
            with self.assertRaises(TableError):f.apply({'tool':'filter','where':{'field':'收入（元）','op':'gt','value':50},**extra})

    def test_premature_duplicate_closer_repair_preserves_strings(self):
        from workbook_intent import remove_stray_json_closers,json_scalar_sequence
        raw='{"tool":"derive","fields":[{"name":"余额","formula":"[收入]-[费用"]}],"output":"V2"}'
        fixed=remove_stray_json_closers(raw)
        self.assertEqual(json_scalar_sequence(raw),json_scalar_sequence(fixed))
        self.assertEqual(json.loads(fixed)['fields'][0]['formula'],'[收入]-[费用')
    def test_unit_display_does_not_divide_canonical_values_twice(self):
        data={'columns':['时长（小时）'],'rows':[['2'],['5']],'provenance':[[0],[1]],'notes':[]}
        f=TableFlow(data,'时长用小时显示。')
        event=f.apply({'tool':'derive','fields':[{'name':'时长（小时）','formula':'[时长（分钟）]/60'}]})
        self.assertTrue(event['presentation_only']);self.assertEqual(len(f.graph),0)
        out=f.finish({'result':'V0'},{'deliver':'detail'})
        self.assertEqual(out['rows'],[['2'],['5']]);self.assertEqual(out['columns'],['时长（小时）'])
        self.assertEqual(f.views['V0']['rows'],[['120'],['300']])
        with self.assertRaisesRegex(TableError,'基础单位'):f.apply({'tool':'derive','name':'两倍','formula':'[时长（小时）]*2'})

    def test_implicit_quantity_unit_is_bound_to_unique_user_value(self):
        data={'columns':['时长（分钟）'],'rows':[['120'],['270']],'provenance':[[0],[1]],'notes':[]}
        f=TableFlow(data,'时长不少于3小时。')
        f.apply({'tool':'filter','where':{'field':'时长（分钟）','op':'gte','value':3}})
        self.assertEqual(f.views[f.last]['rows'],[['270']])
        from table_semantics import grounded_quantity
        with self.assertRaisesRegex(TableError,'多个单位'):grounded_quantity('1','1元和1万元','CNY')

    def test_retained_presentation_units_are_applied_at_delivery(self):
        data={'columns':['重量（克）'],'rows':[['2500']],'provenance':[[0]],'notes':[]}
        f=TableFlow(data,'其他要求不变。');f.presentation_units={'mass':'kg'}
        action={'result':'V0'};out=f.finish(action,{'deliver':'detail'})
        self.assertEqual(out['rows'],[['2.5']]);self.assertEqual(action['display_units'],{'重量（g）':'kg'})
        f.current_goal='用克显示。'
        self.assertEqual(f.finish({'result':'V0','display_units':{'重量（g）':'kg'}},{'deliver':'detail'})['rows'],[['2500']])
    def test_dedup_by_key_with_all_fields_does_not_dedup_full_rows(self):
        f=TableFlow(source(),'按分类去重，保留首次记录。')
        f.apply({'tool':'distinct','fields':source()['columns'],'by':['分类']})
        self.assertEqual([r[0] for r in f.views[f.last]['rows']],['009','012'])
        with self.assertRaisesRegex(TableError,'含义冲突'):f.apply({'tool':'distinct','fields':['业务号'],'by':['分类']})
    def test_batch_dependencies_units_and_atomic_failure(self):
        f=TableFlow(source(),'计算差额和一半，除以2。')
        event=f.apply({'tool':'derive','fields':[{'name':'差额','formula':'[收入（元）]-[支出（元）]'},{'name':'一半','formula':'[差额（元）]/2'}]})
        self.assertEqual(event['batch_count'],2);self.assertEqual(f.views[f.last]['rows'][0][-2:],['80','40'])
        before=deepcopy(f.__dict__)
        with self.assertRaises(TableError):f.apply({'tool':'derive','fields':[{'name':'临时','formula':'[收入（元）]/2'},{'name':'失败','formula':'[不存在]+1'}]})
        self.assertEqual(f.__dict__,before)

    def test_logical_type_alias_and_same_name_metric_are_schema_bound(self):
        f=TableFlow(source(),'筛选收入超过50元，再统计收入。')
        f.apply({'tool':'filter','where':{'type':'all','children':[{'field':'收入（元）','op':'gt','value':50}]}})
        f.apply({'tool':'group','by':[],'metrics':[{'function':'sum','name':'收入（元）'},{'function':'count','name':'人数'}]})
        self.assertEqual(f.views[f.last]['rows'],[['465','3']])
        with self.assertRaises(TableError):f.apply({'tool':'group','input':'V1','by':[],'metrics':[{'function':'sum','name':'不知道哪列'}]})

    def test_same_filter_is_reused_but_aggregate_values_need_a_new_condition(self):
        f=TableFlow(source(),'收入大于50元，按分类汇总收入。')
        action={'tool':'filter','where':{'field':'收入（元）','op':'gt','value':50}}
        f.apply(deepcopy(action));self.assertTrue(f.apply(dict(action,input=f.last))['already_done'])
        f.apply({'tool':'group','by':['分类'],'metrics':[{'function':'sum','field':'收入（元）','name':'收入（元）'}]})
        event=f.apply(dict(action,input=f.last));self.assertFalse(event.get('already_done',False));self.assertEqual(event['result']['row_count'],2)
