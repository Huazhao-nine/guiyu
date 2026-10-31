"""Generation shape constraints, Unicode prefixes and office parameter forms."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from structured_output import JSONGrammar, JSONLogitsProcessor, StructureError
from workbook_schema import obj, text, enum, action_schema,selection_schema
from workbook_flow import TableFlow


class StructuredOutputTests(unittest.TestCase):
    def test_nested_json_and_prefixes_reject_mixed_or_unknown_parameters(self):
        schema=obj({'tool':{'const':'filter'},'where':obj({'field':enum(['F1','F2']),'op':enum(['eq','gte']),'value':{'oneOf':[text(),{'type':'number'}]}})})
        grammar=JSONGrammar(schema)
        sample=json.dumps({'tool':'filter','where':{'field':'F1','op':'gte','value':12}},ensure_ascii=False)
        self.assertTrue(grammar.status(sample)[1])
        self.assertTrue(all(grammar.status(sample[:i])[0] for i in range(len(sample)+1)))
        for invalid in (sample.replace('F1','F3'),sample.replace('12','null'),sample[:-1]+',"fields":[]}',sample+' explanation'):
            self.assertFalse(grammar.status(invalid)[0],invalid)

    def test_recursive_conditions_and_expression_trees_are_canonical(self):
        flow=TableFlow({'columns':['金额（元）','状态'],'rows':[['12','启用']],'provenance':[[0]],'notes':[]},'金额不少于10元。')
        grammar=JSONGrammar(action_schema(flow))
        actions=[{'tool':'filter','input':'V0','where':{'all':[{'field':'F1','op':'gte','value':'10元'},{'not':{'field':'F2','op':'eq','value':'取消'}}]}},
                 {'tool':'derive','input':'V0','name':'两倍金额','formula':{'multiply':[{'column':'F1'},{'constant':'1'}]},'format':'number'},
                 {'tool':'present','input':'V0','units':[{'field':'F1','unit':'万元'}]},
                 {'tool':'finish','result':'V0','summaries':[],'fields':['F1']}]
        for action in actions:
            with self.subTest(action=action):self.assertTrue(grammar.status(json.dumps(action,ensure_ascii=False))[1])
        invalid=[{'tool':'derive','input':'V0','name':'副本','formula':'[F1]','fields':[]},
                 {'tool':'filter','input':'V9','where':{'field':'F1','op':'eq','value':1}},
                 {'tool':'filter','input':'V0','where':{'all':[]}},
                 {'tool':'present','input':'V0','units':[{'field':'F2','unit':'万元'}]},
                 {'tool':'derive','input':'V0','name':'新列','formula':{'column':'F2'}}]
        for action in invalid:
            with self.subTest(action=action):self.assertFalse(grammar.status(json.dumps(action,ensure_ascii=False))[0])

    def test_new_labels_cannot_be_confused_with_allocated_field_ids(self):
        flow=TableFlow({'columns':['Amount'],'rows':[['2']],'provenance':[[0]],'notes':[]},'计算一倍金额。')
        grammar=JSONGrammar(action_schema(flow))
        action={'tool':'derive','input':'V0','name':'差额','formula':{'column':'F1'},'format':'number'}
        text=json.dumps(action,ensure_ascii=False)
        self.assertTrue(all(grammar.status(text[:i])[0] for i in range(len(text)+1)))
        for name in ('F1','F2','F8',''):
            self.assertFalse(grammar.status(json.dumps(dict(action,name=name),ensure_ascii=False))[0])
        self.assertFalse(grammar.status(json.dumps({k:v for k,v in action.items() if k!='format'},ensure_ascii=False))[0])

    def test_ranked_choice_keeps_highest_legal_token_and_eos_only_at_completion(self):
        class Tokenizer:
            eos_token_id=9
            all_special_ids=[9,8]
            pieces={0:'{',1:'"x":',2:'true',3:'false',4:'}',5:'undefined',8:'',9:'<eos>'}
            def decode(self,ids):return ''.join(self.pieces[i] for i in ids)
        processor=JSONLogitsProcessor(Tokenizer(),obj({'x':{'type':'boolean'}}),0)
        self.assertEqual(processor.choose([0,1],[9,5,8,3,2]),3)
        self.assertEqual(processor.choose([0,1,3],[2,4]),4)
        self.assertEqual(processor.choose([0,1,3,4],[2,9]),9)

    def test_each_selected_view_has_its_own_field_choices(self):
        flow=TableFlow({'columns':['类别','金额（元）','日期'],'rows':[['甲','12','2027-01-01']],'provenance':[[0]],'notes':[]},'按类别汇总金额。')
        flow.apply({'tool':'group','by':['F1'],'metrics':[{'function':'sum','field':'F2','name':'合计'}]})
        grammar=JSONGrammar(action_schema(flow))
        leaf={'field':'F3','op':'gte','value':'2027-01-01'}
        self.assertFalse(grammar.status(json.dumps({'tool':'filter','input':'V1','where':leaf}))[0])
        self.assertTrue(grammar.status(json.dumps({'tool':'filter','input':'V0','where':leaf}))[1])

    def test_finish_forms_respect_detail_and_global_summary_roles(self):
        flow=TableFlow({'columns':['部门','金额（元）'],'rows':[['甲','12']],'provenance':[[0]],'notes':[]},'保留明细，另外给这批金额合计和条数。')
        contract={'deliver':'both','preserve_detail':True,'global_summary':True}
        self.assertFalse(JSONGrammar(action_schema(flow,contract)).status(json.dumps({'tool':'finish','result':'V0','summaries':[]}))[0])
        flow.apply({'tool':'group','by':['部门'],'metrics':[{'function':'sum','field':'金额','name':'合计'}]})
        self.assertIsNone(flow.delivery_candidate(contract,flow.goal))
        self.assertIn('by:[]',flow.pending_delivery_error)
        flow.apply({'tool':'group','input':'V0','by':[],'metrics':[{'function':'sum','field':'金额','name':'合计'},{'function':'count','name':'条数'}]})
        grammar=JSONGrammar(action_schema(flow,contract))
        self.assertTrue(grammar.status(json.dumps({'tool':'finish','result':'V0','summaries':['V2']}))[1])
        self.assertFalse(grammar.status(json.dumps({'tool':'finish','result':'V2','summaries':['V1']}))[0])
        self.assertFalse(grammar.status(json.dumps({'tool':'finish','result':'V0','summaries':['V0']}))[0])

    def test_selection_only_uses_real_contiguous_header_rows(self):
        grammar=JSONGrammar(selection_schema([{'id':'T1','row_count':5}]))
        def choice(rows,id='T1'):return json.dumps({'tables':[{'id':id,'header_rows':rows,'exclude_summary':True}]})
        self.assertTrue(grammar.status(choice([2,3]))[1])
        for rows in ([0],[6],[1,3],[1,2,3,4]):self.assertFalse(grammar.status(choice(rows))[0])
        self.assertFalse(grammar.status(choice([1],id='T2'))[0])

    def test_partial_utf8_in_free_text_can_finish_without_replacement(self):
        class Tokenizer:
            eos_token_id=9
            pieces={0:b'{"x":"',1:b'\xe9',2:b'\x95',3:b'\xbf',4:b'"}',9:b'<eos>'}
            def decode(self,ids):return b''.join(self.pieces[i] for i in ids).decode('utf8',errors='replace')
        p=JSONLogitsProcessor(Tokenizer(),obj({'x':text()}),0)
        self.assertEqual(p.choose([0],[1]),1)
        self.assertEqual(p.choose([0,1],[2]),2)
        self.assertEqual(p.choose([0,1,2],[3]),3)
        self.assertEqual(p.choose([0,1,2,3],[4]),4)

    def test_invalid_schema_fails_closed(self):
        for schema in ({'type':'python'},obj({'x':text()},optional=['x']),{'$ref':'#/$defs/absent'},
                       {'type':'string','not':{'pattern':'F[0-9]'}}):
            with self.assertRaises(StructureError):JSONGrammar(schema)


if __name__=='__main__':unittest.main()
