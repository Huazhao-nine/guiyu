"""Run frozen paired model tasks serially without modifying the application."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path.home() / 'Library/Application Support/GuiyuRuntime/python/bin/python'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = json.loads((ROOT / 'qa/v0.23/protocol.json').read_text())
    records_path = ROOT / 'qa/v0.23/matrix-records.json'
    assert not records_path.exists(), 'Keep earlier paired measurements; do not overwrite.'
    records = []
    for group in protocol['groups']:
        for model in protocol['models']:
            assert protocol['backend_hashes'] == {
                p.name: digest(p) for p in (ROOT / 'backend').glob('*.py')}
            assert digest(ROOT / 'scripts/check_model_comparison_v23.py') == protocol['runner_sha256']
            assert all(digest(ROOT / p) == sha for p, sha in protocol['input_hashes'].items())
            before = set((ROOT / 'qa/v0.23/reports').glob('*.json'))
            command = [str(RUNTIME), 'scripts/check_model_comparison_v23.py',
                       '--suite', group['suite'], '--model-id', model]
            if group['cases']:
                command += ['--cases'] + group['cases']
            print('START', group['suite'], model, flush=True)
            started = time.monotonic()
            run = subprocess.run(command, cwd=ROOT)
            added = set((ROOT / 'qa/v0.23/reports').glob('*.json')) - before
            assert len(added) == 1, 'Each run must retain one separate report.'
            report_path = next(iter(added))
            report = json.loads(report_path.read_text())
            assert [c['id'] for c in report['cases']] == group['expected_ids']
            assert report['source_hashes'] == protocol['backend_hashes']
            assert report['source_hashes_unchanged'] and report['network_denied']
            records.append({'suite': group['suite'], 'model': model,
                            'report': str(report_path.relative_to(ROOT)),
                            'exit_code': run.returncode,
                            'elapsed': round(time.monotonic() - started, 3),
                            'finished_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()})
            records_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
            print('END', group['suite'], model, report['passed'], '/', report['total'], flush=True)


if __name__ == '__main__':
    main()
