"""Select by frozen end-to-end goals, retaining exclusions and incorrect outputs."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--extension', action='store_true')
    parser.add_argument('--adaptation', action='store_true')
    args = parser.parse_args()
    assert not (args.extension and args.adaptation)
    prefix = 'adaptation/' if args.adaptation else 'extension-' if args.extension else ''
    protocol_path = ROOT / ('qa/v0.24/adaptation/protocol.json' if args.adaptation else 'qa/v0.24/extension-protocol.json' if args.extension else 'qa/v0.24/search-protocol.json')
    protocol = json.loads(protocol_path.read_text())
    records = json.loads((ROOT / ('qa/v0.24/' + prefix + 'screen-records.json')).read_text())
    exclusions = json.loads((ROOT / ('qa/v0.24/' + prefix + 'screen-exclusions.json')).read_text())
    excluded = {r['model'] for r in exclusions}
    ready = [m for m in protocol['models'] if m not in excluded]
    assert [(r['suite'], r['model']) for r in records] == [(g['suite'], m) for g in protocol['screen'] for m in ready]
    assert protocol['backend_hashes'] == {p.name: sha(p) for p in (ROOT / 'backend').glob('*.py')}
    assert sha(ROOT / protocol.get('runner', 'scripts/check_model_search_v24.py')) == protocol['runner_sha256']
    assert all(sha(ROOT / p) == h for p, h in protocol['input_hashes'].items())
    results, summaries = {}, {}
    for model in ready:
        reports = []
        for record in (r for r in records if r['model'] == model):
            report = json.loads((ROOT / record['report']).read_text())
            group = next(g for g in protocol['screen'] if g['suite'] == record['suite'])
            assert [c['id'] for c in report['cases']] == group['expected_ids']
            assert report['model'] == model and report['suite'] == group['suite']
            assert report['source_hashes'] == protocol['backend_hashes']
            assert report['runner_sha256'] == protocol['runner_sha256']
            assert report['source_hashes_unchanged'] and report['network_denied']
            assert report['common_token_limits'] == {'input': 8192, 'output': 1800}
            assert not report['thinking_enabled']
            assert report['passed'] == sum(bool(c['passed']) for c in report['cases'])
            reports.append(report)
        cases = [c for r in reports for c in r['cases']]
        assert len(cases) == protocol['screen_goals'] == 6
        table_checks = ['expected_rows', 'expected_columns', 'preview_matches_xlsx', 'csv_matches_xlsx',
                        'required_summary', 'typed_summary_rows']
        wrong_tables = [c['id'] for c in cases if 'rows' in c and
                        any(c.get('checks', {}).get(k) is False for k in table_checks)]
        timings = [c['seconds'] for c in cases if c.get('model_executed')]
        summary = {'passed': sum(c['passed'] for c in cases), 'total': len(cases),
                   'model_executed_goals': sum(bool(c.get('model_executed')) for c in cases),
                   'dependency_blocked': sum(bool(c.get('dependency_blocked')) for c in cases),
                   'wrong_delivered_tables': len(wrong_tables), 'wrong_table_goals': wrong_tables,
                   'model_task_seconds_median': round(median(timings), 3) if timings else None,
                   'peak_mlx_gb': max(r['peak_mlx_gb'] for r in reports),
                   'peak_process_rss_gb': max(r['peak_process_rss_gb'] for r in reports),
                   'failures': [{'id': c['id'], 'error': c.get('error'),
                                 'failed_checks': [k for k, v in c.get('checks', {}).items() if v is False],
                                 'dependency_blocked': c.get('dependency_blocked', False)} for c in cases if not c['passed']]}
        limits = protocol['preferred_admission']
        gates = {'completed_goals': summary['passed'] >= limits['screen_passed_min'],
                 'no_wrong_tables': summary['wrong_delivered_tables'] <= limits['wrong_delivered_tables_max'],
                 'memory': summary['peak_mlx_gb'] <= limits['peak_mlx_gb_max'],
                 'latency': bool(timings) and summary['model_task_seconds_median'] <= limits['median_model_task_seconds_max']}
        summary.update(admission_checks=gates, admitted=all(gates.values()))
        summaries[model] = summary
        results[model] = cases
    ranked = sorted(ready, key=lambda m: (-summaries[m]['passed'], summaries[m]['wrong_delivered_tables'],
                                         summaries[m]['model_task_seconds_median'] or float('inf')))
    selected = next((m for m in ranked if summaries[m]['admitted']), None)
    output = {'time': datetime.now().astimezone().isoformat(), 'protocol_sha256': sha(protocol_path),
              'models': summaries, 'exclusions': exclusions, 'ranked': ranked, 'selected': selected,
              'reports': records, 'cases': results,
              'scope': 'Six known screening goals, not final model admission or unseen generalization. MLX and RSS overlap; do not add. Compatibility-excluded model has zero office tasks, not six failed tasks.'}
    target = ROOT / ('qa/v0.24/' + prefix + 'screen-summary.json')
    assert not target.exists(), 'Preserve the first collected screen.'
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'selected': selected, 'models': summaries, 'exclusions': exclusions}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
