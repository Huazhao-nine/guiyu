"""Validate paired scope and summarize model changes without hiding failures."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def status(case):
    if case['passed']:
        return 'completed'
    if case.get('dependency_blocked'):
        return 'dependency_not_run'
    if 'rows' in case:
        return 'delivered_but_failed_fixed_checks'
    return 'execution_failed'


def main():
    protocol = json.loads((ROOT / 'qa/v0.23/protocol.json').read_text())
    records = json.loads((ROOT / 'qa/v0.23/matrix-records.json').read_text())
    expected_order = [(g['suite'], m) for g in protocol['groups'] for m in protocol['models']]
    assert [(r['suite'], r['model']) for r in records] == expected_order
    assert protocol['backend_hashes'] == {p.name: digest(p) for p in (ROOT / 'backend').glob('*.py')}
    assert digest(ROOT / 'scripts/check_model_comparison_v23.py') == protocol['runner_sha256']
    assert all(digest(ROOT / p) == sha for p, sha in protocol['input_hashes'].items())
    assert digest(ROOT / 'qa/v0.23/model-manifests.json') == protocol['model_manifest_sha256']
    reports, by_model = {}, {m: [] for m in protocol['models']}
    for row in records:
        path = ROOT / row['report']
        result = json.loads(path.read_text())
        group = next(g for g in protocol['groups'] if g['suite'] == row['suite'])
        assert result['model'] == row['model'] and result['suite'] == row['suite']
        assert [c['id'] for c in result['cases']] == group['expected_ids']
        assert result['source_hashes'] == protocol['backend_hashes']
        assert result['source_hashes_unchanged'] and result['network_denied']
        assert result['runner_sha256'] == protocol['runner_sha256']
        assert not result['thinking_enabled']
        assert result['common_token_limits'] == {'input': 8192, 'output': 1800}
        assert result['passed'] == sum(bool(c['passed']) for c in result['cases'])
        reports[row['suite'], row['model']] = result
        by_model[row['model']].extend(result['cases'])
    pairs = []
    for group in protocol['groups']:
        for left, right in zip(reports[group['suite'], protocol['models'][0]]['cases'],
                               reports[group['suite'], protocol['models'][1]]['cases']):
            assert left['id'] == right['id'] and left['prompt'] == right['prompt']
            pairs.append({'suite': group['suite'], 'id': left['id'],
                          'baseline': {k: left.get(k) for k in ['passed', 'seconds', 'error', 'model_executed', 'dependency_blocked']}
                                      | {'status': status(left)},
                          'candidate': {k: right.get(k) for k in ['passed', 'seconds', 'error', 'model_executed', 'dependency_blocked']}
                                       | {'status': status(right)}})
    assert len(pairs) == protocol['goals_per_model'] == 18
    summary = {}
    for model, cases in by_model.items():
        selected = [v for (suite, name), v in reports.items() if name == model]
        times = [c['seconds'] for c in cases if c.get('model_executed')]
        summary[model] = {'passed': sum(bool(c['passed']) for c in cases), 'total': len(cases),
                          'model_executed': sum(bool(c.get('model_executed')) for c in cases),
                          'dependency_blocked': sum(bool(c.get('dependency_blocked')) for c in cases),
                          'deterministic_completed': sum(c['passed'] and not c.get('model_executed') for c in cases),
                          'delivered_but_failed_checks': sum(status(c) == 'delivered_but_failed_fixed_checks' for c in cases),
                          'model_task_seconds_median': median(times),
                          'total_case_seconds': round(sum(c['seconds'] for c in cases), 2),
                          'load_seconds_median': median(v['load_seconds'] for v in selected),
                          'peak_mlx_gb': max(v['peak_mlx_gb'] for v in selected),
                          'peak_process_rss_gb': max(v['peak_process_rss_gb'] for v in selected),
                          'groups': {suite: {'passed': v['passed'], 'total': v['total']}
                                     for (suite, name), v in reports.items() if name == model}}
    both = [p for p in pairs if p['baseline']['passed'] and p['candidate']['passed']
            and p['baseline']['model_executed'] and p['candidate']['model_executed']]
    timing = {'paired_successes_with_model_calls': len(both),
              'baseline_median_seconds': median(p['baseline']['seconds'] for p in both) if both else None,
              'candidate_median_seconds': median(p['candidate']['seconds'] for p in both) if both else None}
    result = {'version': '0.23-comparison', 'time': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'hardware': 'Apple M5 32GB', 'protocol_sha256': digest(ROOT / 'qa/v0.23/protocol.json'),
              'protocol_clarification': 'qa/v0.23/protocol-clarification.json',
              'source_hashes': protocol['backend_hashes'], 'reports': records,
              'models': summary, 'paired_timings': timing,
              'recoveries': [p['id'] for p in pairs if not p['baseline']['passed'] and p['candidate']['passed']],
              'regressions': [p['id'] for p in pairs if p['baseline']['passed'] and not p['candidate']['passed']],
              'both_failed': [p['id'] for p in pairs if not p['baseline']['passed'] and not p['candidate']['passed']],
              'pairs': pairs,
              'limits': protocol['method'] + ' MLX allocation and RSS overlap and must not be added; neither is whole-system peak. Loads use an existing OS file cache. Scope is local workbook work and one conversation chain, not every general-Agent capability.'}
    probe = ROOT / 'qa/v0.23/thinking-probe-report.json'
    if probe.exists():
        result['separate_thinking_probes'] = {'path': str(probe.relative_to(ROOT)), 'sha256': digest(probe)}
    audit = ROOT / 'qa/v0.23/candidate-intermediate-audit.json'
    if audit.exists():
        result['separate_intermediate_audit'] = {'path': str(audit.relative_to(ROOT)), 'sha256': digest(audit),
                                                 'affects_primary_scores': False}
    (ROOT / 'qa/v0.23/model-comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'models': summary, 'recoveries': result['recoveries'],
                      'regressions': result['regressions'], 'both_failed': result['both_failed']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
