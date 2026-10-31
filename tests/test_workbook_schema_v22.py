"""Presentation stays separate from arithmetic; clarification gets one self-check."""
from copy import deepcopy
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
import io
import json
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from table_program import TableError
from workbook_agent import Clarification
from workbook_flow import TableFlow,plan_actions,replay,fingerprint,freeze_finish
from workbook_requirements import explicit_binary
from workbook_data import prepare_table,automatic_append


def table(columns,rows):
    return {'columns':columns,'rows':rows,'provenance':[[i] for i in range(len(rows))],'notes':[]}


class WorkbookSchemaTests(unittest.TestCase):
    def test_invalid_arguments_escalate_to_structure_constraints_and_keep_progress(self):
        class Model:
            supports_structured_output=True
            def __init__(self):self.options=[];self.answers=[{'title':'结果','deliver':'detail','detail_request':''},
                {'tool':'filter','where':'金额不少于10'},
                {'tool':'filter','input':'V0','where':{'field':'F1','op':'gte','value':10}},
                {'state':'passed'}]
            def generate(self,*args,**options):self.options.append(options);return json.dumps(self.answers.pop(0)),{'tokens':1}
        model=Model();office=SimpleNamespace(agent=SimpleNamespace(model=model),core=SimpleNamespace(emit=lambda *a,**k:None),workbook_metrics={'tokens':0,'peak_memory_gb':0})
        with redirect_stdout(io.StringIO()):flow,_,_,result,failures=plan_actions(office,table(['金额（元）'],[['5'],['15']]),'找出金额不少于10元的记录。',automatic_handoff=True)
        self.assertEqual(result['rows'],[['15']]);self.assertEqual(len(flow.graph),1)
        self.assertEqual(len(failures),1);self.assertNotIn('response_schema',model.options[1])
        self.assertIn('response_schema',model.options[2]);self.assertEqual(office.workbook_metrics['constraint_escalations'],1)

    def test_first_record_dedup_qualifications_do_not_treat_dropped_rows_as_contributions(self):
        source=table(['票号','日期','金额（元）','联系号'],[['A','2027-02-01','100','X'],['A','2027-03-01','20','']])
        goal='先按票号保留首次记录，日期在2027-02-01至2027-02-28，只统计单笔金额不少于50元的，剔除联系号没填的，统计金额。'
        flow=TableFlow(source,goal)
        flow.apply({'tool':'distinct','fields':['票号']})
        flow.apply({'tool':'filter','where':{'all':[{'field':'日期','op':'gte','value':'2027-02-01'},{'field':'日期','op':'lte','value':'2027-02-28'},{'field':'金额','op':'gte','value':50},{'field':'联系号','op':'not_empty'}]}})
        flow.apply({'tool':'group','by':[],'metrics':[{'function':'sum','field':'金额','name':'合计'}]})
        self.assertEqual(flow.finish({'result':flow.last},{'deliver':'aggregate'})['rows'],[['100']])
        self.assertEqual(flow.views[flow.last]['provenance'],[[0,1]])
        # Reusing a raw field label for a grouped metric does not make its
        # aggregate filter evidence of the original per-record condition.
        changed=TableFlow(table(['金额（元）'],[['100'],['300']]),'单笔金额不少于200元，统计金额合计。')
        changed.apply({'tool':'group','by':[],'metrics':[{'function':'sum','field':'金额','name':'金额（元）'}]})
        changed.apply({'tool':'filter','where':{'field':'金额','op':'gte','value':200}})
        self.assertFalse(changed.source_constraint_enforced([changed.last],{'column':'金额（元）','operator':'gte','type':'number','value':'200'}))
        with self.assertRaises(TableError):changed.finish({'result':changed.last},{'deliver':'detail'})

    def test_explicit_empty_polarity_is_corrected_without_replacing_other_conditions(self):
        source=table(['发票号','状态'],[['','有效'],['INV-A','有效'],['','取消']])
        flow=TableFlow(source,'发票号为空且状态不是取消。')
        event=flow.apply({'tool':'filter','where':{'all':[{'field':'发票号','op':'not_in','value':['']},{'field':'状态','op':'ne','value':'取消'}]}})
        self.assertEqual(flow.views[flow.last]['rows'],[['','有效']])
        self.assertTrue(any(n['kind']=='literal_empty_polarity' and n['quote']=='发票号为空' for n in event['intent_corrections']))
        nonempty=TableFlow(source,'剔除发票号没填的。')
        nonempty.apply({'tool':'filter','where':{'field':'发票号','op':'is_empty'}})
        self.assertEqual(nonempty.views[nonempty.last]['rows'],[['INV-A','有效']])
        from workbook_requirements import literal_empty_requirements
        self.assertEqual(literal_empty_requirements('排除待确认与联系号为空的记录。',table(['联系号'],[['X']]))[0]['operator'],'not_empty')
        self.assertEqual(literal_empty_requirements('剔除无效状态和联系号没填的记录。',table(['联系号'],[['X']]))[0]['operator'],'not_empty')
        overlapping=TableFlow(table(['号','发票号'],[['A','']]),'').views['V0']
        self.assertEqual([r['column'] for r in literal_empty_requirements('找出发票号为空的。',overlapping)],['发票号'])
        for goal in ('如果发票号为空就补填。','发票号为空或状态取消。','不要筛选发票号为空。','统计发票号为空的，再剔除发票号没填的。'):
            self.assertEqual(literal_empty_requirements(goal,flow.views['V0']),[],goal)

    def test_chinese_date_range_and_omitted_year_month_have_two_explicit_bounds(self):
        from workbook_intent import literal_calendar_requirements
        source=TableFlow(table(['到期日'],[['2027-03-10']]),'').views['V0']
        for goal in ('到期日在2027年3月1日至3月31日（含两天）。','到期日在2027年3月1日至31日。','到期日在2027-03-01至2027-03-31。'):
            rules=literal_calendar_requirements(goal,source)
            self.assertEqual([(r['operator'],r['value']) for r in rules],[('gte','2027-03-01'),('lte','2027-03-31')])
        for goal in ('例如到期日在2027年3月1日至31日。','到期日在2027年3月1日至31日或没有到期日。','到期日在2027年3月1日至31日，不包含结束日。'):
            self.assertEqual(literal_calendar_requirements(goal,source),[])
        with self.assertRaisesRegex(TableError,'不能自动交换或猜跨年'):
            literal_calendar_requirements('到期日在2027年12月1日至1月31日。',source)

    def test_missing_calendar_bound_repairs_before_top_n_and_refills_result(self):
        from workbook_revision import repair_delivery_filter
        from workbook_requirements import qualifies_before_limit
        source=table(['编号','到期日','金额（元）'],[['A','2027-04-01','900'],['B','2027-03-03','800'],['C','2027-03-05','700'],['D','2027-03-06','600']])
        goal='到期日在2027年3月1日至31日，按金额降序取前3笔。'
        flow=TableFlow(source,goal)
        flow.apply({'tool':'sort','by':[{'field':'金额','direction':'desc'}]})
        flow.apply({'tool':'limit','count':3})
        with self.assertRaises(TableError) as caught:flow.finish({'result':flow.last},{'deliver':'detail'})
        e=caught.exception;self.assertTrue(e.repair_before_limits)
        rebuilt,finish=repair_delivery_filter(flow,{'result':flow.last},e.repair_predicate,'detail',before_limits=e.repair_before_limits)
        self.assertEqual([r[0] for r in rebuilt.finish(finish,{'deliver':'detail'})['rows']],['B','C','D'])
        self.assertFalse(qualifies_before_limit('先取前3笔，再剔除联系号没填的。','剔除联系号没填的'))

    def test_calendar_bounds_are_checked_even_after_date_field_is_grouped_away(self):
        source=table(['部门','登记日','金额（元）'],[['甲','2027-02-10','300'],['甲','2027-03-01','400']])
        flow=TableFlow(source,'登记日在2027-02-01至2027-02-28，按部门统计金额。')
        flow.apply({'tool':'group','by':['部门'],'metrics':[{'function':'sum','field':'金额','name':'合计'}]})
        with self.assertRaises(TableError) as caught:flow.finish({'result':flow.last},{'deliver':'aggregate'})
        self.assertEqual(caught.exception.repair_predicate,{'column':'登记日','operator':'lte','type':'date','value':'2027-02-28'})
        self.assertEqual(caught.exception.repair_shape,'detail')

    def test_blank_removal_is_checked_through_aggregate_provenance_and_rebuilt(self):
        from workbook_requirements import literal_nonempty_requirements
        from workbook_revision import repair_delivery_filter
        source=table(['站点','联系号','时数（小时）'],[['甲','','2'],['甲','A','3'],['乙','B','1']])
        goal='剔除联系号没填的，按站点统计人数和时数。'
        flow=TableFlow(source,goal)
        flow.apply({'tool':'group','by':['站点'],'metrics':[{'function':'count','name':'人数'},{'function':'sum','field':'时数','name':'时数'}]})
        action={'result':flow.last}
        with self.assertRaises(TableError) as caught:flow.finish(action,{'deliver':'aggregate'})
        predicate=caught.exception.repair_predicate
        corrected,finish=repair_delivery_filter(flow,action,predicate,'detail')
        self.assertEqual(corrected.finish(finish,{'deliver':'aggregate'})['rows'],[['甲','1','180'],['乙','1','60']])
        for wording in ('不要剔除联系号没填的。','剔除联系号没填的或时数不足的。','例如剔除联系号没填的。','剔除紧急联系号没填的。'):
            self.assertEqual(literal_nonempty_requirements(wording,flow.views['V0']),[],wording)
        self.assertEqual(literal_nonempty_requirements('把联系号未填写的去掉。',flow.views['V0'])[0]['column'],'联系号')

    def test_missing_new_field_label_has_specific_repair_advice(self):
        flow=TableFlow(table(['数值'],[['2']]),'计算差额。')
        for name in ('F7','F1',json.loads('"\\u00461"')):
            with self.assertRaisesRegex(TableError,'name是新字段的业务名称'):
                flow.apply({'tool':'derive','name':name,'formula':{'column':'F1'}})

    def test_retained_sort_is_reapplied_after_replanning_without_new_model_round(self):
        class Model:
            def __init__(self):self.calls=0;self.answers=[{'title':'结果','deliver':'detail','detail_request':''},
                {'tool':'filter','where':{'field':'金额','op':'gte','value':200}},
                {'tool':'finish','result':'V1'},{'state':'passed'}]
            def generate(self,*args,**kw):self.calls+=1;return json.dumps(self.answers.pop(0)),{'tokens':1}
        model=Model();office=SimpleNamespace(agent=SimpleNamespace(model=model),core=SimpleNamespace(emit=lambda *a,**k:None),workbook_metrics={'tokens':0,'peak_memory_gb':0})
        old={'deliver':'detail','ordering':[{'column':'金额（元）','direction':'desc','type':'number'}]}
        with redirect_stdout(io.StringIO()):flow,contract,finish,result,_=plan_actions(office,table(['编号','金额（元）'],[['A','250'],['B','300'],['C','100']]),'门槛改为不少于200元，其他要求不变。',previous_contract=old)
        self.assertEqual(result['rows'],[['B','300'],['A','250']]);self.assertEqual(model.calls,4)
        self.assertEqual(contract['ordering_repairs'],1);self.assertEqual(finish['result'],'V2')
        from workbook_requirements import changes_ordering,result_ordering
        self.assertTrue(changes_ordering('这次不要排序，其他不变。'))
        self.assertTrue(changes_ordering('按日期由近到远排列，其他不变。'))
        self.assertTrue(changes_ordering('顺序倒过来，其他不变。'))
        self.assertFalse(changes_ordering('排序保持不变。'))
        self.assertEqual(result_ordering(flow.graph,finish['result']),old['ordering'])

    def test_original_record_bound_cannot_be_replaced_by_aggregate_count(self):
        source=table(['线路','费用（元）'],[['甲','300'],['甲','100'],['乙','250']])
        flow=TableFlow(source,'只统计单笔费用不少于200元的原始登记，按线路汇总费用和票数。')
        flow.apply({'tool':'group','by':['线路'],'metrics':[{'function':'sum','field':'费用','name':'费用合计'},{'function':'count','name':'票数'}]})
        with self.assertRaisesRegex(TableError,'不能改成汇总'):
            flow.apply({'tool':'filter','where':{'field':'票数','op':'gte','value':200}})
        with self.assertRaises(TableError) as caught:flow.finish({'result':flow.last},{'deliver':'aggregate'})
        self.assertEqual(caught.exception.repair_predicate['column'],'费用（元）')
        self.assertEqual(caught.exception.repair_shape,'detail')
        correct=TableFlow(source,flow.current_goal)
        correct.apply({'tool':'filter','where':{'field':'费用','op':'gte','value':'200元'}})
        correct.apply({'tool':'group','by':['线路'],'metrics':[{'function':'sum','field':'费用','name':'费用合计'},{'function':'count','name':'票数'}]})
        self.assertEqual(correct.finish({'result':correct.last},{'deliver':'aggregate'})['rows'],[['甲','300','1'],['乙','250','1']])

    def test_literal_formula_repairs_alias_and_reversed_subtraction_with_source_quote(self):
        flow=TableFlow(table(['毛重（kg）','皮重（g）'],[['1.4','250']]),'净料按毛重减皮重计算。')
        event=flow.apply({'tool':'derive','name':'净料','formula':{'column':'F1'}})
        self.assertEqual(flow.views[flow.last]['rows'][0][-1],'1150')
        self.assertEqual(flow.graph[-1]['operation']['expression'],{'subtract':[{'column':'毛重（g）'},{'column':'皮重（g）'}]})
        self.assertTrue(any(c['kind']=='explicit_arithmetic' for c in event['intent_corrections']))
        english=TableFlow(table(['Gross（g）','Tare（g）'],[['1800','300']]),'Net = Gross - Tare.')
        english.apply({'tool':'derive','name':'Net','formula':{'subtract':[{'column':'F2'},{'column':'F1'}]}})
        self.assertEqual(english.views[english.last]['rows'][0][-1],'1500')

    def test_literal_formula_does_not_compile_a_prefix_or_negated_example(self):
        columns=['毛重（g）','皮重（g）']
        for goal in ('净料按毛重减皮重再除以2计算。','不要计算净料按毛重减皮重计算。',
                     '例如计算净料按毛重减皮重计算。','净料按毛重减皮重减其他费用。',
                     '两倍净料按毛重减皮重计算。','净料按毛重减皮重计算，改为毛重加皮重。'):
            self.assertIsNone(explicit_binary(goal,'净料',columns)[0],goal)

    def test_each_table_converts_own_scale_before_append_and_retains_locations(self):
        def source(id,name,header,rows):
            return {'id':id,'file':name,'sheet':'登记','error':'','limited':False,'width':3,'merges':[],
                    'matrix':[['编号',header,'状态']]+rows}
        a=source('T1','甲.xlsx','费用（千元）',[['A','1.2','有效']])
        b=source('T2','乙.xlsx','费用（元）',[['B','300','有效']])
        before=deepcopy([a,b]);choices=[{'id':'T1','header_rows':[1]},{'id':'T2','header_rows':[1]}]
        merged=prepare_table([a,b],choices)
        self.assertEqual(merged['columns'],['编号','费用（元）','状态']);self.assertEqual([r[1] for r in merged['rows']],['1200','300'])
        self.assertEqual([r['file'] for r in merged['locations']],['甲.xlsx','乙.xlsx']);self.assertEqual([a,b],before)
        self.assertIsNotNone(automatic_append([a,b],'合并甲和乙的登记，只看有效记录。'))
        for goal in ('不要合并甲和乙。','只处理甲。','合并甲，不用乙。'):
            self.assertIsNone(automatic_append([a,b],goal))
        ambiguous=deepcopy(a);ambiguous['matrix'].append(['另一标题','别的字段','说明'])
        self.assertIsNone(automatic_append([ambiguous,b],'合并甲和乙。'))
        prefix=deepcopy(a);prefix.update(id='T3',file='甲乙.xlsx')
        other=deepcopy(b);other['file']='丙.xlsx'
        self.assertIsNone(automatic_append([a,prefix,other],'合并甲乙和丙。'))
        self.assertIsNone(automatic_append([a,b],'合并甲的备份和乙。'))
        for header in ('费用（USD）','费用'):
            incompatible=source('T2','乙.xlsx',header,[['B','300','有效']])
            with self.assertRaises(TableError):prepare_table([a,incompatible],choices)

    def test_present_filters_in_base_units_and_replays_unchanged_arithmetic(self):
        source=table(['包号','毛重（kg）','皮重（g）'],[['A','1.4','250'],['B','1.2','500']]);before=deepcopy(source)
        flow=TableFlow(source,'净重为毛重减皮重，不少于1000g，以kg显示。')
        flow.apply({'tool':'derive','name':'净重','formula':{'subtract':[{'column':'F2'},{'column':'F3'}]}})
        net=next(f for f in flow.fields(flow.views[flow.last]) if f['column'].startswith('净重'))
        event=flow.apply({'tool':'present','units':[{'field':net['id'],'unit':'kg'}]})
        self.assertEqual(len(flow.graph),1);self.assertFalse(event['already_done'])
        self.assertEqual(flow.views[flow.last]['rows'][0][-1],'1150')
        flow.apply({'tool':'filter','where':{'field':net['id'],'op':'gte','value':'1000g'}})
        action={'result':flow.last,'fields':['包号',net['id']]};contract={'deliver':'detail','presentation_fields':dict(flow.presentation_fields)}
        result=flow.finish(action,contract);self.assertEqual(result['rows'],[['A','1.15']])
        saved={'flow':{'graph':flow.graph,'finish':freeze_finish(flow,action),'contract':contract,'expected':fingerprint(result)}}
        self.assertEqual(replay(source,saved)['rows'],result['rows']);self.assertEqual(source,before)

    def test_present_conflicts_wrong_dimensions_and_unknown_fields_restore_full_state(self):
        flow=TableFlow(table(['金额（元）','状态'],[['100','正常']]),'金额以万元显示。')
        flow.fields(flow.views['V0'])
        for units in ([{'field':'F1','unit':'kg'}],[{'field':'F2','unit':'万元'}],
                      [{'field':'F1','unit':'元'},{'field':'F1','unit':'万元'}],
                      [{'field':'F1','unit':'万元'},{'field':'F88','unit':'元'}]):
            before=deepcopy(flow.__dict__)
            with self.subTest(units=units),self.assertRaises(TableError):flow.apply({'tool':'present','units':units})
            self.assertEqual(flow.__dict__,before)
        with self.assertRaises(TableError):flow.apply({'tool':'present','units':[{'field':'F1','unit':'万元'}],'output':'V9'})

    def test_present_does_not_erase_real_business_division(self):
        flow=TableFlow(table(['金额（元）'],[['100000']]),'金额除以10000，再以万元显示。')
        flow.apply({'tool':'derive','name':'分摊额','formula':'[金额（元）]/10000'})
        field=next(f for f in flow.fields(flow.views[flow.last]) if f['column'].startswith('分摊额'))
        flow.apply({'tool':'present','units':[{'field':field['id'],'unit':'万元'}]})
        self.assertIn('divide',flow.graph[0]['operation']['expression'])
        self.assertEqual(flow.finish({'fields':[field['id']]},{'deliver':'detail'})['rows'],[['0.001']])

    def test_one_clarification_self_check_can_resume_but_a_real_missing_requirement_survives(self):
        class Model:
            def __init__(self,answers):self.answers=list(answers);self.calls=[]
            def generate(self,system,user,**kw):
                self.calls.append(json.loads(user));return json.dumps(self.answers.pop(0),ensure_ascii=False),{'tokens':1}
        def office(answers):return SimpleNamespace(agent=SimpleNamespace(model=Model(answers)),core=SimpleNamespace(emit=lambda *a,**k:None),workbook_metrics={'tokens':0,'peak_memory_gb':0})
        contract={'title':'副本','deliver':'detail','detail_request':''}
        good=office([contract,{'clarify':'是否可以统一元与千元？'},{'tool':'select','fields':['F1']},{'tool':'finish','result':'V1'},{'state':'passed'}])
        with redirect_stdout(io.StringIO()):_,_,_,result,_=plan_actions(good,table(['金额（元）','备注'],[['500','甲']]),'只保留金额。')
        self.assertEqual(result['rows'],[['500']]);self.assertEqual(good.workbook_metrics['clarification_reviews'],1)
        self.assertEqual(good.agent.model.calls[2]['待修正动作']['error_code'],'review_clarification')
        missing=office([contract,{'clarify':'缺少计价汇率。'},{'clarify':'缺少计价汇率。'}])
        with redirect_stdout(io.StringIO()),self.assertRaisesRegex(Clarification,'汇率'):
            plan_actions(missing,table(['金额（USD）'],[['5']]),'换算为人民币。')
        self.assertEqual(len(missing.agent.model.calls),3)


if __name__=='__main__':unittest.main()
