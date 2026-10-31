"""Package the model study, without models, runtime, history or private traces."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    summary = json.loads((ROOT / 'qa/v0.23/model-comparison.json').read_text())
    assert all(v['total'] == 18 for v in summary['models'].values())
    probes = json.loads((ROOT / 'qa/v0.23/thinking-probe-report.json').read_text())
    assert set(probes['modes']) == {'disabled', 'native-low'}
    assert probes['source_hashes_unchanged'] and probes['network_denied']
    items = ['backend', 'fixtures', 'requirements.lock', 'LICENSE',
             'docs/BASELINE_32GB_V0_23.md', 'docs/MODEL_COMPARISON_REPRODUCE_V0_23.md',
             'qa/v0.23', 'scripts/check_model_comparison_v23.py',
             'scripts/run_model_comparison_v23.py', 'scripts/collect_model_comparison_v23.py',
             'scripts/check_reasoning_probes_v23.py', 'scripts/replay_model_intermediate_v23.py',
             'scripts/audit_model_intermediates_v23.py',
             'scripts/check_workbook_v22.py', 'scripts/check_workbook_v22_plan_replay.py',
             'scripts/validate_workbook_v22_evidence.py', 'scripts/package_model_comparison_v23.py']
    files = []
    for item in items:
        path = ROOT / item
        assert path.exists(), item
        for p in path.rglob('*') if path.is_dir() else [path]:
            if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or p.name == '.DS_Store':
                continue
            assert not p.name.endswith(('.safetensors', '.onnx', '.onnx_data', '.pyc', '.jsonl'))
            assert '/qa/private/' not in str(p)
            if p.suffix in ('.py', '.json', '.md', '.lock', '.csv'):
                assert not re.search(rb'/Users/[A-Za-z0-9][^/\s\x22\x27]*/', p.read_bytes()), str(p)
            files.append(p)
    entries = {str(p.relative_to(ROOT)): p.read_bytes() for p in sorted(set(files))}
    entries['README.md'] = (ROOT / 'docs/MODEL_COMPARISON_REPRODUCE_V0_23.md').read_bytes()
    prefix = 'Guiyu-32GB-model-comparison/'
    manifest = '\n'.join(hashlib.sha256(data).hexdigest() + '  ' + prefix + name
                         for name, data in sorted(entries.items())) + '\n'
    target = ROOT / 'releases/Guiyu-32GB-model-comparison-20261030.zip'
    assert not target.exists(), 'Preserving existing study bundle.'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            archive.writestr(prefix + name, data)
        archive.writestr(prefix + 'SHA256SUMS', manifest)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for line in manifest.splitlines():
            digest, name = line.split('  ', 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    previous = json.loads((ROOT / 'qa/v0.22-delivery-checks.json').read_text())
    for name, info in previous['archives'].items():
        assert hashlib.sha256((ROOT / 'releases' / name).read_bytes()).hexdigest() == info['sha256']
    record = {'path': str(target.relative_to(ROOT)), 'bytes': target.stat().st_size,
              'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'member_count': len(entries),
              'crc_and_hashes_verified': True, 'no_models_runtime_history_or_private_traces': True,
              'v0_22_archives_preserved': True, 'is_application_release': False}
    (ROOT / 'qa/v0.23-study-package.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
