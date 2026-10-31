"""Literal two-column comparison repair, without business-specific labels."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from table_program import TableError
from workbook_flow import TableFlow
from workbook_intent import compile_column_comparisons


def table(columns,rows):
    return {'columns':columns,'rows':rows,'provenance':[[i] for i in range(len(rows))],'notes':[]}


class LiteralColumnComparisonTests(unittest.TestCase):
    def test_suffix_binding_repairs_direction_and_preserves_other_conditions_and_formulas(self):
        source=table(['物料','现有库存','安全库存','单价','状态'],[
            ['甲','3','8','5','有效'],['乙','10','8','2','有效'],['丙','1','8','3','停用'],['丁','8','8','4','有效']])
        before=deepcopy(source)
        flow=TableFlow(source,'从台账找出库存低于安全库存的物料。计算缺口=安全库存减现有库存，补货成本=缺口乘单价。')
        action={'tool':'filter','where':{'all':[{'field':'安全库存','op':'lt','other':'现有库存'},
                                                   {'field':'状态','op':'eq','value':'有效'}]}}
        event=flow.apply(action)
        self.assertEqual(flow.views[flow.last]['rows'],[source['rows'][0]])
        correction=event['intent_corrections'][0]
        self.assertEqual(correction['kind'],'literal_column_comparison')
        self.assertEqual(correction['before']['column'],'安全库存')
        self.assertEqual(correction['after'],{'column':'现有库存','operator':'lt','type':'number','value_column':'安全库存'})
        self.assertIn('库存低于安全库存',correction['quote'])
        self.assertEqual(flow.graph[-1]['intent_corrections'],event['intent_corrections'])
        self.assertEqual(flow.graph[-1]['operation']['where']['all'][1],{'column':'状态','operator':'eq','type':'text','value':'有效'})
        flow.apply({'tool':'derive','fields':[{'name':'缺口','formula':'[安全库存]-[现有库存]'},
                                               {'name':'补货成本','formula':'[缺口]*[单价]'}]})
        self.assertEqual(flow.views[flow.last]['rows'][0][-2:],['5','25'])
        self.assertEqual(source,before)

    def test_non_inventory_pairs_correct_direction_and_inclusive_boundaries(self):
        cases=[(['实际支出（元）','预算（万元）'],[['200','0.03'],['300','0.03'],['400','0.03']],
                '筛选支出不超过预算的记录。','预算（元）','lt','实际支出（元）',[0,1],'lte'),
               (['交付日期','约定日期'],[['2026-10-01','2026-10-02'],['2026-10-02','2026-10-02'],['2026-10-03','2026-10-02']],
                '保留交付日期早于约定日期的记录。','约定日期','lt','交付日期',[0],'lt'),
               (['实际温度','目标温度'],[['8','9'],['9','9'],['10','9']],
                '只看温度不低于目标温度的设备。','实际温度','lt','目标温度',[1,2],'gte')]
        for columns,rows,goal,left,operator,right,indices,expected in cases:
            with self.subTest(goal=goal):
                flow=TableFlow(table(columns,rows),goal)
                event=flow.apply({'tool':'filter','where':{'field':left,'op':operator,'other':right}})
                self.assertEqual(flow.views[flow.last]['provenance'],[[i] for i in indices])
                self.assertEqual(event['intent_corrections'][0]['after']['operator'],expected)

    def test_equivalent_reverse_comparison_needs_no_correction(self):
        source=table(['实际支出','预算'],[['3','5'],['5','5'],['6','5']])
        flow=TableFlow(source,'找出实际支出低于预算的记录。')
        event=flow.apply({'tool':'filter','where':{'field':'预算','op':'gt','other':'实际支出'}})
        self.assertNotIn('intent_corrections',event)
        self.assertEqual(flow.views[flow.last]['rows'],[['3','5']])

    def test_two_and_comparisons_bind_independently(self):
        source=table(['实测值','上限','下限'],[['2','5','1'],['6','5','1'],['0','5','1']])
        flow=TableFlow(source,'找出实测值低于上限且实测值高于下限的记录。')
        event=flow.apply({'tool':'filter','where':{'all':[{'field':'上限','op':'lt','other':'实测值'},
                                                       {'field':'下限','op':'gt','other':'实测值'}]}})
        self.assertEqual(len(event['intent_corrections']),2)
        self.assertEqual(flow.views[flow.last]['rows'],[['2','5','1']])

    def test_exact_left_field_wins_over_suffix_aliases(self):
        source=table(['库存','现有库存','剩余库存','安全库存'],[['2','8','9','5'],['8','2','3','5']])
        flow=TableFlow(source,'找出库存低于安全库存的记录。')
        event=flow.apply({'tool':'filter','where':{'field':'安全库存','op':'lt','other':'库存'}})
        self.assertEqual(flow.views[flow.last]['rows'],[source['rows'][0]])
        self.assertEqual(event['intent_corrections'][0]['after']['column'],'库存')

    def test_ambiguous_suffix_modified_phrase_and_arithmetic_are_not_guessed(self):
        cases=[(['现有库存','剩余库存','安全库存'],'找出库存低于安全库存的记录。'),
               (['现有库存','安全库存'],'找出总库存低于安全库存的记录。'),
               (['可用库存','预留库存','安全库存'],'找出可用库存减预留库存低于安全库存的记录。'),
               (['现有库存','安全库存'],'找出安全库存高于库存的记录。')]
        for columns,goal in cases:
            with self.subTest(goal=goal):
                flow=TableFlow(table(columns,[['3']*len(columns)]),goal)
                node={'column':columns[0],'operator':'gt','type':'number','value_column':'安全库存'};before=deepcopy(node)
                self.assertEqual(compile_column_comparisons(node,goal,flow.views['V0']),[])
                self.assertEqual(node,before)

    def test_goal_or_negation_and_hypotheticals_never_become_implicit_and(self):
        source=table(['现有库存','安全库存'],[['3','5'],['8','5']]);view=TableFlow(source,'').views['V0']
        for goal in ('找出库存低于安全库存或者相同的记录。','找出库存低于安全库存，或者状态为紧急。',
                     '不要保留库存低于安全库存的记录。','排除库存低于安全库存的记录。',
                     '不保留库存低于安全库存的记录。','别保留库存低于安全库存的记录。',
                     '别再保留库存低于安全库存的记录。','不应当保留库存低于安全库存的记录。',
                     '未满足库存低于安全库存的记录。','避免筛选库存低于安全库存的记录。',
                     '不用保留库存低于安全库存的记录。','禁止保留库存低于安全库存的记录。',
                     '不允许再保留库存低于安全库存的记录。','找出安全库存大于现有库存且不允许保留库存低于安全库存的记录。',
                     '不保留库存低于安全库存且安全库存大于现有库存的记录。',
                     '如果库存低于安全库存，请只整理表头。'):
            node={'column':'安全库存','operator':'lt','type':'number','value_column':'现有库存'};before=deepcopy(node)
            with self.subTest(goal=goal):
                self.assertEqual(compile_column_comparisons(node,goal,view),[]);self.assertEqual(node,before)

    def test_any_not_and_different_field_pairs_are_not_rewritten(self):
        source=table(['实际支出','预算','预估支出'],[['3','5','8']]);view=TableFlow(source,'').views['V0']
        leaf={'column':'预算','operator':'lt','type':'number','value_column':'实际支出'}
        for node in ({'any':[deepcopy(leaf)]},{'not':deepcopy(leaf)},
                     {'column':'预算','operator':'lt','type':'number','value_column':'预估支出'}):
            before=deepcopy(node)
            self.assertEqual(compile_column_comparisons(node,'找出实际支出低于预算的记录。',view),[])
            self.assertEqual(node,before)

    def test_incompatible_units_including_a_missing_dimension_are_rejected(self):
        for columns,values in ((['实际支出（元）','预算（USD）'],['3','5']),
                               (['实际时长（分钟）','预算（元）'],['3','5']),
                               (['实际支出（元）','预算'],['3','5'])):
            with self.subTest(columns=columns):
                flow=TableFlow(table(columns,[values]),'找出支出低于预算的记录。')
                with self.assertRaisesRegex(TableError,'维度不同|维度不一致'):
                    flow.apply({'tool':'filter','where':{'field':columns[0],'op':'gt','other':columns[1]}})
                self.assertEqual(flow.graph,[])
                flow.current_goal='只整理一份表格。'
                with self.assertRaisesRegex(TableError,'维度不同'):
                    flow.apply({'tool':'filter','where':{'any':[{'field':columns[0],'op':'lt','other':columns[1]}]}})
                self.assertEqual(flow.graph,[])

    def test_multiple_inconsistent_claims_are_left_to_semantic_planning(self):
        view=TableFlow(table(['实测值','阈值'],[['3','5']]),'').views['V0']
        node={'column':'实测值','operator':'eq','type':'number','value_column':'阈值'};before=deepcopy(node)
        self.assertEqual(compile_column_comparisons(node,'找出实测值低于阈值且实测值高于阈值的记录。',view),[])
        self.assertEqual(node,before)


if __name__=='__main__':unittest.main()
