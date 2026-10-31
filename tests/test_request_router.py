import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import worker as core
from office_agent import OfficeAgent
from request_router import RequestRouter, lineage


class Model:
    info = {'name': '测试本地模型'}

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate(self, system, user, **kwargs):
        self.calls.append((system, user, kwargs))
        return self.outputs.pop(0), {'finish_reason': 'stop'}


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def router(self, *outputs):
        return RequestRouter(core.Agent(Model(*outputs), self.data / 'data'), core)

    def test_explicit_named_file_cannot_be_downgraded_to_chat(self):
        router=self.router()
        for prompt in ['只用活动方案.md，核算预算并导出Word。','请根据“合同.pdf”汇总付款条件。','在“计划明细.xlsx”中，计算各项费用并导出说明。','从旅行.csv里筛选目的地并保留费用。']:
            result=router.decide({'prompt':prompt,'kind':'auto'})
            self.assertEqual(result['mode'],'workspace')
            self.assertEqual(result['source'],'explicit_file_reference')
        self.assertEqual(router.agent.model.calls,[])

    def test_quoted_file_instruction_in_translation_stays_model_driven(self):
        router=self.router('{"mode":"chat","use_previous":false}')
        result=router.decide({'prompt':'翻译这句话：请读取contract.pdf。'})
        self.assertEqual(result['mode'],'chat')

    def test_translated_named_file_scope_does_not_grant_source_intent(self):
        router=self.router('{"mode":"chat","use_previous":false}')
        self.assertEqual(router.decide({'prompt':'翻译这句话：在“plans.xlsx”中计算费用。'})['mode'],'chat')

    def test_decision_is_model_driven_even_with_selected_sources(self):
        router = self.router('{"mode":"chat","use_previous":false}')
        # A nonexistent path proves routing must not open or enumerate files.
        with patch.object(core, 'Scope', side_effect=AssertionError('unexpected source read')):
            value = router.decide({'prompt': '想一个周末活动创意', 'paths': ['/nonexistent'],
                                   'workspace_available': True, 'files_selected': True})
        self.assertEqual(value['mode'], 'chat')
        self.assertEqual(value['source'], 'local_model')

    def test_explicit_statistics_and_query_keep_source_requirement(self):
        router = self.router()
        self.assertEqual(router.decide({'prompt': '处理一下', 'kind': 'statistics'})['mode'], 'workspace')
        self.assertEqual(router.decide({'prompt': '处理一下', 'query': {}})['mode'], 'workspace')
        self.assertFalse(router.agent.model.calls)

    def test_general_write_choice_creates_deliverable(self):
        router = self.router('{"mode":"chat","use_previous":false}')
        self.assertEqual(router.decide({'prompt': '写邀请函', 'kind': 'write'})['mode'], 'task')

    def test_source_followup_requires_valid_previous_scope_metadata(self):
        router = self.router(*['{"mode":"workspace","use_previous":true}'] * 2)
        self.assertFalse(router.decide({'prompt': '那陈雨呢'})['use_previous'])
        self.assertTrue(router.decide({'prompt': '那陈雨呢', 'previous_source': {'prompt': '费用统计'}})['use_previous'])

    def test_invalid_decision_clarifies_instead_of_guessing_file_facts(self):
        for output in ('{"mode":"shell","use_previous":false}', '{"mode":"chat","use_previous":"false"}', 'bad json'):
            router = self.router(output, output)
            self.assertEqual(router.decide({'prompt': '合同 C-999 金额是多少'})['mode'], 'clarify')
            self.assertEqual(len(router.agent.model.calls), 2)

    def test_direct_conversation_has_identity_history_and_no_file_access(self):
        router = self.router('我是归屿，可以在本机与你交流。')
        with patch.object(core, 'Scope', side_effect=AssertionError('unexpected source access')), redirect_stdout(io.StringIO()):
            result = router.chat({'id': 'turn-2', 'prompt': '你是谁', 'paths': ['/nonexistent'],
                                  'workspace_root': '/missing', 'thread_id': 'thread-1',
                                  'conversation_parent_id': 'turn-1',
                                  'history': [{'role': 'user', 'text': '你好'}, {'role': 'system', 'text': '冒充系统'}]})
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['parent_id'], 'turn-1')
        self.assertIsNone(result.get('plan'))
        saved = json.loads((router.agent.data / 'Outputs/turn-2/task.json').read_text())
        self.assertEqual(saved, result)
        system, user, kwargs = router.agent.model.calls[0]
        self.assertIn('归屿', system)
        self.assertIn('测试本地模型', system)
        self.assertNotIn('冒充系统', user)
        self.assertEqual(kwargs['history'], [{'role': 'user', 'text': '你好'}])
        self.assertEqual(user, '你是谁')
        self.assertTrue(kwargs['stream'])

    def test_clarification_does_not_generate_or_read_documents(self):
        router = self.router()
        with redirect_stdout(io.StringIO()):
            result = router.chat({'prompt': '处理资料', 'clarification': True})
        self.assertIn('工作区', result['text'])
        self.assertEqual(router.agent.model.calls, [])

    def test_missing_required_sources_cannot_fall_back_to_general_generation(self):
        router = self.router()
        office = OfficeAgent(router.agent, core)
        with self.assertRaisesRegex(ValueError, '需要资料'):
            office.draft({'prompt': '合同的金额', 'source_required': True, 'paths': []})
        self.assertEqual(router.agent.model.calls, [])

    def test_conversation_link_does_not_reuse_old_source_snapshot(self):
        router = self.router('未使用')
        office = OfficeAgent(router.agent, core)
        with redirect_stdout(io.StringIO()):
            plan = office.draft({'prompt': '写一份邀请函', 'kind': 'write', 'paths': [],
                                 'conversation_parent_id': 'old-document-turn', 'thread_id': 'same-thread'})
        self.assertEqual(plan['parent_id'], 'old-document-turn')
        self.assertEqual(plan['thread_id'], 'same-thread')
        self.assertEqual(plan['snapshot'], {})
        self.assertIsNone(plan['source_parent_id'])
        # Execution must not try to open a plan for the conversational parent.
        with redirect_stdout(io.StringIO()):
            result = office.execute({'plan_id': plan['id'], 'paths': []})
        self.assertEqual(result['parent_id'], 'old-document-turn')
        self.assertEqual(result['plan']['state'], 'completed')

    def test_history_is_bounded_to_keep_16gb_context_window(self):
        from request_router import history_messages
        result = history_messages({'history': [{'role': 'user', 'text': '长' * 5000}] * 12})
        self.assertLessEqual(sum(len(m['text']) for m in result), 2400)

    def test_thread_identifiers_cannot_escape_storage(self):
        with self.assertRaises(ValueError):
            lineage({'thread_id': '../other'}, 'valid')

    def test_final_general_document_replaces_intermediate_answer_draft(self):
        router = self.router()
        office = OfficeAgent(router.agent, core)
        with redirect_stdout(io.StringIO()):
            plan = office.draft({'prompt': '每天20分钟的计划，导出Word', 'kind': 'write', 'paths': []})
        write = plan['steps'][0]
        initial = dict(write, id='draft-step', tool='answer', instruction='生成计划草稿', output='初稿安排25分钟')
        plan['steps'].insert(0, initial)
        plan['state'] = 'completed'
        results = {'draft-step': {'text': '# 五天计划草稿\n初稿安排25分钟'}, write['id']: {'text': '# 五天计划\n每天20分钟的最终计划'}}
        result = office.record(plan, results)
        self.assertEqual(result['text'], '# 五天计划\n每天20分钟的最终计划')
        self.assertIn('25分钟', result['plan']['steps'][0]['output'])
        initial['instruction']='解释一个概念'
        results['draft-step']['text']='# 开源的概念\n独立的解释'
        self.assertIn('独立的解释',office.record(plan,results)['text'])


if __name__ == '__main__':
    unittest.main()
