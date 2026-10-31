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
from general_assistant import GeneralAssistant, clock_context, dates_in, percentage_request


def action(tool, arguments):
    return json.dumps({'action': 'call', 'tool': tool, 'arguments': arguments}, ensure_ascii=False)


class Model:
    info = {'name': '本地测试模型'}
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []
        self.reviews = []
    def generate(self, system, user, **kwargs):
        self.calls.append((system, user))
        if system.startswith('你是归屿的本地交付核对器'):
            value = self.reviews.pop(0) if self.reviews else '{"state":"complete"}'
            return value if isinstance(value,tuple) else (value, {'tokens':10,'seconds':.1})
        return self.outputs.pop(0) if self.outputs else '{"action":"ask","question":"请补充条件"}', {'tokens': 10, 'seconds': .1}


class GeneralAssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def run_assistant(self, prompt, outputs, **request):
        agent = core.Agent(Model(outputs), self.data)
        agent.model.reviews = request.pop('review_outputs',[])
        assistant = GeneralAssistant(agent, core)
        with redirect_stdout(io.StringIO()), patch.object(core, 'Scope', side_effect=AssertionError('Document scope accessed')):
            result = assistant.run({'prompt': prompt, **request}, now=date(2026, 10, 22))
        return result, assistant

    def test_money_result_and_trace_are_persisted_without_reading_documents(self):
        result, _ = self.run_assistant('午餐368元和交通125.5元，3人平摊，保留两位小数', [
            action('calculate', {'expression': '(368+125.5)/3', 'precision': 2}),
            '{"action":"answer","text":"每人164.50元。"}'], paths=['/missing'], workspace_root='/missing')
        self.assertEqual(result['tool_calls'][0]['result']['data']['result'], '164.50')
        self.assertEqual(result['sources'], [])
        self.assertEqual(json.loads((self.data/'Outputs'/result['id']/'task.json').read_text()), result)

    def test_truncated_review_is_repaired_without_repeating_correct_tool(self):
        result, assistant = self.run_assistant('2029年5月20日提前4天是哪天', [
            action('calendar', {'operation':'date_shift','date':'2029-05-20','days':-4}),
            '{"action":"answer","text":"已核对日期。"}'],
            review_outputs=[('{"state":"complete"}',{'finish_reason':'length','tokens':240,'seconds':.1}),
                            '{"state":"complete"}'])
        self.assertEqual(len(result['tool_calls']),1)
        self.assertEqual(result['completion_check']['state'],'passed')
        self.assertEqual([r['state'] for r in result['review_history']],['invalid','complete'])
        producers=[c for c in assistant.agent.model.calls if not c[0].startswith('你是归屿的本地交付核对器')]
        self.assertEqual(len(producers),2)

    def test_repeated_successful_call_triggers_independent_completion_review(self):
        call=action('calendar',{'operation':'date_shift','date':'2031-08-18','days':-5})
        result, _ = self.run_assistant('2031年8月18日提前5天是哪天',[call,call])
        self.assertEqual(len(result['tool_calls']),1)
        self.assertEqual(result['completion_check']['state'],'passed')
        self.assertEqual(result['review_history'][0]['state'],'complete')
        self.assertEqual(result['producer_recoveries'][0]['reason'],'repeated_completed_tool')

    def test_duplicate_does_not_hide_missing_numeric_delivery(self):
        spent=action('calculate',{'expression':'30+20'})
        result, _ = self.run_assistant('预算120，花30和20，计算已花总额和剩余预算',[
            spent,spent,action('calculate',{'expression':'120-50'}),
            '{"action":"answer","text":"已核对。"}'],
            review_outputs=['{"state":"missing","quote":"剩余预算","reason":"还缺剩余预算"}',
                            '{"state":"complete"}'])
        self.assertEqual(result['completion_check']['state'],'passed')
        self.assertEqual([c['result']['data']['result'] for c in result['tool_calls']],['50','70'])
        self.assertEqual([r['state'] for r in result['review_history']],['missing','complete'])

    def test_repeated_failed_call_never_becomes_completed(self):
        call=action('calculate',{'expression':'999+20'})
        result, _ = self.run_assistant('计算30加20',[call]*6)
        self.assertFalse(any(c['state']=='completed' for c in result['tool_calls']))
        self.assertEqual(result['producer_recoveries'],[])
        self.assertEqual(result['completion_check']['state'],'unavailable')

    def test_invalid_review_quote_is_repaired_by_reviewer_not_execution(self):
        result, _ = self.run_assistant('计算76加24', [
            action('calculate', {'expression':'76+24'}),'{"action":"answer","text":"已核对。"}'],
            review_outputs=['{"state":"missing","quote":"顺便算退款日期","reason":"遗漏"}',
                            '{"state":"complete"}'])
        self.assertEqual(result['completion_check']['state'],'passed')
        self.assertEqual(len(result['tool_calls']),1)
        self.assertEqual(result['review_history'][0]['state'],'invalid')

    def test_invalid_reviews_never_release_unchecked_completion(self):
        result, _ = self.run_assistant('计算76加24', [
            action('calculate', {'expression':'76+24'}),'{"action":"answer","text":"已核对。"}'],
            review_outputs=['not json','{"state":"complete","unchecked":true}'])
        self.assertEqual(result['completion_check']['state'],'unavailable')
        self.assertEqual(len(result['tool_calls']),1)
        self.assertEqual(len(result['review_history']),2)
        self.assertIn('未完成整项目标核对',result['text'])

    def test_repeated_missing_review_cannot_be_bypassed_when_budget_ends(self):
        result, _ = self.run_assistant('计算已花总额和剩余预算：100元预算，花20元', [
            action('calculate', {'expression':'100-20'}),
            *['{"action":"answer","text":"已核对。"}']*5],
            review_outputs=['{"state":"missing","quote":"已花总额","reason":"未算已花总额"}']*4)
        self.assertEqual(result['completion_check']['state'],'partial')
        self.assertEqual(len(result['review_history']),4)
        self.assertIn('未算已花总额',result['text'])

    def test_chinese_discount_and_people_are_grounded(self):
        result, _ = self.run_assistant('199元买三件，八五折，加20元运费', [
            action('calculate', {'expression': '199*3*0.85+20', 'precision': 2}),
            '{"action":"answer","text":"合计527.45元。"}'])
        self.assertEqual(result['tool_calls'][0]['state'], 'completed')

    def test_model_invented_operand_retries_original_goal(self):
        result, _ = self.run_assistant('午餐100元和交通20元，3人平摊', [
            action('calculate', {'expression': '(100+200)/3'}),
            action('calculate', {'expression': '(100+20)/3'}),
            '{"action":"answer","text":"每人40元。"}'])
        self.assertEqual([c['state'] for c in result['tool_calls']], ['failed', 'completed'])
        self.assertIn('40', result['text'])
        self.assertNotIn('200', result['text'])

    def test_assistant_prose_is_not_numeric_authority(self):
        result, _ = self.run_assistant('把费用除以3', [action('calculate', {'expression': '999/3'})],
                                       history=[{'role': 'assistant', 'text': '费用是999元'}])
        self.assertFalse(any(c['state']=='completed' for c in result['tool_calls']))

    def test_verified_tools_support_followup_and_conversation_lineage(self):
        first, _ = self.run_assistant('158.6、89.9和32.5元，三人均摊', [
            action('calculate', {'expression': '158.6+89.9+32.5'}),
            action('calculate', {'expression': '281/3', 'precision': 2}),
            '{"action":"answer","text":"每人93.67元。"}'])
        second, assistant = self.run_assistant('改成四人呢', [
            action('calculate', {'expression': '281/4', 'precision': 2}),
            '{"action":"answer","text":"每人70.25元。"}'],
            conversation_parent_id=first['id'], thread_id=first['thread_id'])
        self.assertEqual(second['parent_id'], first['id'])
        self.assertEqual(second['tool_calls'][0]['result']['data']['result'], '70.25')
        self.assertIn('verified_previous_tools', assistant.agent.model.calls[0][1])

    def test_tampered_previous_result_is_not_reused(self):
        first, _ = self.run_assistant('100加20', [action('calculate', {'expression': '100+20'}), '{"action":"answer","text":"120"}'])
        path = self.data/'Outputs'/first['id']/'task.json'
        saved = json.loads(path.read_text()); saved['tool_calls'][0]['result']['data']['result'] = '777'
        path.write_text(json.dumps(saved))
        second, _ = self.run_assistant('除以3', [action('calculate', {'expression': '777/3'})], conversation_parent_id=first['id'])
        self.assertFalse(any(c['state']=='completed' for c in second['tool_calls']))

    def test_divide_by_zero_cannot_be_repaired_by_changing_divisor(self):
        result, assistant = self.run_assistant('计算10除以0', [action('calculate', {'expression': '10/0'}), action('calculate', {'expression': '10/1'})])
        self.assertEqual(len(assistant.agent.model.calls), 1)
        self.assertEqual(result['tool_calls'][0]['state'], 'failed')
        self.assertIn('除数不能为0', result['text'])

    def test_relative_week_and_clock_are_program_anchored(self):
        result, _ = self.run_assistant('下周五是哪天', [
            action('calendar', {'operation': 'week_date', 'week_offset': 1, 'weekday': 4}),
            action('calendar', {'operation': 'week_date', 'week_offset': 1, 'weekday': 5}),
            '{"action":"answer","text":"下周五是2026-10-30。"}'])
        self.assertEqual(result['clock']['today'], '2026-10-22')
        self.assertEqual(result['tool_calls'][0]['state'], 'failed')
        self.assertEqual(result['tool_calls'][1]['result']['data']['date'], '2026-10-30')

    def test_invented_date_is_rejected(self):
        result, _ = self.run_assistant('2026年10月22日后两天', [
            action('calendar', {'operation': 'date_shift', 'date': '2030-01-01', 'days': 2})])
        self.assertFalse(any(c['state']=='completed' for c in result['tool_calls']))

    def test_unknown_numbers_in_final_prose_are_not_delivered(self):
        result, _ = self.run_assistant('100加20', [
            action('calculate', {'expression': '100+20'}),
            '{"action":"answer","text":"合计999元。"}',
            '{"action":"answer","text":"合计120元。"}'])
        self.assertNotIn('999', result['text'])
        self.assertIn('120', result['text'])

    def test_input_number_cannot_masquerade_as_computed_conclusion(self):
        result, _ = self.run_assistant('100加20', [action('calculate', {'expression':'100+20'}),
                                                '{"action":"answer","text":"合计100元。"}'])
        self.assertNotIn('合计100元',result['text'])
        self.assertIn('= 120',result['text'])

    def test_precision_metadata_does_not_authorize_a_new_operand(self):
        result, _ = self.run_assistant('100加20', [action('calculate', {'expression':'100+20','precision':8}),
                                                action('calculate', {'expression':'120/8'})])
        self.assertEqual([c['state'] for c in result['tool_calls']],['completed','failed'])

    def test_date_direction_is_preserved(self):
        result, _ = self.run_assistant('今天2天后', [action('calendar', {'operation':'date_shift','days':-2}),
                                                action('calendar', {'operation':'date_shift','days':2}),
                                                '{"action":"answer","text":"已按日历天核对。"}'])
        self.assertEqual(result['tool_calls'][0]['state'],'failed')
        self.assertEqual(result['tool_calls'][1]['result']['data']['date'],'2026-10-24')

    def test_unrequested_week_operation_cannot_replace_today(self):
        result, _ = self.run_assistant('今天是几号', [action('calendar', {'operation':'week_date','week_offset':52,'weekday':7})])
        self.assertFalse(any(c['state']=='completed' for c in result['tool_calls']))

    def test_inclusive_endpoints_are_computed_and_visible(self):
        result, _ = self.run_assistant('2026年10月22日到2026年10月31日相隔多少天，含首尾呢', [
            action('calendar',{'operation':'date_difference','start':'2026-10-22','end':'2026-10-31'}),
            '{"action":"answer","text":"两种口径已分别核对。"}'])
        self.assertEqual(result['tool_calls'][1]['result']['data']['result'],'10')
        self.assertIn('10 天',result['text'])

    def test_parent_directory_symlink_cannot_read_external_tool_journal(self):
        outside = self.data/'external';outside.mkdir()
        (outside/'task.json').write_text('{"id":"linked","thread_id":"thread","tool_calls":[]}')
        outputs=self.data/'Outputs';outputs.mkdir(exist_ok=True)
        (outputs/'linked').symlink_to(outside,target_is_directory=True)
        agent=core.Agent(Model([]),self.data)
        self.assertEqual(GeneralAssistant(agent,core).previous_tools({'conversation_parent_id':'linked','thread_id':'thread'}),[])

    def test_malformed_and_other_thread_history_are_ignored(self):
        folder=self.data/'Outputs'/'old';folder.mkdir(parents=True)
        path=folder/'task.json'
        path.write_text(json.dumps({'id':'old','thread_id':'thread','tool_calls':[None,{'state':'completed','result':None}]}))
        assistant=GeneralAssistant(core.Agent(Model([]),self.data),core)
        self.assertEqual(assistant.previous_tools({'conversation_parent_id':'old','thread_id':'thread'}),[])
        self.assertEqual(assistant.previous_tools({'conversation_parent_id':'old','thread_id':'another'}),[])

    def test_explicit_document_is_a_generated_copy(self):
        result, _ = self.run_assistant('100加20，算完导出Word说明', [
            action('calculate', {'expression': '100+20'}),
            '{"action":"answer","text":"费用合计120元。"}'])
        self.assertEqual({a['type'] for a in result['artifacts']}, {'docx', 'md'})
        self.assertTrue(all(Path(a['path']).is_relative_to(self.data/'Outputs') for a in result['artifacts']))

    def test_clock_context_does_not_need_network(self):
        self.assertEqual(clock_context(date(2026,10,22))['weekday'], '星期四')

    def test_delivery_review_can_fill_missing_requested_total(self):
        result, _ = self.run_assistant('预算4500，已花180乘12，另外320和750，算已花总额和剩余预算', [
            action('calculate',{'expression':'4500-(180*12+320+750)'}),
            '{"action":"answer","text":"核对完成。"}',
            action('calculate',{'expression':'180*12+320+750'}),
            '{"action":"answer","text":"两个要求均已核对。"}'],
            review_outputs=['{"state":"missing","quote":"已花总额","reason":"还缺已花总额"}','{"state":"complete"}'])
        self.assertIn('3230',result['text']);self.assertIn('1270',result['text'])
        self.assertEqual(result['completion_check']['state'],'passed')

    def test_percentage_followup_inherits_only_the_recent_rate_goal(self):
        prior = '45份申请已有36份通过，通过率是多少？'
        history = [{'role': 'user', 'text': prior}]
        self.assertTrue(percentage_request('总申请数不变，又通过4份呢？', history))
        self.assertTrue(percentage_request('如果改成40份通过呢？', history))
        self.assertFalse(percentage_request('午餐120元，3人均摊，每人多少？', history))
        self.assertFalse(percentage_request('那午餐120元，3人均摊呢？', history))
        self.assertFalse(percentage_request('不用再算通过率了。午餐120元，3人均摊。', history))
        self.assertFalse(percentage_request('那改成4人呢？', history + [
            {'role': 'user', 'text': '午餐120元，3人均摊。'}]))
        self.assertTrue(percentage_request('先不算预算。现在通过率是多少？', history))

    def test_rate_then_unrelated_cost_does_not_multiply_by_one_hundred(self):
        prior = '45份申请已有36份通过，通过率是多少？'
        first, _ = self.run_assistant(prior, [
            action('calculate', {'expression': '36/45', 'precision': 2}),
            '{"action":"answer","text":"通过率已经核对。"}'])
        self.assertIn('80.00%', first['text'])
        history = [{'role': 'user', 'text': prior}, {'role': 'assistant', 'text': first['text']}]
        followup, _ = self.run_assistant('总申请数不变，又通过4份呢？', [
            action('calculate', {'expression': '(36+4)/45', 'precision': 2}),
            '{"action":"answer","text":"通过率已经更新。"}'],
            conversation_parent_id=first['id'], thread_id=first['thread_id'], history=history)
        self.assertIn('88.89%', followup['text'])
        for prompt in ('午餐120元，3人均摊，每人多少？', '不用再算通过率了。午餐120元，3人均摊。'):
            with self.subTest(prompt=prompt):
                result, _ = self.run_assistant(prompt, [
                    action('calculate', {'expression': '120/3', 'precision': 2}),
                    '{"action":"answer","text":"分摊金额已核对。"}'],
                    conversation_parent_id=first['id'], thread_id=first['thread_id'], history=history)
                self.assertEqual(result['tool_calls'][0]['result']['data']['result'], '40.00')
                self.assertEqual(result['tool_calls'][0]['arguments']['expression'], '120/3')
                self.assertNotIn('%', result['text'])

    def test_explicit_date_year_is_not_reauthorized_as_current_year(self):
        for text in ('2028年2月28日往后两天', '2028-02-28往后两天'):
            with self.subTest(text=text):
                known = dates_in(text, '2026-10-22')
                self.assertIn('2028-02-28', known)
                self.assertNotIn('2026-02-28', known)
        self.assertNotIn('2026-02-28', dates_in('2027年2月29日', '2026-10-22'))
        self.assertIn('2026-03-01', dates_in('2028年2月28日，另外3月1日', '2026-10-22'))
        result, _ = self.run_assistant('2028年2月28日往后两天是什么日子', [
            action('calendar', {'operation': 'date_shift', 'date': '2026-02-28', 'days': 2}),
            action('calendar', {'operation': 'date_shift', 'date': '2028-02-28', 'days': 2}),
            '{"action":"answer","text":"日期已经核对。"}'])
        self.assertEqual([call['state'] for call in result['tool_calls']], ['failed', 'completed'])
        self.assertEqual(result['tool_calls'][1]['result']['data']['date'], '2028-03-01')


if __name__ == '__main__':
    unittest.main()
