"""Complete18 known goals and4 pre-frozen new goals for an admitted candidate."""
import argparse
from datetime import datetime
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-id', required=True)
    args = parser.parse_args()
    summaries = [ROOT / 'qa/v0.24/adaptation/screen-summary.json']
    source_path = next(p for p in summaries if p.exists() and json.loads(p.read_text())['selected'] == args.model_id)
    screen = json.loads(source_path.read_text())
    old = json.loads((ROOT / 'qa/v0.23/protocol.json').read_text())
    extension = source_path.name.startswith('extension-')
    base_path = ROOT / 'qa/v0.24/adaptation/protocol.json'
    base = json.loads(base_path.read_text())
    runner = base.get('runner', 'scripts/check_model_search_v24.py')
    protocol_path, records_path = ROOT / 'qa/v0.24/adaptation/confirmation-protocol.json', ROOT / 'qa/v0.24/adaptation/confirmation-records.json'
    assert not protocol_path.exists() and not records_path.exists(), 'Preserve the first confirmation phase.'
    novel_path = ROOT / 'qa/v0.24/new-input-freeze.json'
    novel = json.loads(novel_path.read_text())
    assert all(sha(ROOT / p) == h for p, h in novel['hashes'].items())
    groups = old['groups'] + [{'suite': 'novel', 'cases': [], 'expected_ids':
                               [c['id'] for c in json.loads((ROOT / 'fixtures/workbook_model_search_v24/tasks.json').read_text())['cases']]}]
    protocol = {'time': datetime.now().astimezone().isoformat(), 'model': args.model_id,
                'selected_by': str(source_path.relative_to(ROOT)), 'selection_sha256': sha(source_path),
                'backend_hashes': base['backend_hashes'], 'runner': runner, 'runner_sha256': sha(ROOT / runner),
                'input_hashes': old['input_hashes'] | novel['hashes'], 'groups': groups,
                'known_goals': 18, 'new_goals': 4, 'model_revision': base['candidate_revisions'][args.model_id],
                'reserved_new_freeze_sha256': sha(novel_path),
                'reuse': 'Reuse the exact completed variants2 and fresh1 screen reports. Reexecute unseen full4 and followups full5 to retain their complete conversation parents; regression6 and novel4 run once. Repeated screen cases are never counted twice.',
                'method': 'Paired-screen selected model on the v0.24 contract-context adaptation; fixed common8192/1800 windows; structured temperature0; same local nonthinking template. All inference serial in deny-network sandbox. The six-goal9B comparison is freshly paired on this adapted backend. Historical v23 full18 are a separate backend scope. No candidate tuning on novel outputs.'}
    assert sha(ROOT / runner) == base['runner_sha256']
    assert protocol['backend_hashes'] == {p.name: sha(p) for p in (ROOT / 'backend').glob('*.py')}
    protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + '\n')
    records = []
    for group in groups:
        assert all(sha(ROOT / p) == h for p, h in protocol['input_hashes'].items())
        assert protocol['backend_hashes'] == {p.name: sha(p) for p in (ROOT / 'backend').glob('*.py')}
        if group['suite'] in ('variants', 'fresh'):
            record = next(r for r in screen['reports'] if r['model'] == args.model_id and r['suite'] == group['suite'])
            record = dict(record, reused_screen=True)
        else:
            before = set((ROOT / 'qa/v0.24/adaptation/reports').glob('*.json'))
            command = [str(RUNTIME), runner, '--suite', group['suite'], '--model-id', args.model_id]
            if group['cases']:
                command += ['--cases'] + group['cases']
            print('START_CONFIRMATION', group['suite'], args.model_id, flush=True)
            start = time.monotonic()
            result = subprocess.run(command, cwd=ROOT)
            added = set((ROOT / 'qa/v0.24/adaptation/reports').glob('*.json')) - before
            assert len(added) == 1
            report_path = next(iter(added))
            record = {'suite': group['suite'], 'model': args.model_id, 'report': str(report_path.relative_to(ROOT)),
                      'exit_code': result.returncode, 'elapsed': round(time.monotonic() - start, 3), 'reused_screen': False}
        report = json.loads((ROOT / record['report']).read_text())
        assert [c['id'] for c in report['cases']] == group['expected_ids']
        assert report['source_hashes'] == protocol['backend_hashes']
        assert report['runner_sha256'] == protocol['runner_sha256']
        assert report['source_hashes_unchanged'] and report['network_denied']
        records.append(record)
        records_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
        print('END_CONFIRMATION', group['suite'], report['passed'], '/', report['total'], flush=True)


if __name__ == '__main__':
    main()
