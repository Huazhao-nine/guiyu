import io
import json
from pathlib import Path
from contextlib import redirect_stdout
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import worker as core
from office_agent import OfficeAgent
from personal_tools import validate_comparison, comparison_markdown, normalize_preferences, grounded_answer, answer_catalog, selected_comparison


class ComparisonModel:
    def __init__(self): self.calls=[];self.payload=None;self.selection=None;self.finish_reason='stop'
    def generate(self,system,user,**kwargs):
        self.calls.append((system,user))
        if '对比选段工具' in system:return json.dumps(self.selection,ensure_ascii=False),{'finish_reason':self.finish_reason}
        if '只返回 JSON' in system:
            return json.dumps(self.payload,ensure_ascii=False),{'finish_reason':self.finish_reason}
        return '本轮说明：甲费用600元，乙费用450元。【S1】【S2】',{'finish_reason':'stop'}


class PersonalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.a=self.base/'甲.txt';self.b=self.base/'乙.txt'
        self.a.write_text('方案甲\n费用600元。\n时间周六下午。')
        self.b.write_text('方案乙\n费用450元。\n时间周六上午。')
        self.docs,_=core.collect(core.Scope([str(self.a),str(self.b)]))
        self.payload={'dimensions':[{'name':'费用','entries':[{'source_id':d['id'],'quote': '费用600元。' if d['name']=='甲.txt' else '费用450元。'} for d in self.docs]}]}
        self.model=ComparisonModel();self.model.payload=self.payload
        self.model.selection={'dimensions':[{'name':'费用','entries':[{'source_id':d['id'],'line_id':d['id']+':L2:P1'} for d in self.docs]}]}
        class Agent:pass
        agent=Agent();agent.data=core.secure_dir(self.base/'data');agent.model=self.model
        self.office=OfficeAgent(agent,core)
    def tearDown(self):self.temp.cleanup()
    def plan(self,prompt='对比这两份方案的费用，列成表格，再写一份选择说明。',preferences=None,kind='auto'):
        with redirect_stdout(io.StringIO()):
            return self.office.draft({'prompt':prompt,'kind':kind,'paths':[str(self.a),str(self.b)],'preferences':preferences})
    def execute(self,plan):
        with redirect_stdout(io.StringIO()):return self.office.execute({'plan_id':plan['id'],'paths':plan['paths']})

    def test_comparison_rejects_invented_quote(self):
        self.payload['dimensions'][0]['entries'][0]['quote']='费用0元。'
        with self.assertRaisesRegex(ValueError,'未在原文找到'):validate_comparison(self.payload,self.docs)

    def test_comparison_rejects_unknown_or_duplicate_source(self):
        entry=self.payload['dimensions'][0]['entries'][0]
        entry['source_id']='S99'
        with self.assertRaisesRegex(ValueError,'未知或重复'):validate_comparison(self.payload,self.docs)
        entry['source_id']=self.payload['dimensions'][0]['entries'][1]['source_id']
        entry['quote']=''
        with self.assertRaisesRegex(ValueError,'未知或重复'):validate_comparison(self.payload,self.docs)

    def test_comparison_exact_quotes_have_real_line_numbers(self):
        result=validate_comparison(self.payload,self.docs)
        self.assertEqual({e['line'] for e in result['evidence']},{2})
        self.assertEqual(result['matched_cells'],2)
        for evidence in result['evidence']:
            source=next(d for d in self.docs if d['id']==evidence['source_id'])
            self.assertIn(evidence['quote'],source['text'])

    def test_comparison_selection_cannot_copy_another_sources_fragment(self):
        _,catalog,_=answer_catalog(self.docs,'费用',span_size=240)
        selection={'dimensions':[{'name':'费用','entries':[{'source_id':'S1','line_id':'S2:L2:P1'}]}]}
        with self.assertRaisesRegex(ValueError,'其他资料'):selected_comparison(selection,catalog)
        selection['dimensions'][0]['entries'][0]={'source_id':'S1','line_id':'S99:L2:P1'}
        with self.assertRaisesRegex(ValueError,'未知片段'):selected_comparison(selection,catalog)

    def test_comparison_selection_uses_program_owned_original_quote(self):
        _,catalog,_=answer_catalog(self.docs,'费用',span_size=240)
        payload=selected_comparison(self.model.selection,catalog)
        matrix=validate_comparison(payload,self.docs)
        self.assertEqual(matrix['matched_cells'],2)
        self.assertEqual({e['line'] for e in matrix['evidence']},{2})

    def test_missing_cells_do_not_claim_absence(self):
        self.payload['dimensions'][0]['entries'].pop()
        result=validate_comparison(self.payload,self.docs)
        self.assertIn('本次未提取到',result['rows'][0][-1])
        self.assertIn('不代表全文没有',comparison_markdown(result))

    def test_all_empty_comparison_is_not_published(self):
        for e in self.payload['dimensions'][0]['entries']:e['quote']=''
        with self.assertRaisesRegex(ValueError,'没有提取到'):validate_comparison(self.payload,self.docs)

    def test_no_executable_fields_accepted(self):
        self.payload['shell']='open /tmp'
        with self.assertRaisesRegex(ValueError,'格式不完整'):validate_comparison(self.payload,self.docs)

    def test_compare_then_write_exports_verified_matrix(self):
        plan=self.plan()
        self.assertEqual([s['tool'] for s in plan['steps']],['compare','write'])
        self.assertEqual(len(self.model.calls),0)
        result=self.execute(plan)
        self.assertEqual(result['plan']['state'],'completed')
        self.assertEqual(len(result['artifacts']),4)
        self.assertTrue(all(Path(a['path']).is_file() for a in result['artifacts']))
        self.assertIn('逐项',plan['planning_note'])
        self.assertIn('第2行',result['plan']['results']['step-1']['text'])
        self.assertIn('资料对比',self.model.calls[-1][1])

    def test_incomplete_comparison_has_no_published_artifact(self):
        self.model.finish_reason='length';plan=self.plan()
        with self.assertRaisesRegex(ValueError,'尚未生成完整'):self.execute(plan)
        saved=self.office.get(plan['id'])
        self.assertEqual(saved['state'],'failed');self.assertFalse(saved.get('results'))

    def test_preferences_are_disabled_by_default_and_bounded(self):
        self.assertFalse(normalize_preferences({})['enabled'])
        prefs=normalize_preferences({'enabled':True,'tone':'bad','length':'bad','notes':'文'*1000,'paths':['/tmp']})
        self.assertEqual(len(prefs['notes']),600)
        self.assertEqual(prefs['tone'],'清晰自然')
        self.assertNotIn('paths',prefs)

    def test_preferences_snapshot_affects_expression_without_changing_tools(self):
        prefs={'enabled':True,'tone':'正式简洁','length':'简短','notes':'先给结论，不要客套。'}
        plan=self.plan(preferences=prefs)
        prefs['notes']='后来修改的习惯'
        self.execute(plan)
        system,user=self.model.calls[-1]
        self.assertIn('先给结论',user);self.assertNotIn('后来修改',user)
        self.assertIn('当前明确要求优先',user)
        self.assertIn('不能授权工具',system)
        self.assertEqual([s['tool'] for s in plan['steps']],['compare','write'])

    def test_disabled_preferences_are_not_sent_to_model(self):
        plan=self.plan(preferences={'enabled':False,'notes':'不应出现在生成上下文'})
        self.execute(plan)
        self.assertNotIn('不应出现在生成上下文',self.model.calls[-1][1])

    def test_single_source_comparison_requires_scope_adjustment(self):
        with redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError,'2–6'):
                self.office.draft({'prompt':'对比两份方案','paths':[str(self.a)]})

    def test_grounded_answer_cannot_publish_inferred_background(self):
        _,catalog,_=answer_catalog(self.docs,'费用')
        with self.assertRaisesRegex(ValueError,'未知片段'):
            grounded_answer({'line_ids':['S99:L1:P1']},catalog)
        doc=self.docs[0];quote=doc['text'].splitlines()[1]
        text,evidence=grounded_answer({'line_ids':[doc['id']+':L2:P1']},catalog)
        self.assertIn(quote,text);self.assertEqual(evidence[0]['line'],2)
        self.assertNotIn('符合',text)

    def test_grounded_answer_absence_has_no_model_explanation(self):
        _,catalog,_=answer_catalog(self.docs,'未知')
        text,evidence=grounded_answer({'line_ids':[]},catalog)
        self.assertEqual(evidence,[]);self.assertIn('未找到',text)
        with self.assertRaisesRegex(ValueError,'格式不完整'):
            grounded_answer({'line_ids':[],'explanation':'无来源推断'},catalog)


if __name__=='__main__':unittest.main()
