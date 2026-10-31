"""Screen two verified candidates on the same six known office goals."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path.home() / 'Library/Application Support/GuiyuRuntime/python/bin/python'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = json.loads((ROOT / 'qa/v0.24/search-protocol.json').read_text())
    path = ROOT / 'qa/v0.24/screen-records.json'
    assert not path.exists(), 'Preserving the first screening records.'
    eligible, excluded = [], []
    for model in protocol['models']:
        manifest = json.loads((ROOT / 'qa/v0.24' / (model + '-manifest.json')).read_text())
        assert manifest['upstream_hashes_verified']
        assert manifest['revision'] == protocol['candidate_revisions'][model]
        smoke = json.loads((ROOT / 'qa/v0.24' / (model + '-compatibility.json')).read_text())
        assert smoke['network_denied']
        if smoke['passed']:
            eligible.append(model)
        else:
            excluded.append({'model': model, 'reason': 'source_free_compatibility_failed',
                             'report': 'qa/v0.24/' + model + '-compatibility.json',
                             'office_goals_executed': 0})
    assert eligible, 'No compatible candidate; preserve failures and investigate first.'
    (ROOT / 'qa/v0.24/screen-exclusions.json').write_text(json.dumps(excluded, ensure_ascii=False, indent=2) + '\n')
    records = []
    for group in protocol['screen']:
        for model in eligible:
            assert protocol['backend_hashes'] == {p.name: sha(p) for p in (ROOT / 'backend').glob('*.py')}
            assert sha(ROOT / 'scripts/check_model_search_v24.py') == protocol['runner_sha256']
            assert all(sha(ROOT / p) == v for p, v in protocol['input_hashes'].items())
            before = set((ROOT / 'qa/v0.24/reports').glob('*.json'))
            command = [str(RUNTIME), 'scripts/check_model_search_v24.py',
                       '--suite', group['suite'], '--model-id', model, '--cases'] + group['cases']
            print('START_SCREEN', group['suite'], model, flush=True)
            began = time.monotonic()
            result = subprocess.run(command, cwd=ROOT)
            added = set((ROOT / 'qa/v0.24/reports').glob('*.json')) - before
            assert len(added) == 1
            report_path = next(iter(added))
            report = json.loads(report_path.read_text())
            assert [c['id'] for c in report['cases']] == group['expected_ids']
            assert report['source_hashes'] == protocol['backend_hashes']
            assert report['source_hashes_unchanged'] and report['network_denied']
            records.append({'suite': group['suite'], 'model': model, 'exit_code': result.returncode,
                            'elapsed': round(time.monotonic() - began, 3),
                            'report': str(report_path.relative_to(ROOT))})
            path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
            print('END_SCREEN', group['suite'], model, report['passed'], '/', report['total'], flush=True)


if __name__ == '__main__':
    main()
