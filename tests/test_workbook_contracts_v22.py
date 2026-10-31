"""Task-contract scope, calculation reuse and source-level follow-up invariants."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from table_program import TableError
from workbook_flow import TableFlow,fingerprint,freeze_finish,replay
from workbook_agent import output_contract
from workbook_qualifiers import initial_distinct_keys,literal_boolean_rules
from workbook_revision import try_revision,covered_raw_revision,repair_delivery_filter
from workbook_data import automatic_append


def table(columns,rows):return {'columns':columns,'rows':rows,'provenance':[[i] for i in range(len(rows))],'notes':[]}
def no_model():
    class Model:
        def generate(self,*a,**k):raise AssertionError('A literal verified operation must not need model inference.')
    return SimpleNamespace(agent=SimpleNamespace(model=Model()),core=SimpleNamespace(emit=lambda *a,**k:None),workbook_metrics={'tokens':0,'peak_memory_gb':0})


class WorkbookContractTests(unittest.TestCase):
    def test_boolean_proof_traverses_unrelated_derived_fields(self):
        source=table(['State','Origin','金额（元）'],[['DONE','EXTERNAL','10'],['REVIEW','INTERNAL','20'],['REVIEW','EXTERNAL','30']])
        goal='保留State为DONE或者State为REVIEW且Origin为INTERNAL的记录。'
        flow=TableFlow(source,goal)
        flow.apply({'tool':'derive','name':'金额副本','formula':{'column':'金额'}})
        rule=literal_boolean_rules(goal,flow.views['V0'])[0]
        flow.apply({'tool':'filter','where':{'any':[{'field':'State','op':'eq','value':'DONE'},{'all':[{'field':'State','op':'eq','value':'REVIEW'},{'field':'Origin','op':'eq','value':'INTERNAL'}]}]}})
        self.assertTrue(flow.source_constraint_enforced([flow.last],rule['predicate']))
        self.assertEqual(len(flow.finish({'result':flow.last},{'deliver':'detail'})['rows']),2)

    def test_omitted_field_names_bind_only_unique_observed_categories(self):
        source=TableFlow(table(['组','跟进状态','来源'],[['甲','已完成','外部'],['乙','复核通过','转介'],['乙','复核通过','其他']]),'').views['V0']
        rules=literal_boolean_rules('只算已完成的，或复核通过并且来源为转介的记录。',source)
        self.assertEqual(len(rules),1);self.assertEqual(set(rules[0]['fields']),{'跟进状态','来源'})
        ambiguous=TableFlow(table(['状态','备注'],[['完成','完成'],['通过','通过']]),'').views['V0']
        self.assertEqual(literal_boolean_rules('只看完成的或通过的记录。',ambiguous),[])
        case_distinct={'columns':['Status','status'],'rows':[['DONE','HOLD'],['WAIT','REVIEW']],'field_types':{'Status':'text','status':'text'}}
        self.assertEqual(set(literal_boolean_rules('只看DONE或REVIEW。',case_distinct)[0]['fields']),{'Status','status'})
        free_text={'columns':['状态','备注'],'rows':[['完成','记录'+str(i)] for i in range(41)]+[['完成','完成'],['通过','通过']],'field_types':{'状态':'text','备注':'text'}}
        self.assertEqual(literal_boolean_rules('只看完成或通过。',free_text),[])

    def test_replay_restores_first_scope_graph_and_rejects_corrupt_ids(self):
        source=table(['编号','状态'],[['A','不符'],['A','有效'],['B','有效']]);before=deepcopy(source)
        flow=TableFlow(source,'先按编号保留原表首次记录，之后只看状态为有效。')
        keys=initial_distinct_keys(flow.goal,source['columns']);flow.enable_initial_distinct(keys)
        flow.apply({'tool':'filter','input':'V0','where':{'field':'状态','op':'eq','value':'有效'}})
        contract={'deliver':'detail','initial_distinct_keys':keys};finish={'result':flow.last};expected=flow.finish(finish,contract)
        config={'flow':{'graph':flow.graph,'finish':freeze_finish(flow,finish),'contract':contract,'expected':fingerprint(expected)}}
        self.assertEqual(replay(source,config)['rows'],[['B','有效']]);self.assertEqual(source,before)
        for graph in ([{'id':'V0','input':'V0','operation':{'op':'distinct','columns':['编号']}}],[{'id':'V1','input':'V1','operation':{'op':'distinct','columns':['编号']}}]):
            bad=deepcopy(config);bad['flow']['graph']=graph
            with self.assertRaisesRegex(TableError,'编号或依赖无效'):replay(source,bad)

    def test_unit_pair_lists_normalize_unambiguously_and_reject_conflicts(self):
        from workbook_intent import normalize_action,validate_action
        action=normalize_action({'tool':'finish','result':'V0','display_units':[{'field':'金额','unit':'万元'}]})
        self.assertEqual(action['display_units'],{'金额':'万元'});validate_action(action)
        for units in ([{'field':'金额','unit':'万元'},{'field':'金额','unit':'kg'}],[{'field':'金额','unit':'unrecognized'}],[{'field':'金额','unit':'元','code':'no'}]):
            with self.assertRaises(TableError):normalize_action({'tool':'finish','display_units':units})

    def test_projection_distinguishes_record_retention_from_explicit_columns(self):
        source=table(['票据号','差额（元）'],[['A','100']]);office=no_model()
        self.assertEqual(output_contract(office,'先按票据号保留原表首次记录，不排序后再去重。仅留票据号和差额。每条明细保留，再给合计。',source,{}),source['columns'])
        self.assertIsNone(output_contract(office,'按票据号保留原表首次记录，不排序后再去重。',source,{}))
        grouped=table(['小组','条数','时长合计（分钟）'],[['甲','2','90']])
        self.assertEqual(output_contract(office,'只要小组、条数、时长合计三列，不撰写说明。',grouped,{}),grouped['columns'])
        self.assertEqual(output_contract(office,'只要票据号和差额合计两列。',source,{}),source['columns'])

    def test_equivalent_unit_alias_reuses_checked_arithmetic_without_new_column(self):
        flow=TableFlow(table(['毛重（kg）','皮重（g）'],[['2.52','430']]),'净料按毛重减皮重计算，以kg显示。')
        expr={'subtract':[{'column':'F1'},{'column':'F2'}]}
        flow.apply({'tool':'derive','name':'净料','formula':expr})
        event=flow.apply({'tool':'derive','name':'净料_kg','formula':expr,'precision':2})
        self.assertTrue(event['verification_only']);self.assertEqual(len(flow.graph),1)
        self.assertEqual(flow.finish({'fields':['净料']},{'deliver':'detail'})['rows'],[['2.09']])
        flow.apply({'tool':'derive','name':'另一个业务量','formula':expr})
        self.assertEqual(len(flow.graph),2)

    def test_reuse_does_not_silently_change_rounded_values(self):
        flow=TableFlow(table(['实数','基数'],[['1','3']]),'比率按实数除以基数计算。')
        expr={'divide':[{'column':'F1'},{'column':'F2'}]}
        flow.apply({'tool':'derive','name':'比率','formula':expr,'precision':8})
        with self.assertRaises(TableError):flow.apply({'tool':'derive','name':'比率','formula':expr,'precision':2})
        self.assertEqual(flow.views[flow.last]['rows'][0][-1],'0.33333333')

    def test_boolean_scope_repairs_flattened_or_and_preserves_global_condition(self):
        source=table(['State','Origin','金额（元）'],[['DONE','EXTERNAL','10'],['REVIEW','INTERNAL','20'],['REVIEW','EXTERNAL','30'],['DRAFT','INTERNAL','40']])
        goal='只看State为DONE，或者State为REVIEW并且Origin为INTERNAL的记录。'
        flow=TableFlow(source,goal);rules=literal_boolean_rules(goal,flow.views['V0']);self.assertEqual(len(rules),1)
        event=flow.apply({'tool':'filter','where':{'all':[{'field':'State','op':'in','value':['DONE','REVIEW']},{'field':'Origin','op':'eq','value':'INTERNAL'}]}})
        self.assertEqual(flow.views[flow.last]['rows'],source['rows'][:2])
        self.assertTrue(any(c['kind']=='literal_boolean_scope' for c in event['intent_corrections']))
        for text in ('不要保留State为DONE或State为REVIEW。','例如State为DONE或State为REVIEW。','State为DONE或(State为REVIEW且Origin为INTERNAL)。'):
            self.assertEqual(literal_boolean_rules(text,flow.views['V0']),[],text)

    def test_missing_boolean_condition_rebuilds_existing_aggregate(self):
        source=table(['组','状态','来源','金额（元）'],[['甲','完成','外部','10'],['甲','复核通过','内部','20'],['甲','复核通过','外部','30']])
        flow=TableFlow(source,'保留状态是完成的，或者状态是复核通过且来源为内部的记录，按组汇总金额。')
        flow.apply({'tool':'group','by':['组'],'metrics':[{'function':'sum','field':'金额','name':'合计'}]})
        with self.assertRaises(TableError) as caught:flow.finish({'result':flow.last},{'deliver':'aggregate'})
        fixed,finish=repair_delivery_filter(flow,{'result':flow.last},caught.exception.repair_predicate,'detail')
        self.assertEqual(fixed.finish(finish,{'deliver':'aggregate'})['rows'],[['甲','30']])

    def test_comma_separated_or_is_not_narrowed_by_single_category_shortcut(self):
        source=table(['状态','来源'],[['完成','外部'],['复核通过','内部'],['复核通过','外部']])
        flow=TableFlow(source,'只看完成的，或者复核通过且来源为内部的记录。')
        flow.apply({'tool':'filter','where':{'all':[{'field':'状态','op':'in','value':['完成','复核通过']},{'field':'来源','op':'eq','value':'内部'}]}})
        self.assertEqual(flow.finish({'result':flow.last},{'deliver':'detail'})['rows'],[['完成','外部'],['复核通过','内部']])

    def test_explicit_first_dedup_precedes_filters_and_cannot_be_bypassed(self):
        source=table(['编号','状态','金额（元）'],[['A','不符','100'],['A','有效','300'],['B','有效','200']])
        goal='先按编号保留原表首次记录，之后只看状态为有效的，按金额汇总。'
        flow=TableFlow(source,goal);keys=initial_distinct_keys(goal,flow.views['V0']['columns']);self.assertEqual(keys,['编号'])
        first=flow.enable_initial_distinct(keys)
        action={'tool':'filter','input':'V0','where':{'field':'状态','op':'eq','value':'有效'}}
        flow.apply(action);self.assertEqual(action['input'],first['view'])
        self.assertEqual(flow.views[flow.last]['rows'],[['B','有效','200']])
        with self.assertRaises(TableError):flow.finish({'result':'V0'},{'deliver':'detail','initial_distinct_keys':keys})
        self.assertIsNone(initial_distinct_keys('先排除无效记录，先按编号保留首次记录。',source['columns']))
        self.assertIsNone(initial_distinct_keys('不要先按编号保留原表首次记录。',source['columns']))

    def test_named_append_preserves_user_file_order(self):
        def book(id,name,code):return {'id':id,'file':name,'sheet':'登记','width':2,'row_count':2,'error':'','limited':False,'merges':[],'matrix':[['编号','金额（元）'],[code,'10']]}
        first=book('T1','甲.xlsx','A');second=book('T2','乙.xlsx','B')
        _,source=automatic_append([first,second],'合并乙和甲的登记，先按编号保留原表首次记录。')
        self.assertEqual([r[0] for r in source['rows']],['B','A'])

    def test_record_bound_followup_replays_before_group_without_model(self):
        source=table(['线路','状态','费用（元）'],[['甲','有效','100'],['甲','有效','300'],['乙','有效','250'],['乙','取消','1000']])
        old_goal='只看有效记录，按线路汇总费用，按费用合计降序。'
        old=TableFlow(source,old_goal)
        old.apply({'tool':'filter','where':{'field':'状态','op':'eq','value':'有效'}})
        old.apply({'tool':'group','by':['线路'],'metrics':[{'function':'sum','field':'费用','name':'费用合计'},{'function':'count','name':'条数'}]})
        old.apply({'tool':'sort','by':[{'field':'费用合计','direction':'desc'}]})
        finish={'result':old.last};contract={'deliver':'aggregate','write':'','docx':False}
        prior=old.finish(finish,contract)
        config={'mode':'flow','previous_result':None,'flow':{'graph':deepcopy(old.graph),'finish':freeze_finish(old,finish),'contract':contract,'expected':fingerprint(prior)}}
        parent={'id':'verified-parent','prompt':old_goal,'workbook':config}
        goal='只统计单笔费用不少于200元的原始登记，仍按线路汇总，其他要求不变。'
        with redirect_stdout(io.StringIO()):result=try_revision(no_model(),source,goal,parent,prior)
        self.assertIsNotNone(result)
        flow,new_contract,_,table_result,_=result
        self.assertEqual(table_result['rows'],[['甲','300','1'],['乙','250','1']])
        self.assertTrue(new_contract['revision']['record_granularity'])
        from workbook_requirements import raw_numeric_requirements
        self.assertFalse(covered_raw_revision('只统计单笔费用不少于200元，改按状态汇总，其他不变。',raw_numeric_requirements(goal,old.views['V0']),old,3))


if __name__=='__main__':unittest.main()
