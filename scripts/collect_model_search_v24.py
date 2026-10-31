"""Summarize the full study without merging incompatible scopes or hiding failures."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(reports):
    cases = [c for r in reports for c in r['cases']]
    times = [c['seconds'] for c in cases if c.get('model_executed')]
    table_checks = ['expected_rows', 'expected_columns', 'preview_matches_xlsx', 'csv_matches_xlsx',
                    'required_summary', 'typed_summary_rows']
    wrong = [c['id'] for c in cases if 'rows' in c and any(c.get('checks', {}).get(k) is False for k in table_checks)]
    return {'passed': sum(c['passed'] for c in cases), 'total': len(cases),
            'model_executed_goals': sum(bool(c.get('model_executed')) for c in cases),
            'dependency_blocked': sum(bool(c.get('dependency_blocked')) for c in cases),
            'deterministic_completed': sum(c['passed'] and not c.get('model_executed') for c in cases),
            'wrong_delivered_tables': len(wrong), 'wrong_table_goals': wrong,
            'model_task_seconds_median': round(median(times), 3) if times else None,
            'peak_mlx_gb': max(r['peak_mlx_gb'] for r in reports),
            'peak_process_rss_gb': max(r['peak_process_rss_gb'] for r in reports),
            'failures': [{'id': c['id'], 'error': c.get('error'),
                          'failed_checks': [k for k, v in c.get('checks', {}).items() if v is False],
                          'model_executed': c.get('model_executed', False),
                          'dependency_blocked': c.get('dependency_blocked', False)} for c in cases if not c['passed']]}


def main():
    target = ROOT / 'qa/v0.24/model-search.json'
    assert not target.exists(), 'Preserve the first final study summary.'
    screens = [json.loads((ROOT / ('qa/v0.24/' + prefix + 'screen-summary.json')).read_text())
               for prefix in ['', 'extension-']]
    selected = [s['selected'] for s in screens if s['selected']]
    assert len(selected) <= 1, 'Explicitly rank multiple admitted candidates before confirmation.'
    reports = []
    for s in screens:
        for record in s['reports']:
            report = json.loads((ROOT / record['report']).read_text())
            assert report['source_hashes_unchanged'] and report['network_denied']
            reports.append((record, report))
    baseline = json.loads((ROOT / 'qa/v0.23/model-comparison.json').read_text())
    ids = {c['id'] for c in screens[0]['cases']['glm-4.7-flash']}
    paired = [c for c in baseline['pairs'] if c['id'] in ids]
    assert len(paired) == 6
    historical = {name: {'passed': sum(c[side]['passed'] for c in paired), 'total': 6,
                         'from': 'qa/v0.23/model-comparison.json',
                         'note': 'Same six goals and backend, historical v23 run; not a newly rerun paired baseline.'}
                  for name, side in [('qwen3.5-9b', 'baseline'), ('qwen3.8-27b', 'candidate')]}
    result = {'version': '0.24-model-search', 'time': datetime.now().astimezone().isoformat(),
              'hardware': 'Apple M5 32GB', 'selected_after_screen': selected[0] if selected else None,
              'screens': [{'summary': 'qa/v0.24/' + prefix + 'screen-summary.json',
                          'models': s['models'], 'exclusions': s['exclusions']} for prefix, s in zip(['', 'extension-'], screens)],
              'historical_six_goal_reference': historical,
              'backend_hashes': reports[0][1]['source_hashes'],
              'network_denied_all_office_runs': all(r['network_denied'] for _, r in reports),
              'scope': 'Frozen local Chinese office tasks. All traces and failures retained. No normal application/history operated, no arbitrary shell, no cloud inference, and no original-file mutations. Model and backend fit are measured jointly; these are not pure size-causality results or independent user testing.'}
    result['backend_unchanged'] = result['backend_hashes'] == {p.name: sha(p) for p in (ROOT / 'backend').glob('*.py')}
    assert result['backend_unchanged']
    if selected:
        protocol_path = ROOT / 'qa/v0.24/confirmation-protocol.json'
        protocol = json.loads(protocol_path.read_text())
        records = json.loads((ROOT / 'qa/v0.24/confirmation-records.json').read_text())
        assert [r['suite'] for r in records] == [g['suite'] for g in protocol['groups']]
        assert protocol['model'] == selected[0]
        assert protocol['backend_hashes'] == result['backend_hashes']
        assert sha(ROOT / protocol['runner']) == protocol['runner_sha256']
        assert all(sha(ROOT / p) == h for p, h in protocol['input_hashes'].items())
        known, novel, cases = [], [], []
        for record, group in zip(records, protocol['groups']):
            report = json.loads((ROOT / record['report']).read_text())
            assert [c['id'] for c in report['cases']] == group['expected_ids']
            assert report['source_hashes'] == protocol['backend_hashes']
            assert report['runner_sha256'] == protocol['runner_sha256']
            assert report['network_denied'] and report['source_hashes_unchanged']
            assert report['common_token_limits'] == {'input': 8192, 'output': 1800}
            assert not report['thinking_enabled']
            (novel if record['suite'] == 'novel' else known).append(report)
            cases.extend({'suite': record['suite'], **c} for c in report['cases'])
        result['confirmation'] = {'model': selected[0], 'known': summarize(known), 'new': summarize(novel),
                                  'reports': records, 'cases': cases, 'protocol_sha256': sha(protocol_path),
                                  'new_scope': 'Four pre-frozen first-use developer-synthesized goals; no candidate tuning after reading their outputs.'}
        assert result['confirmation']['known']['total'] == 18 and result['confirmation']['new']['total'] == 4
    else:
        result['confirmation'] = {'executed': False, 'reason': 'No candidate met the frozen screen admission. Novel4 remain unused.'}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['selected_after_screen', 'historical_six_goal_reference', 'backend_unchanged']} |
                     ({'known': result['confirmation']['known'], 'new': result['confirmation']['new']} if selected else
                      {'confirmation': result['confirmation']}), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
