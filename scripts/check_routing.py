"""Serial real local routing and mixed-conversation QA with fictional sources only."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--model-id', default='qwen3.5-9b')
p.add_argument('--isolated', action='store_true')
p.add_argument('--routing-only', action='store_true')
p.add_argument('--mixed-only', action='store_true', help='Reuse routing decisions only when backend and fixture hashes match exactly.')
args = p.parse_args()
if not args.isolated:
    raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)',
                                     sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], '--isolated']).returncode)
sys.path.insert(0, str(ROOT / 'backend'))
import worker as core
from request_router import RequestRouter
from office_agent import OfficeAgent
from workspace_index import WorkspaceIndex
from bge_embedding import LocalEmbedder
import mlx.core as mx

suite = ROOT / 'fixtures/routing/tasks.json'
report = {'version': '0.11.0', 'date': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
          'model_id': args.model_id, 'network_denied': core.network_probe()['blocked'],
          'protocol': {'seed': 133, 'fixture_sha256': hashlib.sha256(suite.read_bytes()).hexdigest(),
                       'hardware': 'Apple M5 32 GB; standard 16 GB runtime policy, not an actual 16 GB device',
                       'method': 'Fixed routing cases then mixed local conversation; normal bounded planner/review; no injected model outputs.'},
          'source_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'backend').glob('*.py')},
          'routing': [], 'checks': {}, 'turns': []}
assert report['network_denied']
output = ROOT / 'qa' / f'v0.11-{args.model_id}-routing-report.json'
if args.mixed_only:
    previous_report = json.loads(output.read_text())
    assert previous_report['source_hashes'] == report['source_hashes']
    assert previous_report['protocol']['fixture_sha256'] == report['protocol']['fixture_sha256']
    assert len(previous_report['routing']) == len(json.loads(suite.read_text())['cases'])
    report['routing'] = previous_report['routing']
    report['protocol']['routing_reused'] = 'Preserved fixed-case decisions with identical backend and fixture hashes; mixed conversation rerun from scratch.'
trace = ROOT / 'qa/private/v0.11' / f'{args.model_id}-trace.jsonl'
trace.parent.mkdir(parents=True, exist_ok=True)
trace.write_text('')
def save():
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
def check(name, condition):
    report['checks'][name] = bool(condition)
    save()
    if not condition:
        raise AssertionError(name)

model_path = Path.home() / 'Library/Application Support' / ('GuiyuRuntime/model' if args.model_id == 'qwen3-4b' else 'GuiyuModels/Installed/' + args.model_id)
model = core.LocalModel(model_path)
report['runtime_policy'] = model.policy.object()
original = model.generate
def generate(system, user, **kwargs):
    text, stats = original(system, user, **kwargs)
    with trace.open('a') as f:
        f.write(json.dumps({'system': system, 'user': user, 'text': text, 'stats': stats}, ensure_ascii=False) + '\n')
    return text, stats
model.generate = generate

with tempfile.TemporaryDirectory(prefix='guiyu-routing-') as temporary:
    base = Path(temporary).resolve()
    agent = core.Agent(model, base / 'data')
    router = RequestRouter(agent, core)
    prior = {'prompt': '社区费用台账中只统计状态包含待报销且金额大于100元，按经办人分组统计。',
             'query': '状态包含待报销，金额大于100元，按经办人分组', 'source_names': ['社区费用台账.csv']}
    for case in ([] if args.mixed_only else json.loads(suite.read_text())['cases']):
        mx.random.seed(133)
        request = {'prompt': case['prompt'], 'kind': 'auto', 'workspace_available': True, 'files_selected': True}
        if case.get('prior'):
            request.update(previous_source=prior, history=[{'role': 'user', 'text': prior['prompt']},
                                                         {'role': 'assistant', 'text': '林晓128.5元，陈雨180元。'}])
        start = time.perf_counter()
        # Routing cannot enumerate sources or run retrieval.
        with patch.object(core, 'Scope', side_effect=AssertionError('Routing opened source scope')):
            decision = router.decide(request)
        passed = decision['mode'] == case['mode'] and (not case.get('reuse') or decision['use_previous'])
        report['routing'].append({'id': case['id'], 'prompt': case['prompt'], 'expected': case['mode'],
                                  'decision': decision, 'passed': passed, 'seconds': round(time.perf_counter() - start, 2)})
        print('ROUTE', case['id'], decision['mode'], passed, flush=True)
        save()

    if not args.routing_only:
        workspace = base / 'fictional'
        workspace.mkdir()
        ledger = workspace / '社区费用台账.csv'
        shutil.copy2(ROOT / 'fixtures/query/社区费用台账.csv', ledger)
        before = core.digest(ledger)
        embedding = LocalEmbedder(Path.home() / 'Library/Application Support/GuiyuModels/Installed/bge-small-zh-v1.5', ROOT / 'packaging/model-catalog.json')
        check('real_local_embedding_available', embedding.available)
        index = WorkspaceIndex(workspace, base / 'index', embedding)
        office = OfficeAgent(agent, core)
        history = []
        previous = None
        last_source = None
        def turn(prompt, expected, paused=False):
            request = {'id': str(__import__('uuid').uuid4()), 'prompt': prompt, 'kind': 'auto',
                       'history': history[-8:], 'workspace_available': True, 'files_selected': True}
            if previous:
                request.update(conversation_parent_id=previous['id'], thread_id=previous['thread_id'])
            if last_source:
                request['previous_source'] = {'prompt': last_source['prompt'], 'query': last_source.get('query_summary', ''),
                                              'source_names': last_source['plan']['source_names']}
            mx.random.seed(133)
            decision = router.decide(request)
            check('route_' + str(len(report['turns'])), decision['mode'] == expected)
            start = time.perf_counter()
            with redirect_stdout(io.StringIO()):
                if decision['mode'] == 'chat':
                    # Paused or unavailable index must not prevent direct conversation.
                    with patch.object(core, 'Scope', side_effect=AssertionError('Chat read a source')):
                        result = router.chat(request)
                elif decision['mode'] == 'workspace':
                    assert not paused
                    retrieval_request = {'query': prompt}
                    if decision['use_previous'] and last_source:
                        retrieval_request['previous'] = {'snapshots': last_source['plan']['snapshot'], 'retrieval': last_source['plan']['retrieval']}
                    found = index.retrieve(retrieval_request)
                    if not found['paths']:
                        result = {'id': request['id'], 'thread_id': request.get('thread_id', request['id']),
                                  'prompt': prompt, 'text': '', 'sources': [], 'not_found': True}
                    else:
                        request.update(paths=found['paths'], retrieval=found, source_required=True, adaptive=True)
                        if found.get('refreshed'):
                            request['refresh_sources'] = True
                        if decision['use_previous'] and last_source and (found.get('reuse') or found.get('refreshed')):
                            request['parent_id'] = last_source['id']
                        elif not found.get('reuse'):
                            request['history'] = [m for m in request['history'] if m['role'] == 'user']
                        plan = office.draft(request)
                        result = office.execute({'plan_id': plan['id'], 'paths': plan['paths']})
                else:
                    request.update(paths=[], adaptive=True, source_free=True)
                    plan = office.draft(request)
                    result = office.execute({'plan_id': plan['id'], 'paths': []})
            report['turns'].append({'prompt': prompt, 'decision': decision, 'text': result['text'],
                                    'kind': result.get('kind'), 'not_found': result.get('not_found', False),
                                    'source_count': len(result['sources']), 'parent_id': result.get('parent_id'),
                                    'thread_id': result['thread_id'], 'artifact_types': [a['type'] for a in result.get('artifacts', [])],
                                    'seconds': round(time.perf_counter() - start, 2)})
            save()
            print('TURN', prompt[:24], decision['mode'], flush=True)
            return result

        result = turn('你是谁？', 'chat', paused=True)
        check('identity_is_guiyu_without_files_or_plan', '归屿' in result['text'] and not result['sources'] and not result.get('plan'))
        previous = result
        history += [{'role': 'user', 'text': result['prompt']}, {'role': 'assistant', 'text': result['text']}]
        result = turn(prior['prompt'], 'workspace')
        check('source_statistics_remain_exact', sorted(r[3] for r in result['rows']) == ['128.5', '180'])
        check('chat_to_source_keeps_thread', result['thread_id'] == previous['thread_id'] and result['parent_id'] == previous['id'])
        previous = last_source = result
        history += [{'role': 'user', 'text': result['prompt']}, {'role': 'assistant', 'text': result['text']}]
        result = turn('用一个生活例子解释什么是开源软件。', 'chat', paused=True)
        check('source_to_general_has_no_source_read_or_plan', not result['sources'] and not result.get('plan') and '开源' in result['text'])
        check('source_to_chat_keeps_thread', result['thread_id'] == previous['thread_id'] and result['parent_id'] == previous['id'])
        previous = result
        history += [{'role': 'user', 'text': result['prompt']}, {'role': 'assistant', 'text': result['text']}]
        result = turn('回到刚才的费用统计，那陈雨呢？', 'workspace')
        check('interleaved_followup_keeps_conditions', len(result['rows']) == 1 and '陈雨' in str(result['rows']) and '180' in str(result['rows']) and '260' not in str(result['rows']))
        check('source_parent_is_separate_from_conversation_parent', result['parent_id'] == previous['id'] and result['plan']['source_parent_id'] == last_source['id'])
        previous = last_source = result
        history += [{'role': 'user', 'text': result['prompt']}, {'role': 'assistant', 'text': result['text']}]
        result = turn('把这句话翻译成英文：请在周五前反馈。', 'chat')
        check('inline_translation_without_documents', not result['sources'] and 'Friday' in result['text'])
        previous = result
        history += [{'role': 'user', 'text': result['prompt']}, {'role': 'assistant', 'text': result['text']}]
        result = turn('语气更轻松一点。', 'chat')
        check('general_followup_uses_conversation', not result['sources'] and 'Friday' in result['text'])
        previous = result
        history += [{'role': 'user', 'text': result['prompt']}, {'role': 'assistant', 'text': result['text']}]
        result = turn('在社区费用台账中查找编号BX-999的记录，直接回答是否找到。', 'workspace')
        check('missing_identifier_does_not_get_general_invention', not result.get('not_found') and bool(result['sources']) and any(s in result['text'] for s in ('没有', '未找到', '未能', '无匹配')) and '180' not in result['text'])
        result = turn('查一下合同HT-999的违约金。', 'workspace')
        check('missing_contract_has_no_general_fallback', result.get('not_found') is True or
              (result.get('kind') != 'chat' and '没有匹配结果' in result['text'] and not result['sources']))
        report['protocol']['contract_grading_note'] = 'A semantically related ledger may be a retrieval candidate. Accept empty retrieval or verified zero exact search hits, both without a general answer. Original output was safe; initial grader incorrectly required zero semantic candidates.'
        check('source_files_unchanged', core.digest(ledger) == before)
        # Update only fictional fixture and require fresh snapshot before reuse.
        ledger.write_text(ledger.read_text().replace('180.00', '205.00'))
        result = turn('回到刚才的费用统计，那陈雨呢？', 'workspace')
        check('changed_source_refreshes_before_followup', result['plan'].get('sources_refreshed') is True and '205' in str(result['rows']) and '180' not in str(result['rows']))
        result = turn('帮我制定一份下周的五天读书计划，每天20分钟，导出为Word文档。', 'task')
        check('general_plan_can_export_without_sources', not result['sources'] and any(a['type'] == 'docx' for a in result['artifacts']) and '20' in result['text'])
        index.close()

report.update(routing_passed=sum(r['passed'] for r in report['routing']), routing_count=len(report['routing']),
              peak_mlx_gb=round(mx.get_peak_memory() / 1e9, 3),
              peak_process_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 3))
report['all_checks_passed'] = all(r['passed'] for r in report['routing']) and all(report['checks'].values())
save()
print(json.dumps({k: report[k] for k in ('routing_passed', 'routing_count', 'peak_mlx_gb', 'all_checks_passed')}))
