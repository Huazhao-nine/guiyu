"""Recheck failed candidate tables on CPU, separately from user delivery scores."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
import worker as core
from workbook_data import inspect_documents, prepare_table
from workbook_flow import TableFlow
from check_workbook_v22_plan_replay import action
from check_model_comparison_v23 import equal_rows


def replay(item):
    files = [{'path': str(ROOT / path), 'name': Path(path).name} for path in item['source_fixtures']]
    source = prepare_table(inspect_documents(files, core), item['selection']['tables'])
    flow = TableFlow(source, item['goal'])
    mapping = {'V0': 'V0', 'P0': 'P0'}
    for step in item['graph']:
        event = flow.apply(dict(action(step['operation']), input=mapping[step['input']]))
        mapping[step['id']] = event['view']
    finish = deepcopy(item['finish'])
    finish['result'] = mapping[finish['result']]
    finish['summaries'] = [mapping[v] for v in finish.get('summaries', [])]
    return flow.finish(finish, item['contract'])


def main():
    protocol = json.loads((ROOT / 'qa/v0.23/protocol.json').read_text())
    summary = json.loads((ROOT / 'qa/v0.23/model-comparison.json').read_text())
    target = ROOT / 'qa/v0.23/candidate-intermediate-audit.json'
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert protocol['backend_hashes'] == {p.name: digest(p) for p in (ROOT / 'backend').glob('*.py')}
    if '--capture' in sys.argv:
        assert not target.exists(), 'Keep the original diagnostic capture.'
        rows = []
        for record in summary['reports']:
            if record['model'] != 'qwen3.8-27b':
                continue
            report = json.loads((ROOT / record['report']).read_text())
            stamp = Path(record['report']).stem.split('-qwen3.8-27b-', 1)[1]
            trace = ROOT / 'qa/private/v0.23' / stamp / 'model-trace.jsonl'
            calls = [json.loads(line) for line in trace.read_text().splitlines()]
            for case in report['cases']:
                if case['passed'] or case.get('dependency_blocked'):
                    continue
                item = {'id': case['id'], 'original_status': 'failed',
                        'counts_as_completed_agent_task': False, 'model_calls': 0}
                selection, overview, review, finish = None, None, None, None
                for call in [c for c in calls if c['case'] == case['id']]:
                    try:
                        output = core.parse_json(call.get('output', ''))
                    except (ValueError, TypeError):
                        continue
                    if output.get('tables'):
                        selection = output
                        overview = json.loads(call['user'])['工作簿结构']
                    if output.get('tool') == 'finish':
                        finish = output
                    if output.get('state') in ('passed', 'missing') and '最终明细' in call.get('user', ''):
                        review = json.loads(call['user'])
                try:
                    assert selection and overview and review and finish, 'No complete checked view was recorded.'
                    fixtures = []
                    for name in dict.fromkeys(t['file'] for t in overview):
                        private_source = trace.parent / 'workspace' / name
                        sha = digest(private_source)
                        candidates = [p for p, v in protocol['input_hashes'].items()
                                      if Path(p).name == name and v == sha]
                        assert candidates, 'Missing matching frozen fictional source.'
                        fixtures.append(candidates[0])
                    expected = []
                    for path in protocol['input_hashes']:
                        if not path.endswith('/tasks.json'):
                            continue
                        expected.extend(c for c in json.loads((ROOT / path).read_text())['cases']
                                        if c['id'] == case['id'] and c['prompt'] == case['prompt'])
                    assert len(expected) == 1
                    item.update(source_fixtures=fixtures, selection=selection, goal=review['目标'],
                                graph=review['已执行'], finish=finish, contract=review['交付约定'],
                                expected_rows=expected[0]['rows'])
                    result = replay(item)
                    item.update(columns=result['columns'], rows=result['rows'],
                                intermediate_rows_match=equal_rows(result['rows'], item['expected_rows']))
                except Exception as exc:
                    item.update(intermediate_rows_match=False, replay_error=str(exc)[:400])
                rows.append(item)
        data = {'version': '0.23-comparison', 'source_hashes': protocol['backend_hashes'],
                'cases': rows, 'model_calls': 0,
                'scope': 'All failed nondependent candidate cases are audited when a checked graph exists. CPU replay uses only actually recorded model operations and frozen fictional sources. It verifies intermediate primary rows, not Word/files, all semantics or completed user tasks. No primary scores are changed.'}
        data['intermediate_rows_match'] = sum(bool(c['intermediate_rows_match']) for c in rows)
        data['failed_candidate_cases_audited'] = len(rows)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    data = json.loads(target.read_text())
    assert data['source_hashes'] == protocol['backend_hashes']
    for item in data['cases']:
        assert not item['counts_as_completed_agent_task']
        if 'replay_error' in item:
            continue
        result = replay(item)
        assert result['columns'] == item['columns'] and result['rows'] == item['rows']
        assert equal_rows(result['rows'], item['expected_rows']) == item['intermediate_rows_match']
    print(json.dumps({'intermediate_rows_match': data['intermediate_rows_match'],
                      'failed_cases_audited': data['failed_candidate_cases_audited'],
                      'no_primary_score_changes': True,
                      'cases': [{k: c.get(k) for k in ['id', 'intermediate_rows_match', 'replay_error']}
                                for c in data['cases']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
