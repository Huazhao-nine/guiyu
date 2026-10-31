"""Changing a delivery format must not discard a prior result's data scope."""
import sys,unittest
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from workbook_flow import TableFlow,freeze_finish,fingerprint
from workbook_revision import try_delivery_reuse,delivery_only_request
from workbook_recovery import previous_scope_proof

class DeliveryReuseTests(unittest.TestCase):
    def make(self):
        source={'columns':['科室','费用（元）','状态'],'rows':[['甲','80','有效'],['乙','50','有效'],['乙','900','撤销']],'provenance':[[0],[1],[2]],'locations':[],'inputs':['虚构.csv'],'notes':[]}
        first=TableFlow(source,'只统计有效记录，按科室合计费用。')
        first.apply({'tool':'filter','where':{'field':'状态','op':'eq','value':'有效'}})
        first.apply({'tool':'group','by':['科室'],'metrics':[{'function':'sum','field':'费用（元）','name':'累计额'}]})
        first.apply({'tool':'sort','by':[{'field':'累计额（元）','direction':'desc'}]})
        prior=first.finish({'result':first.last},{'deliver':'aggregate'})
        # Simulate a verified result followed by another turn on that result.
        current=TableFlow(source,'只要第一名，其他条件不变。',prior,previous_shape='aggregate')
        current.verified_previous_scope=True
        current.apply({'tool':'limit','input':'P0','count':1})
        contract={'title':'科室费用','deliver':'aggregate','docx':False,'write':'','requirements':['只统计有效记录，按科室合计费用。','只要第一名，其他条件不变。']}
        finish=freeze_finish(current,{'result':current.last});result=current.finish(finish,contract)
        config={'mode':'flow','previous_result':prior,'previous_shape':'aggregate','flow':{'graph':current.graph,'finish':finish,'contract':contract,'expected':fingerprint(result),'previous_scope_proof':previous_scope_proof(current)}}
        parent={'id':'previous','snapshot':{'virtual-source':'a'*64},'workbook':config}
        old={'result_table':result,'snapshot':dict(parent['snapshot'])}
        return source,parent,old,result
    def test_export_replays_the_exact_nested_result_and_keeps_requirements(self):
        source,parent,old,previous=self.make()
        value=try_delivery_reuse(source,'把上轮结果再导出一份Word，其他口径和列不变。',parent,old)
        self.assertIsNotNone(value);flow,contract,finish,result,repairs=value
        self.assertEqual(result['columns'],previous['columns']);self.assertEqual(result['rows'],[['甲','80']])
        self.assertTrue(contract['docx']);self.assertTrue(contract['delivery_revision']['data_unchanged'])
        self.assertIn('只统计有效记录，按科室合计费用。',contract['requirements'])
    def test_reference_to_already_singular_first_place_does_not_expand_data(self):
        source,parent,old,previous=self.make()
        value=try_delivery_reuse(source,'回到刚才的费用汇总，给第一名的结果再导出一份Word，其他口径和列不变。',parent,old)
        self.assertIsNotNone(value);self.assertEqual(value[3]['rows'],previous['rows'])
    def test_new_data_requirements_are_not_treated_as_format_changes(self):
        for goal in ('只要第一名，导出Word，其他条件不变。','只要前三名，导出Word，其他条件不变。','把门槛改成500元，再导出Word。','按状态重新分组，其他条件不变，导出Word。','只保留科室一列，导出Word。','换另一份工作簿，导出Word。'):
            self.assertFalse(delivery_only_request(goal,3),goal)
    def test_changed_saved_result_or_source_snapshot_cannot_be_reused(self):
        source,parent,old,_=self.make();goal='把上轮结果导出Word，其他条件不变。'
        old['result_table']['rows'][0][1]='900'
        self.assertIsNone(try_delivery_reuse(source,goal,parent,old))
        source,parent,old,_=self.make();old['snapshot']['virtual-source']='b'*64
        self.assertIsNone(try_delivery_reuse(source,goal,parent,old))
    def test_tampered_prior_result_proof_cannot_be_reused(self):
        source,parent,old,_=self.make();parent['workbook']['previous_result']['rows'][0][1]='900'
        self.assertIsNone(try_delivery_reuse(source,'把上轮结果导出Word，其他条件不变。',parent,old))
    def test_cancel_word_changes_only_the_delivery_contract(self):
        source,parent,old,previous=self.make();value=try_delivery_reuse(source,'其他条件不变，不用Word。',parent,old)
        self.assertIsNotNone(value);self.assertFalse(value[1]['docx']);self.assertEqual(value[3]['rows'],previous['rows'])

if __name__=='__main__':unittest.main()
