"""Local behavior checks for canonical arithmetic and field-bound display units."""
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
from table_semantics import canonical_table
from workbook_flow import TableFlow,fingerprint,freeze_finish,plan_actions,replay
from workbook_intent import normalize_action,validate_action


def table(columns,rows):
    return {'columns':columns,'rows':rows,'provenance':[[i] for i in range(len(rows))],
            'inputs':['fictional-a.csv','fictional-b.csv'],'notes':[]}


class UnitPresentationTests(unittest.TestCase):
    def test_single_derive_scalar_unit_and_empty_summaries_normalize_without_changing_values(self):
        for source_unit,target,value,expected in (('分钟','小时','150','2.5'),('元','万元','25000','2.5'),('g','kg','2500','2.5')):
            with self.subTest(target=target):
                source=table(['输入（'+source_unit+'）'],[[value]])
                action={'tool':'derive','name':'显示量','formula':'[输入（'+source_unit+'）]',
                        'display_units':target,'summaries':[]};before=deepcopy(action)
                normalized=normalize_action(action)
                self.assertEqual(action,before);self.assertNotIn('summaries',normalized)
                self.assertEqual(normalized['display_units'],{'显示量':target})
                self.assertEqual(normalize_action(normalized),normalized)
                flow=TableFlow(source,'计算显示量。');flow.apply(action)
                self.assertEqual(flow.views[flow.last]['rows'],[[value,value]])
                self.assertEqual(flow.finish({'fields':['显示量']},{'deliver':'detail'})['rows'],[[expected]])

    def test_batch_field_scalar_units_bind_each_name_and_single_outer_scalar_is_unambiguous(self):
        source=table(['时长（分钟）','费用（元）'],[['150','25000']])
        flow=TableFlow(source,'计算工时和费用副本。')
        flow.apply({'tool':'derive','summaries':[],'fields':[
            {'name':'工时','formula':'[时长（分钟）]','display_units':'小时'},
            {'name':'费用副本','formula':'[费用（元）]','display_units':'万元','summaries':[]}]})
        result=flow.finish({'fields':['工时','费用副本']},{'deliver':'detail'})
        self.assertEqual(result['rows'],[['2.5','2.5']])
        single=TableFlow(source,'计算工时。')
        single.apply({'tool':'derive','fields':[{'name':'工时','formula':'[时长（分钟）]'}],'display_units':'小时'})
        self.assertEqual(single.finish({'fields':['工时']},{'deliver':'detail'})['rows'],[['2.5']])

    def test_representation_recovery_rejects_ambiguous_units_conflicts_and_nonempty_summaries(self):
        source=table(['时长（分钟）','费用（元）'],[['150','25000']])
        base={'tool':'derive','name':'副本','formula':'[费用（元）]'}
        actions=[dict(base,summaries=['V0']),dict(base,summaries={}),dict(base,display_units='unknown'),
                 dict(base,display_units='小时'),dict(base,display_units='万元',having={'field':'费用','op':'gt','value':0}),
                 {'tool':'derive','name':'副本（万元）','formula':'[费用（元）]','display_units':'千元'},
                 {'tool':'derive','fields':[{'name':'甲','formula':'[时长（分钟）]'},
                                           {'name':'乙','formula':'[时长（分钟）]'}],'display_units':'小时'},
                 {'tool':'derive','fields':[{'name':'甲','formula':'[时长（分钟）]','display_units':'小时'}],
                  'display_units':'分钟'},
                 {'tool':'derive','fields':[{'name':'甲','formula':'[时长（分钟）]'},
                                           {'name':'乙','formula':'[费用（元）]','display_units':'小时'}]}]
        for action in actions:
            flow=TableFlow(source,'整理资料。');before=deepcopy(flow.__dict__)
            with self.subTest(action=action),self.assertRaises(TableError):flow.apply(action)
            self.assertEqual(flow.__dict__,before)

    def test_scalar_display_unit_preserves_explicit_business_division(self):
        flow=TableFlow(table(['金额（元）'],[['100000']]),'每笔金额除以10000作为实发金额，然后全部以万元显示。')
        flow.apply({'tool':'derive','name':'实发金额','formula':'[金额（元）]/10000','display_units':'万元','summaries':[]})
        self.assertIn('divide',flow.graph[-1]['operation']['expression'])
        self.assertEqual(flow.views[flow.last]['rows'],[['100000','10']])
        self.assertEqual(flow.finish({'fields':['实发金额']},{'deliver':'detail'})['rows'],[['0.001']])

    def test_derive_display_mapping_keeps_arithmetic_and_other_fields_canonical(self):
        source=table(['承诺（万元）','实付（元）'],[['1.8','3000']]);before=deepcopy(source)
        flow=TableFlow(source,'计算余额并保留原字段。')
        flow.apply({'tool':'derive','name':'余额','formula':'[承诺（元）]-[实付（元）]',
                    'display_units':{'余额':'万元'}})
        self.assertEqual(flow.views[flow.last]['rows'],[['18000','3000','15000']])
        result=flow.finish({'result':flow.last},{'deliver':'detail'})
        self.assertEqual(result['columns'],['承诺（元）','实付（元）','余额（万元）'])
        self.assertEqual(result['rows'],[['18000','3000','1.5']])
        self.assertEqual(source,before)

    def test_grouped_duration_can_be_renamed_and_displayed_in_hours_without_threshold(self):
        source=table(['小组','时长（分钟）'],[['东','1小时'],['东','45分钟'],['西','30分钟']])
        flow=TableFlow(source,'按小组统计总工时（小时）。')
        flow.apply({'tool':'group','by':['小组'],'metrics':[{'function':'sum','field':'时长（分钟）','name':'累计时长'}]})
        event=flow.apply({'tool':'derive','name':'总工时（小时）','formula':'[累计时长（分钟）]/60'})
        self.assertEqual(flow.graph[-1]['operation']['expression'],{'column':'累计时长（分钟）'})
        self.assertEqual(flow.views[event['view']]['rows'],[['东','105','105'],['西','30','30']])
        # Any later sorting/filtering continues to see minutes. The conversion
        # ratio has not become permission to add a numeric filter threshold.
        with self.assertRaisesRegex(TableError,'没有来自用户要求'):
            flow.apply({'tool':'filter','where':{'field':'总工时','op':'gte','value':60}})
        finish={'result':flow.last,'fields':['小组','总工时']}
        result=flow.finish(finish,{'deliver':'aggregate'})
        self.assertEqual(result['columns'],['小组','总工时（小时）'])
        self.assertEqual(result['rows'],[['东','1.75'],['西','0.5']])
        config={'flow':{'graph':flow.graph,'finish':freeze_finish(flow,finish),'contract':{'deliver':'aggregate'},'expected':fingerprint(result)}}
        self.assertEqual(replay(source,config)['rows'],result['rows'])
        self.assertEqual(canonical_table(result)['rows'],[['东','105'],['西','30']])

    def test_known_unit_ratios_normalize_only_direct_aliases(self):
        for unit,values,target,divisor in (
                ('元',['24000','4000'],'万元',10000),
                ('分钟',['150','30'],'小时',60),
                ('g',['2600','100'],'kg',1000)):
            with self.subTest(unit=unit):
                source=table(['前项（'+unit+'）','后项（'+unit+'）'],[values])
                flow=TableFlow(source,'计算显示量。')
                flow.apply({'tool':'derive','name':'差额（'+target+'）',
                            'formula':'[前项（'+unit+'）]/'+str(divisor)})
                self.assertEqual(flow.graph[-1]['operation']['expression'],{'column':'前项（'+unit+'）'})
                self.assertEqual(canonical_table(flow.finish({'result':flow.last,'fields':['差额']},{'deliver':'detail'}))['rows'],[[values[0]]])
                for formula in ('([前项（'+unit+'）]-[后项（'+unit+'）])/'+str(divisor),
                                '([前项（'+unit+'）]+17)/'+str(divisor)):
                    failed=TableFlow(source,'计算两项差额。')
                    with self.assertRaisesRegex(TableError,'没有来自用户要求'):
                        failed.apply({'tool':'derive','name':'差额（'+target+'）','formula':formula})
                    self.assertEqual(failed.graph,[])

    def test_user_business_division_is_preserved_before_display_conversion(self):
        for goal in ('每笔金额除以10000作为实发金额，然后全部以万元显示。',
                     '计算每人金额=总额/10000，结果以万元显示。'):
            with self.subTest(goal=goal):
                flow=TableFlow(table(['金额（元）'],[['100000']]),goal)
                flow.apply({'tool':'derive','name':'实发金额','formula':'[金额（元）]/10000'})
                self.assertIn('divide',flow.graph[-1]['operation']['expression'])
                self.assertEqual(flow.views[flow.last]['rows'],[['100000','10']])
                self.assertEqual(flow.finish({'fields':['实发金额']},{'deliver':'detail'})['rows'],[['0.001']])
        flow=TableFlow(table(['总时长（分钟）'],[['7200']]),'把总工时分给60人，每人以小时显示。')
        flow.apply({'tool':'derive','name':'每人工时（小时）','formula':'[总时长（分钟）]/60'})
        self.assertIn('divide',flow.graph[-1]['operation']['expression'])
        self.assertEqual(flow.finish({'fields':['每人工时']},{'deliver':'detail'})['rows'],[['2']])

    def test_ambiguous_or_denied_numeric_division_requires_display_metadata(self):
        for goal in ('时长不少于60分钟，以小时显示。','不要除以60，只用小时显示。','把分钟数除以60换算成小时。'):
            flow=TableFlow(table(['时长（分钟）'],[['120']]),goal)
            with self.subTest(goal=goal),self.assertRaisesRegex(TableError,'不能自动当作展示换算'):
                flow.apply({'tool':'derive','name':'时长（小时）','formula':'[时长（分钟）]/60'})
            self.assertEqual(flow.graph,[]);self.assertEqual(flow.presentation_fields,{})

    def test_only_verified_target_ratio_is_normalized(self):
        flow=TableFlow(table(['时长（分钟）'],[['150']]),'显示工时。')
        for action in (
                {'name':'工时（小时）','formula':'[时长（分钟）]/59'},
                {'name':'工时','formula':'[时长（分钟）]/60'},
                {'name':'工时（小时）','formula':'[时长（分钟）]*60'},
                {'name':'工时（小时）','formula':{'divide':[{'column':'时长（分钟）'},{'constant':'60分钟'}]}},
                {'name':'工时（元）','formula':'[时长（分钟）]/60'},
                {'name':'工时（小时）','formula':'[时长（分钟）]/60','display_units':{'工时':'kg'}},
                {'name':'工时（小时）','formula':'__import__("os")'},
                {'name':'工时（小时）','formula':'60/60'}):
            with self.subTest(action=action),self.assertRaises(TableError):flow.apply(dict(action,tool='derive'))
            self.assertEqual(flow.graph,[]);self.assertEqual(flow.presentation_fields,{})
        flow.apply({'tool':'derive','name':'工时','formula':'[时长（分钟）]/60','display_units':{'工时':'小时'}})
        self.assertEqual(flow.finish({'fields':['工时']},{'deliver':'detail'})['rows'],[['2.5']])

    def test_batch_display_preferences_are_validated_and_rolled_back_together(self):
        source=table(['收入（元）','支出（元）'],[['16000','4000']])
        fields=[{'name':'净额','formula':'[收入（元）]-[支出（元）]','display_units':{'净额':'万元'}},
                {'name':'两倍净额','formula':'[净额]*2'}]
        flow=TableFlow(source,'计算净额和乘以2的结果。')
        before=deepcopy(flow.__dict__)
        with self.assertRaisesRegex(TableError,'字段不在'):
            flow.apply({'tool':'derive','fields':deepcopy(fields),'display_units':{'未生成字段':'万元'}})
        self.assertEqual(flow.__dict__,before)
        with self.assertRaisesRegex(TableError,'冲突'):
            flow.apply({'tool':'derive','fields':deepcopy(fields),'display_units':{'净额':'千元'}})
        self.assertEqual(flow.__dict__,before)
        flow.apply({'tool':'derive','fields':fields,'display_units':{'两倍净额':'千元'}})
        result=flow.finish({'fields':['净额','两倍净额']},{'deliver':'detail'})
        self.assertEqual(result['columns'],['净额（万元）','两倍净额（千元）'])
        self.assertEqual(result['rows'],[['1.2','24']])
        for invalid in ({'净额':3},['万元'],{'净额':'unknown'}):
            failed=TableFlow(source,'计算净额。')
            with self.assertRaises(TableError):
                failed.apply({'tool':'derive','name':'净额','formula':'[收入（元）]-[支出（元）]','display_units':invalid})
            self.assertEqual(failed.graph,[])

    def test_same_column_presentation_is_field_specific_and_base_unit_goal_can_override_it(self):
        flow=TableFlow(table(['记录时长（小时）','服务时长（分钟）'],[['2','45']]),'整理时长。')
        event=flow.apply({'tool':'derive','name':'记录时长（小时）','formula':'[记录时长（分钟）]/60'})
        self.assertTrue(event['presentation_only']);self.assertEqual(flow.graph,[])
        result=flow.finish({'result':'V0'},{'deliver':'detail'})
        self.assertEqual(result['columns'],['记录时长（小时）','服务时长（分钟）'])
        self.assertEqual(result['rows'],[['2','45']])
        self.assertEqual(flow.finish({'result':'V0','display_units':{'记录时长':'分钟'}},{'deliver':'detail'})['rows'],[['120','45']])
        flow.current_goal='以分钟显示。'
        self.assertEqual(flow.finish({'result':'V0'},{'deliver':'detail'})['rows'],[['120','45']])

    def test_derive_cannot_absorb_unknown_conditions_into_display_metadata(self):
        with self.assertRaisesRegex(TableError,'不接受参数'):
            validate_action({'tool':'derive','name':'工时','formula':'[时长]',
                             'display_units':{'工时':'小时'},'having':{'field':'小组','op':'eq','value':'东'}})
        flow=TableFlow(table(['金额（元）'],[['1000']]),'整理金额。')
        for mapping in ({'金额':'小时'},{'不存在':'元'},{'金额':'万元','金额（元）':'千元'}):
            with self.subTest(mapping=mapping),self.assertRaises(TableError):
                flow.apply({'tool':'derive','name':'副本','formula':'[金额]','display_units':mapping})
            self.assertEqual(flow.graph,[]);self.assertEqual(flow.presentation_fields,{})

    def test_presentation_only_action_still_validates_all_parameters_and_numeric_fields(self):
        flow=TableFlow(table(['时长（分钟）','标签'],[['120','本地']]),'整理时长。')
        for extra in ({'format':'python'},{'precision':True},{'precision':9},{'display_units':{'标签':'人'}}):
            with self.subTest(extra=extra),self.assertRaises(TableError):
                flow.apply({'tool':'derive','name':'时长（小时）','formula':'[时长（分钟）]/60',**extra})
            self.assertEqual(flow.graph,[]);self.assertEqual(flow.presentation_fields,{})

    def test_mock_planner_persists_field_preferences_in_finish_and_followup_contract(self):
        class Model:
            def __init__(self,answers):self.answers=list(answers);self.calls=0
            def generate(self,*args,**kwargs):
                self.calls+=1
                return json.dumps(self.answers.pop(0),ensure_ascii=False),{'tokens':10,'seconds':0}
        def office(answers):
            return SimpleNamespace(agent=SimpleNamespace(model=Model(answers)),
                core=SimpleNamespace(emit=lambda *a,**k:None),workbook_metrics={'tokens':0,'peak_memory_gb':0})
        source=table(['收入（元）','支出（元）'],[['16000','4000']])
        original=office([{'title':'净额','deliver':'detail','detail_request':''},
            {'tool':'derive','name':'净额','formula':'[收入（元）]-[支出（元）]','display_units':{'净额':'万元'}},
            {'tool':'finish','result':'V1'},{'state':'passed'}])
        with redirect_stdout(io.StringIO()):flow,contract,finish,result,failures=plan_actions(original,source,'计算净额。')
        self.assertEqual(failures,[]);self.assertEqual(original.agent.model.calls,4)
        self.assertEqual(contract['presentation_fields'],{'净额（元）':'万元'})
        self.assertEqual(finish['display_units'],{'净额（元）':'万元'})
        self.assertEqual(replay(source,{'flow':{'graph':flow.graph,'finish':finish,'contract':contract,'expected':fingerprint(result)}})['rows'],result['rows'])
        followup=office([{'title':'原结果','deliver':'detail','detail_request':''},
            {'tool':'finish','result':'P0'},{'state':'passed'}])
        with redirect_stdout(io.StringIO()):_,next_contract,_,next_result,failures=plan_actions(
            followup,source,'其他要求不变。',previous=result,previous_goal='计算净额。',previous_contract=contract,previous_shape='detail')
        self.assertEqual(failures,[]);self.assertEqual(next_contract['presentation_fields'],contract['presentation_fields'])
        self.assertEqual(next_result['columns'],result['columns']);self.assertEqual(next_result['rows'],result['rows'])


if __name__=='__main__':unittest.main()
