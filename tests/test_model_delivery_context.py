"""Keep row retention and displayed-unit review independent from model choice."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from workbook_agent import output_contract
from workbook_flow import TableFlow,delivery_review_payload,deferred_artifact_review


def no_model_office():
    def generate(*a,**k):raise AssertionError('No semantic mapping is needed here.')
    return SimpleNamespace(agent=SimpleNamespace(model=SimpleNamespace(generate=generate)),
                           core=SimpleNamespace(parse_json=json.loads,emit=lambda *a,**k:None),workbook_metrics={})


class RetentionProjectionTests(unittest.TestCase):
    def test_occurrences_are_not_output_columns(self):
        table={'columns':['编号','金额'],'rows':[]}
        for phrase in ['原表第一次出现的','表中第2次提交的记录','输入第十一条记录',
                       '各表最后一条记录','最早登记的记录','原始首次记录','每表最新一条版本']:
            with self.subTest(phrase=phrase):
                self.assertIsNone(output_contract(no_model_office(),'按编号处理，只保留'+phrase+'；随后按类别统计。',table,{}))
    def test_later_explicit_projection_is_still_enforced(self):
        table={'columns':['编号','金额','机构'],'rows':[]}
        self.assertEqual(output_contract(no_model_office(),'按编号去重，只保留原表第一次出现的记录；仅导出编号、金额两列。',table,{}),['编号','金额'])
    def test_negative_operation_after_comma_is_not_a_field(self):
        table={'columns':['编号','金额'],'rows':[]}
        for operation in ['不排序','不再筛选','不换算','不汇总']:
            with self.subTest(operation=operation):
                self.assertIsNone(output_contract(no_model_office(),'按编号保留第一次提交的记录，'+operation+'。',table,{}))
                self.assertEqual(output_contract(no_model_office(),'只导出编号、金额，'+operation+'。',table,{}),table['columns'])
    def test_row_retention_ends_at_its_clause_boundary(self):
        table={'columns':['流水ID','区域'],'rows':[]}
        for following in ['随后检查区域并统计','遇到空值时略过','之后仅纳入已核准项目']:
            with self.subTest(following=following):
                self.assertIsNone(output_contract(no_model_office(),'按流水ID只保留原表最早提交的记录，'+following+'。',table,{}))
    def test_real_column_with_row_sounding_name_is_not_discarded(self):
        table={'columns':['最早提交的记录','金额'],'rows':[]}
        self.assertEqual(output_contract(no_model_office(),'只要最早提交的记录，金额。',table,{}),table['columns'])
    def test_separate_row_delivery_does_not_expand_the_column_list(self):
        table={'columns':['订单号','差额（元）','其他'],'rows':[]}
        self.assertEqual(output_contract(no_model_office(),'只要订单号、差额，保留逐条明细并附加整批合计。',table,{}),['订单号','差额（元）'])
    def test_real_retention_named_column_is_not_a_new_operation(self):
        table={'columns':['编号','保留明细','保留记录数'],'rows':[]}
        self.assertEqual(output_contract(no_model_office(),'只保留编号，保留明细，保留记录数三列。',table,{}),table['columns'])
    def test_occurrence_named_fields_are_preserved(self):
        for name in ['首次登记日期','第一次出现的日期','最早记录日期','最新版本号']:
            with self.subTest(name=name):
                table={'columns':[name,'金额'],'rows':[]}
                self.assertEqual(output_contract(no_model_office(),'只保留'+name+'、金额两列。',table,{}),[name,'金额'])
    def test_quoted_row_sounding_column_is_an_explicit_field(self):
        table={'columns':['第一条记录','金额'],'rows':[]}
        self.assertEqual(output_contract(no_model_office(),'只保留“第一条记录”、金额。',table,{}),table['columns'])


class DisplayedReviewTests(unittest.TestCase):
    def source(self):
        return {'columns':['小组','工作量（分钟）'],'rows':[['甲','120'],['乙','90']],
                'provenance':[[0],[1]],'inputs':['虚构.csv'],'notes':[]}
    def test_review_uses_displayed_unit_and_remaps_contract_without_mutation(self):
        flow=TableFlow(self.source(),'工作量用小时显示。')
        contract={'deliver':'detail','docx':True,'column_bindings':[{'requested':'工作量','column':'工作量（分钟）'}]}
        before=deepcopy(contract);original=deepcopy(flow.views['V0'])
        result=flow.finish({'result':'V0'},contract)
        payload=delivery_review_payload(flow.current_goal,'',contract,flow,result)
        self.assertEqual(result['rows'],[['甲','2'],['乙','1.5']])
        field=payload['最终明细']['fields'][1]
        self.assertEqual((field['column'],field['unit']),('工作量（小时）','小时'))
        self.assertEqual(payload['交付约定']['column_bindings'][0]['column'],'工作量（小时）')
        self.assertEqual(contract,before);self.assertEqual(flow.views['V0'],original)
        self.assertIn('核对',payload['后续交付']['Word']);self.assertNotIn('state',payload)
    def test_unconverted_data_is_not_relabelled_as_requested_unit(self):
        flow=TableFlow(self.source(),'汇总工作量。')
        result=deepcopy(flow.views['V0'])
        payload=delivery_review_payload('工作量用小时显示。','',{'docx':False},flow,result)
        self.assertEqual(payload['最终明细']['fields'][1]['unit'],'分钟')
        self.assertEqual(payload['最终字段的实际展示单位'],[{'column':'工作量（分钟）','unit':'分钟'}])
        self.assertEqual(payload['后续交付']['Word'],'用户未要求')
    def test_mass_display_does_not_change_base_arithmetic(self):
        flow=TableFlow({'columns':['重量（g）'],'rows':[['1250']],'provenance':[[0]],'notes':[]},'重量用kg显示。')
        result=flow.finish({'result':'V0'},{'deliver':'detail'})
        payload=delivery_review_payload(flow.current_goal,'',{},flow,result)
        self.assertEqual(payload['最终明细']['fields'][0]['unit'],'kg')
        self.assertEqual(result['rows'],[['1.25']]);self.assertEqual(flow.views['V0']['rows'],[['1250']])


class ReviewPhaseTests(unittest.TestCase):
    def test_atomic_word_requirement_is_scheduled_not_delivered(self):
        for requirement in ['再写一段不超过180字的概述并导出Word','生成Word，标题“办公说明”，不新增审核意见']:
            contract={'docx':True,'requirements':[requirement]}
            result=deferred_artifact_review({'state':'missing','next':'write_docx','requirement_index':0},contract)
            self.assertEqual(result['state'],'scheduled');self.assertNotIn('deferred_artifact_requirements',contract)
    def test_mixed_data_requirement_cannot_be_deferred(self):
        for requirement in ['按部门统计后导出Word','生成按部门统计的Word','筛选不少于500元的记录并生成Word']:
            self.assertIsNone(deferred_artifact_review({'state':'missing','next':'write_docx','requirement_index':0},{'docx':True,'requirements':[requirement]}))
    def test_unscheduled_or_non_atomic_request_still_requires_review(self):
        contract={'docx':True,'requirements':['导出Word']}
        for review in [{'state':'missing','next':'先计算总额然后write_docx','requirement_index':0},
                       {'state':'missing','next':'write_docx','requirement_index':True},
                       {'state':'missing','next':'write_docx','requirement_index':3},
                       {'state':'passed','next':'write_docx','requirement_index':0}]:
            self.assertIsNone(deferred_artifact_review(review,contract))
        self.assertIsNone(deferred_artifact_review({'state':'missing','next':'write_docx','requirement_index':0},{'docx':False,'requirements':['导出Word']}))


if __name__=='__main__':unittest.main()
