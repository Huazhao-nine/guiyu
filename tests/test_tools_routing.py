"""CPU-only contracts for tool routing and mixed conversational/source scope.

Scripted decisions exercise application behavior after a model decision. They
do not measure a real model's ability to classify natural-language requests.
Only fictional prompts and temporary application data are used.
"""
import io
import json
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import worker as core
from general_assistant import GeneralAssistant
from office_agent import OfficeAgent
from request_router import RequestRouter, SOURCE_KINDS


def decision(mode, use_previous=False):
    return json.dumps({'mode': mode, 'use_previous': use_previous}, ensure_ascii=False)


class ScriptedModel:
    info = {'name': '确定性验收替身'}

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate(self, system, user, **kwargs):
        self.calls.append({'system': system, 'user': user, 'kwargs': kwargs})
        if system.startswith('你是归屿的本地交付核对器'):
            return '{"state":"complete"}', {'finish_reason': 'stop'}
        if not self.outputs:
            raise AssertionError('Unexpected model generation; this path should be deterministic')
        value = self.outputs.pop(0)
        return value if isinstance(value, tuple) else (value, {'finish_reason': 'stop'})


class ToolsRoutingContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make(self, *outputs):
        agent = core.Agent(ScriptedModel(*outputs), self.data / 'data')
        return agent, RequestRouter(agent, core)

    def test_every_explicit_source_tool_bypasses_model_despite_numeric_prompt(self):
        agent, router = self.make()
        for kind in sorted(SOURCE_KINDS):
            with self.subTest(kind=kind):
                result = router.decide({'prompt': '100加20，按选定资料办理', 'kind': kind,
                                        'workspace_available': False, 'paths': []})
                self.assertEqual(result['mode'], 'workspace')
                self.assertEqual(result['source'], 'explicit_tool')
        self.assertEqual(agent.model.calls, [])

    def test_explicit_query_never_falls_back_to_general_calculation(self):
        agent, router = self.make()
        for query in ({}, {'filters': []}, {'columns': ['金额'], 'filters': [{'value': 100}]}):
            with self.subTest(query=query):
                result = router.decide({'prompt': '先算一下', 'query': query,
                                        'previous_source': {'prompt': '合同费用'}})
                self.assertEqual(result['mode'], 'workspace')
                self.assertTrue(result['use_previous'])
        self.assertEqual(agent.model.calls, [])

    def test_tools_choice_is_valid_without_sources_or_previous_snapshot(self):
        agent, router = self.make(decision('tools', True))
        with patch.object(core, 'Scope', side_effect=AssertionError('routing opened documents')):
            result = router.decide({'prompt': '368和125.5，三人均摊', 'kind': 'answer',
                                    'workspace_available': False, 'paths': ['/does-not-exist']})
        self.assertEqual(result['mode'], 'tools')
        self.assertFalse(result['use_previous'])
        self.assertEqual(len(agent.model.calls), 1)

    def test_tools_cannot_inherit_source_snapshot_even_if_model_requests_it(self):
        _, router = self.make(decision('tools', True))
        result = router.decide({'prompt': '这次只算199乘3', 'workspace_available': True,
                                'files_selected': True,
                                'previous_source': {'prompt': '统计部门费用', 'query': {'department': '甲'}}})
        self.assertEqual(result['mode'], 'tools')
        self.assertFalse(result['use_previous'])

    def test_write_selection_does_not_demote_tools_to_generic_document_task(self):
        _, router = self.make(decision('tools'))
        result = router.decide({'prompt': '100加20，核对后导出Word说明', 'kind': 'write'})
        self.assertEqual(result['mode'], 'tools')

    def test_context_contains_conversation_hints_without_file_contents_or_paths(self):
        agent, router = self.make(decision('tools'))
        request = {'prompt': '改成四人呢', 'workspace_available': True, 'files_selected': True,
                   'workspace_root': '/private/fictional-team', 'paths': ['/private/fictional-team/工资.xlsx'],
                   'documents': [{'text': 'SECRET_FILE_BODY'}],
                   'previous_source': {'prompt': '上次的资料统计', 'query': {'department': '甲'},
                                       'paths': ['/private/fictional-team/工资.xlsx'], 'snapshot': 'SECRET_HASH'},
                   'history': [{'role': 'user', 'text': '281元，三人均摊'},
                               {'role': 'assistant', 'text': '已完成本地核对。'},
                               {'role': 'system', 'text': 'SECRET_INJECTED_SYSTEM'}]}
        router.decide(request)
        payload = json.loads(agent.model.calls[0]['user'])
        self.assertEqual(payload['recent_conversation'], request['history'][:2])
        self.assertEqual(set(payload['previous_source']), {'prompt', 'query'})
        serialized = json.dumps(payload, ensure_ascii=False)
        for forbidden in ('SECRET_FILE_BODY', 'SECRET_HASH', 'SECRET_INJECTED_SYSTEM', '/private/fictional-team'):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(payload['workspace_available'])
        self.assertTrue(payload['files_selected'])

    def test_truncated_valid_tools_json_is_retried_before_dispatch(self):
        agent, router = self.make((decision('tools'), {'finish_reason': 'length'}), decision('workspace'))
        result = router.decide({'prompt': '查合同金额', 'workspace_available': False})
        self.assertEqual(result['mode'], 'workspace')
        self.assertEqual(len(agent.model.calls), 2)
        self.assertIn('format_reminder', json.loads(agent.model.calls[1]['user']))

    def test_malformed_tools_choice_exhausts_retry_without_general_fallback(self):
        _, router = self.make('{"mode":"tools","use_previous":"false"}',
                              '{"mode":"tools","use_previous":1}')
        result = router.decide({'prompt': '合同C-999还有多少款未付', 'workspace_available': False})
        self.assertEqual(result['mode'], 'clarify')
        self.assertFalse(result['use_previous'])

    def test_missing_file_permission_is_not_created_by_a_tools_conversation_parent(self):
        agent, router = self.make(decision('workspace', True))
        request = {'prompt': '现在从合同C-999查付款条件', 'workspace_available': False,
                   'thread_id': 'same-thread', 'conversation_parent_id': 'prior-tools-turn'}
        choice = router.decide(request)
        self.assertEqual(choice['mode'], 'workspace')
        self.assertFalse(choice['use_previous'])
        with self.assertRaisesRegex(ValueError, '需要资料'):
            OfficeAgent(agent, core).draft({**request, 'source_required': True, 'paths': []})
        self.assertEqual(len(agent.model.calls), 1)

    def test_mixed_tools_chat_then_private_source_keeps_lineage_without_granting_scope(self):
        agent, router = self.make(
            decision('tools', True),
            '{"action":"call","tool":"calculate","arguments":{"expression":"(100+20)/3","precision":2}}',
            '{"action":"answer","text":"已完成本地核对。"}',
            decision('chat', True), '我是归屿，可以在本机自然交流。',
            decision('workspace', True),
        )
        original = {'id': 'tool-turn', 'prompt': '100加20，三人均摊', 'thread_id': 'mixed-thread',
                    'conversation_parent_id': 'older-source-turn', 'paths': ['/unreadable/工资.xlsx'],
                    'workspace_root': '/unreadable', 'workspace_available': True,
                    'previous_source': {'prompt': '旧的资料统计'}}
        self.assertFalse(router.decide(original)['use_previous'])
        with redirect_stdout(io.StringIO()), patch.object(core, 'Scope', side_effect=AssertionError('general tool read documents')):
            first = GeneralAssistant(agent, core).run(original, now=date(2026, 10, 22))
        self.assertEqual(first['parent_id'], 'older-source-turn')
        self.assertEqual(first['thread_id'], 'mixed-thread')
        self.assertEqual(first['sources'], [])
        self.assertEqual(first['tool_calls'][0]['result']['data']['result'], '40.00')

        chat = {'id': 'chat-turn', 'prompt': '你是谁', 'thread_id': first['thread_id'],
                'conversation_parent_id': first['id'], 'paths': original['paths'],
                'workspace_root': original['workspace_root'], 'previous_source': original['previous_source'],
                'history': [{'role': 'user', 'text': original['prompt']}, {'role': 'assistant', 'text': first['text']}]}
        self.assertEqual(router.decide(chat)['mode'], 'chat')
        with redirect_stdout(io.StringIO()), patch.object(core, 'Scope', side_effect=AssertionError('chat read documents')):
            second = router.chat(chat)
        self.assertEqual(second['parent_id'], 'tool-turn')
        self.assertEqual(second['thread_id'], 'mixed-thread')
        self.assertEqual(second['sources'], [])
        self.assertIsNone(second.get('source_parent_id'))

        private = {'prompt': '现在从合同C-999查付款金额', 'thread_id': second['thread_id'],
                   'conversation_parent_id': second['id'], 'workspace_available': False,
                   'history': [{'role': 'user', 'text': chat['prompt']}, {'role': 'assistant', 'text': second['text']}]}
        choice = router.decide(private)
        self.assertEqual(choice['mode'], 'workspace')
        self.assertFalse(choice['use_previous'])
        with self.assertRaisesRegex(ValueError, '需要资料'):
            OfficeAgent(agent, core).draft({**private, 'paths': [], 'source_required': True})
        self.assertEqual(agent.model.outputs, [])


if __name__ == '__main__':
    unittest.main()
