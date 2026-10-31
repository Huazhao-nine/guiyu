"""Atomic expansion of bounded workbook actions into checked primitives."""
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
from workbook_flow import TableFlow,fingerprint,freeze_finish,plan_actions,replay


def table(columns,rows):
    return {'columns':columns,'rows':rows,'provenance':[[i] for i in range(len(rows))],'notes':[]}


class CompoundActionTests(unittest.TestCase):
    def test_repeated_repair_payload_counts_failures_changes_context_and_keeps_failure_bound(self):
        class Model:
            def __init__(self,answers):self.answers=list(answers);self.calls=[]
            def generate(self,system,user,**kwargs):
                self.calls.append({'system':system,'payload':json.loads(user),'kwargs':kwargs})
                return json.dumps(self.answers.pop(0),ensure_ascii=False),{'tokens':1,'seconds':0}
        def office(answers):
            return SimpleNamespace(agent=SimpleNamespace(model=Model(answers)),
                core=SimpleNamespace(emit=lambda *a,**k:None),workbook_metrics={'tokens':0,'peak_memory_gb':0})
        contract={'title':'副本','deliver':'detail','detail_request':''}
        bad={'tool':'derive','name':'副本','formula':'[数额]','having':{'field':'数额','op':'gt','value':0}}
        source=table(['数额'],[['3']])
        recovering=office([contract,bad,bad,{'tool':'derive','name':'副本','formula':'[数额]'},
                           {'tool':'finish','result':'V1'},{'state':'passed'}])
        with redirect_stdout(io.StringIO()):flow,_,_,result,failures=plan_actions(recovering,source,'计算副本。')
        first,second=recovering.agent.model.calls[2:4]
        self.assertEqual([first['payload']['总失败次数'],second['payload']['总失败次数']],[1,2])
        self.assertEqual([first['payload']['同一动作及错误失败次数'],second['payload']['同一动作及错误失败次数']],[1,2])
        self.assertNotEqual(first['payload'],second['payload']);self.assertIn('不能再次返回相同动作',second['system'])
        self.assertEqual(len(second['payload']['最近失败摘要']),2)
        self.assertTrue(all(len(item['动作JSON'])<=800 and len(item['error'])<=300 for item in second['payload']['最近失败摘要']))
        self.assertEqual([first['kwargs']['temperature'],second['kwargs']['temperature']],[0,0])
        self.assertEqual(result['rows'],[['3','3']]);self.assertEqual(len(failures),2);self.assertEqual(len(flow.graph),1)
        repeated=office([contract,bad,bad,bad,bad])
        with redirect_stdout(io.StringIO()),self.assertRaisesRegex(TableError,'最后遇到'):
            plan_actions(repeated,source,'计算副本。')
        self.assertEqual(len(repeated.agent.model.calls),5)
        self.assertEqual(repeated.agent.model.calls[-1]['payload']['总失败次数'],3)

    def test_source_guard_runs_before_division_and_derived_condition_runs_after(self):
        source=table(['项目','总额（元）','基数'],[['A','10','0'],['B','30','3'],['C','12','4']]);original=deepcopy(source)
        flow=TableFlow(source,'基数大于0，计算均额，均额不少于5元。')
        action={'tool':'derive','name':'均额','formula':'[总额（元）]/[基数]',
                'where':{'all':[{'field':'基数','op':'gt','value':0},{'field':'均额','op':'gte','value':5}]},'output':'V3'}
        event=flow.apply(action)
        self.assertEqual([step['operation']['op'] for step in flow.graph],['filter','derive','filter'])
        self.assertEqual(event['view'],'V3');self.assertEqual(event['primitive_views'],['V1','V2','V3'])
        self.assertEqual(event['input_rows'],3);self.assertEqual(flow.views[event['view']]['rows'],[['B','30','3','10']])
        self.assertEqual(source,original)
        finish={'result':event['view'],'fields':['项目','均额']};contract={'deliver':'detail'}
        result=flow.finish(finish,contract)
        config={'flow':{'graph':flow.graph,'finish':freeze_finish(flow,finish),'contract':contract,'expected':fingerprint(result)}}
        self.assertEqual(replay(source,config)['rows'],result['rows'])

    def test_existing_only_condition_precedes_derive_and_new_only_condition_follows(self):
        source=table(['分子','分母'],[['10','0'],['30','3'],['12','4']])
        old=TableFlow(source,'分母大于0，计算比值。')
        old.apply({'tool':'derive','name':'比值','formula':'[分子]/[分母]','where':{'field':'分母','op':'gt','value':0}})
        self.assertEqual([s['operation']['op'] for s in old.graph],['filter','derive'])
        new=TableFlow(table(['数额'],[['3'],['8']]),'计算两倍数额，结果至少10。')
        new.apply({'tool':'derive','name':'两倍','formula':'[数额]*2','where':{'field':'两倍','op':'gte','value':10}})
        self.assertEqual([s['operation']['op'] for s in new.graph],['derive','filter'])
        self.assertEqual(new.views[new.last]['rows'],[['8','16']])

    def test_filter_sort_select_sorts_before_dropping_sort_column(self):
        source=table(['项目','排序量','分类'],[['A','3','保留'],['B','1','保留'],['C','2','去掉']])
        flow=TableFlow(source,'只要保留分类，按排序量升序，仅保留项目。')
        event=flow.apply({'tool':'filter','where':{'field':'分类','op':'eq','value':'保留'},
                          'select':['项目'],'sort':[{'field':'排序量','direction':'asc'}],'output':'V3'})
        self.assertEqual([s['operation']['op'] for s in flow.graph],['filter','sort','select'])
        self.assertEqual(flow.views[event['view']]['rows'],[['B'],['A']])
        self.assertEqual(flow.views['V2']['columns'],source['columns'])
        self.assertEqual(event['view'],flow.last)

    def test_envelope_and_nested_parameter_shapes_preserve_arguments(self):
        flow=TableFlow(table(['名称','数额'],[['A','2'],['B','1']]),'数额至少1，降序，只保留名称。')
        event=flow.apply({'tool':'filter','arguments':{'where':[{'field':'数额','op':'gte','value':1}],
            'sort':{'by':[{'field':'数额','order':'desc','ascending':False}]},'select':{'columns':['名称']}}})
        self.assertEqual(flow.views[event['view']]['rows'],[['A'],['B']])

    def test_invalid_projection_rolls_back_all_state_and_does_not_switch_branches(self):
        source=table(['名称','数额（元）'],[['A','2'],['B','1']]);flow=TableFlow(source,'数额至少1。')
        before=deepcopy(flow.__dict__)
        with self.assertRaises(TableError):
            flow.apply({'tool':'filter','where':{'field':'数额','op':'gte','value':1},
                        'sort':[{'field':'数额','direction':'desc'}],'select':['未知字段']})
        self.assertEqual(flow.__dict__,before)

    def test_late_derived_constraint_error_rolls_back_registry_and_presentation(self):
        flow=TableFlow(table(['数额（元）'],[['100']]),'计算副本。');before=deepcopy(flow.__dict__)
        with self.assertRaisesRegex(TableError,'没有来自用户要求'):
            flow.apply({'tool':'derive','name':'副本','formula':'[数额（元）]','display_units':{'副本':'万元'},
                        'where':{'field':'副本','op':'gte','value':17}})
        self.assertEqual(flow.__dict__,before)

    def test_mixed_or_batch_derive_and_empty_conditions_are_rejected_atomically(self):
        flow=TableFlow(table(['分子','分母'],[['10','0'],['12','3']]),'分母大于0，结果至少2。')
        actions=[{'tool':'derive','name':'比值','formula':'[分子]/[分母]',
                  'where':{'any':[{'field':'分母','op':'gt','value':0},{'field':'比值','op':'gte','value':2}]}},
                 {'tool':'derive','fields':[{'name':'副本','formula':'[分子]'}],'where':{'field':'分母','op':'gt','value':0}},
                 {'tool':'derive','name':'副本','formula':'[分子]','where':{'all':[]}}]
        for action in actions:
            before=deepcopy(flow.__dict__)
            with self.subTest(action=action),self.assertRaises(TableError):flow.apply(action)
            self.assertEqual(flow.__dict__,before)

    def test_unknown_parameters_code_wrong_units_and_sort_conflicts_are_rejected(self):
        source=table(['数额（元）','时间（分钟）'],[['100','5']])
        base={'tool':'filter','where':{'field':'数额','op':'gt','value':0},'select':['数额']}
        actions=[dict(base,limit=1),dict(base,sort={'by':[{'field':'数额'}],'limit':1}),
                 dict(base,sort=[{'field':'数额','direction':'asc','order':'desc'}]),
                 dict(base,sort=[{'field':'数额','ascending':'false'}]),
                 dict(base,select={'fields':['数额'],'input':'V0'}),
                 {'tool':'derive','name':'执行','formula':'__import__("os")','where':{'field':'数额','op':'gt','value':0}},
                 {'tool':'derive','name':'副本','formula':'[数额（元）]','where':{'field':'副本','op':'gt','other':'时间'}}]
        for action in actions:
            flow=TableFlow(source,'只看数额大于0。');before=deepcopy(flow.__dict__)
            with self.subTest(action=action),self.assertRaises(TableError):flow.apply(action)
            self.assertEqual(flow.__dict__,before)

    def test_graph_limit_and_incorrect_output_roll_back_whole_compound(self):
        flow=TableFlow(table(['数值'],[['2']]),'保留结果。')
        for i in range(15):flow.record(flow.last,{'op':'derive','name':'副本'+str(i),'expression':{'column':'数值'},'format':'number','precision':8})
        before=deepcopy(flow.__dict__)
        with self.assertRaisesRegex(TableError,'16项'):
            flow.apply({'tool':'filter','where':{'field':'数值','op':'gt','value':0},'select':['数值']})
        self.assertEqual(flow.__dict__,before)
        fresh=TableFlow(table(['数值'],[['2']]),'保留结果。');before=deepcopy(fresh.__dict__)
        with self.assertRaisesRegex(TableError,'最终视图'):
            fresh.apply({'tool':'filter','where':{'field':'数值','op':'gt','value':0},'select':['数值'],'output':'V1'})
        self.assertEqual(fresh.__dict__,before)

    def test_presentation_only_derive_uses_actual_final_view_and_source_values(self):
        flow=TableFlow(table(['时长（分钟）'],[['120'],['30']]),'时长大于0，以小时显示。')
        event=flow.apply({'tool':'derive','name':'时长（小时）','formula':'[时长（分钟）]/60',
                          'where':{'field':'时长（分钟）','op':'gt','value':0},'output':'V1'})
        self.assertEqual(event['view'],'V1');self.assertEqual(len(flow.graph),1)
        self.assertEqual(flow.views[flow.last]['rows'],[['120'],['30']])
        self.assertEqual(flow.finish({'result':event['view']},{'deliver':'detail'})['rows'],[['2'],['0.5']])

    def test_future_handles_are_rejected_as_numeric_references_but_text_values_are_kept(self):
        source=table(['甲值','乙值'],[['3','5']])
        for target in ('F3',{'field':'F3'}):
            flow=TableFlow(source,'计算差值。');before=deepcopy(flow.__dict__)
            with self.subTest(target=target),self.assertRaisesRegex(TableError,'不能猜测'):
                flow.apply({'tool':'derive','name':'差值','formula':'[甲值]-[乙值]',
                            'where':{'field':'甲值','op':'lt','value':target}})
            self.assertEqual(flow.__dict__,before)
        flow=TableFlow(table(['分类','数额'],[['F3','3'],['F4','5']]),'只看分类F3并计算数额副本。')
        flow.apply({'tool':'derive','name':'副本','formula':'[数额]','where':{'field':'分类','op':'eq','value':'F3'}})
        self.assertEqual(flow.views[flow.last]['rows'],[['F3','3','3']])

    def test_mock_planner_preserves_feedback_ids_and_replays_both_compound_forms(self):
        class Model:
            def __init__(self,answers):self.answers=list(answers);self.calls=0
            def generate(self,*args,**kwargs):
                self.calls+=1
                return json.dumps(self.answers.pop(0),ensure_ascii=False),{'tokens':10,'seconds':0}
        answers=[{'title':'均额','deliver':'detail','detail_request':''},
            {'tool':'derive','name':'均额','formula':'[总额（元）]/[基数]','display_units':'元','summaries':[],
             'where':{'all':[{'field':'基数','op':'gt','value':0},{'field':'均额','op':'gte','value':5}]}},
            {'tool':'filter','where':{'field':'均额','op':'gte','value':5},
             'sort':[{'field':'总额','direction':'desc'}],'select':['项目','均额']},
            {'tool':'finish','result':'V5'},{'state':'passed'}]
        calls=[];office=SimpleNamespace(agent=SimpleNamespace(model=Model(answers)),
            core=SimpleNamespace(emit=lambda *a,**k:calls.append((a,k))),workbook_metrics={'tokens':0,'peak_memory_gb':0})
        source=table(['项目','总额（元）','基数'],[['A','10','0'],['B','30','3'],['C','12','4'],['D','60','6']])
        goal='基数大于0，计算均额，均额不少于5元，按总额降序，只保留项目、均额两列。'
        with redirect_stdout(io.StringIO()):flow,contract,finish,result,failures=plan_actions(office,source,goal)
        self.assertEqual(failures,[]);self.assertEqual(office.agent.model.calls,5)
        self.assertEqual(office.workbook_metrics.get('argument_normalizations'),1)
        self.assertEqual(result['rows'],[['D','10'],['B','10']]);self.assertEqual(finish['result'],'V5')
        self.assertEqual([s['operation']['op'] for s in flow.graph],['filter','derive','filter','sort','select'])
        self.assertTrue(any(args==('tool_call',) for args,_ in calls))
        self.assertEqual(replay(source,{'flow':{'graph':flow.graph,'finish':finish,'contract':contract,'expected':fingerprint(result)}})['rows'],result['rows'])


if __name__=='__main__':unittest.main()
