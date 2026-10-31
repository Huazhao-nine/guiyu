"""Calendar-month boundaries and explicit continuity use facts, not model size."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from table_program import TableError
from workbook_intent import literal_calendar_requirements,retains_delivery,compile_calendar_month_bounds,check_literal_inclusions
from workbook_flow import TableFlow,freeze_finish,fingerprint
from workbook_revision import retained_scope_flow,covered_request


class MonthBoundsTests(unittest.TestCase):
    def view(self,two=False):
        return {'columns':['登记日','结束日'] if two else ['登记日'],
                'field_types':{'登记日':'date',**({'结束日':'date'} if two else {})},'rows':[]}
    def test_full_month_uses_actual_leap_and_year_boundaries(self):
        for phrase,last in [('2028年2月整月','2028-02-29'),('2027年2月全月','2027-02-28'),('2027年12月整个月','2027-12-31')]:
            with self.subTest(phrase=phrase):
                rules=literal_calendar_requirements('只看'+phrase+'的记录。',self.view())
                self.assertEqual([r['value'] for r in rules],[last[:8]+'01',last])
                self.assertEqual([r['operator'] for r in rules],['gte','lte'])
    def test_ambiguous_date_fields_are_not_guessed(self):
        self.assertEqual(literal_calendar_requirements('只看2027年11月整月。',self.view(True)),[])
        rules=literal_calendar_requirements('结束日在2027年11月整月。',self.view(True))
        self.assertEqual({r['column'] for r in rules},{'结束日'})
    def test_negative_examples_or_alternative_months_are_not_positive_filters(self):
        for goal in ['排除2027年7月整月。','比如2027年7月整月。','2027年7月整月或2027年8月整月。','2027年7月整月，不含月初。']:
            with self.subTest(goal=goal):self.assertEqual(literal_calendar_requirements(goal,self.view()),[])
    def test_missing_year_is_not_filled_from_current_clock(self):
        self.assertEqual(literal_calendar_requirements('只看7月整月。',self.view()),[])
        with self.assertRaises(TableError):literal_calendar_requirements('只看2027年13月整月。',self.view())
    def test_aggregate_with_outside_origins_is_blocked_before_export(self):
        source={'columns':['编号','登记日','部门','金额（元）'],
                'rows':[['A','2027-06-30','甲','800'],['B','2027-07-01','甲','200'],['C','2027-08-01','甲','900']],
                'provenance':[[0],[1],[2]],'notes':[]}
        flow=TableFlow(source,'只纳入2027年7月整月，按部门汇总金额。')
        flow.apply({'tool':'group','by':['部门'],'metrics':[{'function':'sum','field':'金额（元）','name':'合计'}]})
        with self.assertRaises(TableError) as raised:flow.finish({'result':flow.last},{'deliver':'aggregate'})
        self.assertEqual(raised.exception.repair_predicate['type'],'date')
        self.assertIn(raised.exception.repair_predicate['value'],['2027-07-01','2027-07-31'])

    def test_month_endpoint_correction_preserves_nested_business_branches(self):
        source={'columns':['登记日','结束日','类型'],
                'rows':[['2024-01-01','2024-02-28','甲'],['2024-01-02','2024-02-29','乙'],['2024-01-03','2024-03-01','甲']],
                'provenance':[[0],[1],[2]],'notes':[]}
        flow=TableFlow(source,'结束日在2024年2月整月，类型为甲或者乙。')
        event=flow.apply({'tool':'filter','where':{'all':[
            {'field':'结束日','op':'gte','value':'2024-02-01'},
            {'field':'结束日','op':'lte','value':'2024-02-28'},
            {'any':[{'field':'类型','op':'eq','value':'甲'},{'field':'类型','op':'eq','value':'乙'}]}]}})
        self.assertEqual(len(flow.views[flow.last]['rows']),2)
        self.assertEqual(flow.graph[-1]['operation']['where']['all'][1]['value'],'2024-02-29')
        self.assertEqual(event['intent_corrections'][0]['kind'],'calendar_month_endpoint')

    def test_exclusive_equivalents_and_explicit_extra_restrictions_are_preserved(self):
        view=self.view()
        for goal,node in [
            ('登记日在2024年2月整月。',{'column':'登记日','operator':'lt','type':'date','value':'2024-03-01'}),
            ('登记日在2024年2月整月，并且晚于2024-02-15。',{'column':'登记日','operator':'gt','type':'date','value':'2024-02-15'}),
            ('登记日在2024年2月整月。',{'any':[{'column':'登记日','operator':'lte','type':'date','value':'2024-02-28'}]})]:
            with self.subTest(goal=goal,node=node):
                before=deepcopy(node);self.assertEqual(compile_calendar_month_bounds(node,goal,view),[]);self.assertEqual(before,node)

    def test_calendar_context_is_bound_to_real_field(self):
        source={'columns':['RecordedAt'],'rows':[['2032-02-29']],'provenance':[[0]],'notes':[]}
        context=TableFlow(source,'只要2032年2月整月的记录。').context()
        self.assertEqual(context['explicit_calendar_bounds'][-1]['value'],'2032-02-29')


class ContinuityTests(unittest.TestCase):
    def test_explicit_processing_scope_families_are_recognized(self):
        for phrase in ['其他业务规则不变','其它统计口径都保持不变','其余计算标准照旧','其他的处理规则均不变']:
            with self.subTest(phrase=phrase):self.assertTrue(retains_delivery('那乙组呢？'+phrase+'。'))
        self.assertFalse(retains_delivery('换一种统计口径。'))
        self.assertTrue(covered_request('把金额门槛改为800元，其他计算规则都保持不变。',['金额门槛改为800元']))
        self.assertTrue(covered_request('回到刚才的设备维护任务，把金额门槛改为800元，其他计算规则都保持不变。',['金额门槛改为800元']))
        self.assertFalse(covered_request('回到刚才的设备维护任务并改用别的工作簿，把金额门槛改为800元，其他计算规则都保持不变。',['金额门槛改为800元']))
    def retained(self,goal):
        source={'columns':['Ref','Group','Paid（元）','Stage'],
                'rows':[['A','甲组','150','已核准'],['B','乙组','300','已核准'],['C','甲组','9000','驳回'],['D','甲组','20','已核准']],
                'provenance':[[0],[1],[2],[3]],'notes':[]}
        original='只纳入Stage为已核准且Paid不少于100元，按Group统计总额。'
        flow=TableFlow(source,original)
        flow.apply({'tool':'filter','where':{'all':[{'field':'Stage','op':'eq','value':'已核准'},{'field':'Paid（元）','op':'gte','value':100}]}})
        flow.apply({'tool':'group','by':['Group'],'metrics':[{'function':'sum','field':'Paid（元）','name':'总额'}]})
        contract={'deliver':'aggregate','docx':False};finish=freeze_finish(flow,{'result':flow.last})
        result=flow.finish(deepcopy(finish),contract)
        parent={'id':'parent','workbook':{'mode':'flow','flow':{'graph':flow.graph,'finish':finish,'contract':contract,'expected':fingerprint(result)}}}
        return retained_scope_flow(source,goal,parent,result,original)
    def test_department_followup_starts_from_the_verified_scope(self):
        flow,note=self.retained('那甲组呢？其他统计口径不变，这次只要表格。')
        self.assertEqual([row[0] for row in flow.views[flow.last]['rows']],['A','B'])
        self.assertEqual(note['mode'],'subset')
        flow.apply({'tool':'filter','where':{'field':'Group','op':'eq','value':'甲组'}})
        self.assertEqual([row[0] for row in flow.views[flow.last]['rows']],['A'])
    def test_format_only_followup_cannot_drop_prior_records(self):
        flow,note=self.retained('其他业务规则不变，这次只要表格。')
        self.assertEqual(note['mode'],'equal');self.assertEqual(len(flow.views[flow.last]['rows']),2)

    def test_single_category_request_is_subset_and_checked_against_actual_values(self):
        flow,note=self.retained('把乙组单独列出来，其他业务规则不变，这次只要表格。')
        self.assertEqual(note['mode'],'subset')
        with self.assertRaises(TableError) as raised:
            check_literal_inclusions('把乙组单独展示，其他业务规则不变。',flow.views[flow.last])
        self.assertEqual(raised.exception.repair_predicate['value'],'乙组')
        for goal in ['不要把乙组单独列出来。','乙组单独列出来或保留甲组。','比如乙组单独查看。']:
            check_literal_inclusions(goal,flow.views[flow.last])

    def test_category_selection_cannot_be_omitted_by_grouping(self):
        flow,note=self.retained('把甲组单独列出来，其他处理规则不变，这次只要表格。')
        flow.apply({'tool':'group','by':['Group'],'metrics':[{'function':'sum','field':'Paid（元）','name':'总额'}]})
        with self.assertRaises(TableError) as raised:
            flow.finish({'result':flow.last},{'deliver':'aggregate'})
        self.assertEqual(raised.exception.repair_predicate['value'],'甲组')
        from workbook_revision import repair_delivery_filter
        fixed,finish=repair_delivery_filter(flow,{'result':flow.last},raised.exception.repair_predicate,'aggregate')
        result=fixed.finish(finish,{'deliver':'aggregate'})
        self.assertEqual(result['rows'],[['甲组','150']])


if __name__=='__main__':unittest.main()
