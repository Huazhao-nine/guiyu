"""Create local review packages from an explicit allowlist, without model/data caches."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
release = root/'releases'
release.mkdir(exist_ok=True)
version = '0.22.0'
qa = ['qa/guiyu-home.png','qa/guiyu-privacy.png','qa/guiyu-summary.png',
      'qa/guiyu-v0.2-home.png','qa/guiyu-v0.2-plan.png','qa/guiyu-v0.2-result.png',
      'qa/guiyu-v0.2-statistics.png','qa/guiyu-v0.2-paused.png',
      'qa/integration-report.json','qa/office-integration-report.json',
      'qa/office-gui-report.json','qa/v0.2-direct-integration-report.json',
      'qa/guiyu-v0.3-home.png','qa/guiyu-v0.3-filters.png','qa/guiyu-v0.3-followup.png',
      'qa/guiyu-v0.3-search.png','qa/guiyu-v0.3-models.png',
      'qa/v0.3-query-integration-report.json','qa/v0.3-office-integration-report.json',
      'qa/v0.3-direct-integration-report.json','qa/v0.3-gui-report.json',
      'qa/guiyu-v0.4-workspace.png','qa/guiyu-v0.4-search.png','qa/guiyu-v0.4-models.png',
      'qa/guiyu-v0.4-switcher.png','qa/guiyu-v0.4-generation.png',
      'qa/v0.4-query-integration-report.json','qa/v0.4-office-integration-report.json',
      'qa/v0.4-direct-integration-report.json','qa/v0.4-gui-report.json',
      'qa/v0.4-model-download-report.json','qa/v0.4-native-workspace-report.json',
      'qa/v0.4-download-control-report.json',
      'qa/guiyu-v0.5-workspace.png','qa/guiyu-v0.5-semantic.png','qa/guiyu-v0.5-updated.png',
      'qa/v0.5-workspace-integration-report.json','qa/v0.5-file-watcher-report.json',
      'qa/v0.5-gui-report.json','qa/v0.5-query-integration-report.json',
      'qa/v0.5-office-integration-report.json','qa/v0.5-direct-integration-report.json',
      'qa/guiyu-v0.6-products.png','qa/guiyu-v0.6-compare.png','qa/guiyu-v0.6-preferences.png',
      'qa/v0.6-personal-integration-report.json','qa/v0.6-gui-report.json',
      'qa/v0.6-query-integration-report.json','qa/v0.6-office-integration-report.json',
      'qa/v0.6-workspace-integration-report.json','qa/v0.6-direct-integration-report.json',
      'qa/guiyu-v0.7-plan.png','qa/guiyu-v0.7-result.png','qa/guiyu-v0.7-models.png','qa/guiyu-v0.7-needs-input.png',
      'qa/guiyu-v0.7-activity.png','qa/guiyu-v0.7-preview.png',
      'qa/v0.7-adaptive-integration-report.json','qa/v0.7-gui-report.json',
      'qa/v0.7-model-catalog-report.json','qa/v0.7-query-integration-report.json',
      'qa/v0.7-office-integration-report.json','qa/v0.7-workspace-integration-report.json',
      'qa/v0.7-personal-integration-report.json','qa/v0.7-direct-integration-report.json']
qa += ['qa/guiyu-v0.8-workflow.png','qa/guiyu-v0.8-models.png','qa/guiyu-v0.8-preview.png','qa/guiyu-v0.8-constraints.png',
       'qa/v0.8-gui-report.json','qa/v0.8-model-catalog-report.json','qa/v0.8-model-comparison-protocol.json',
       'qa/v0.8-model-comparison-report.json','qa/v0.8-repair-integration-report.json',
       'qa/v0.8-model-qwen3-4b.json','qa/v0.8-model-qwen3.5-9b.json',
       'qa/v0.8-model-gemma4-e4b.json','qa/v0.8-model-gpt-oss-20b.json',
       'qa/v0.8-adaptive-qwen3-4b-report.json','qa/v0.8-adaptive-qwen3.5-9b-report.json',
       'qa/v0.8-adaptive-gpt-oss-20b-report.json','qa/v0.8-query-integration-report.json',
       'qa/v0.8-office-integration-report.json','qa/v0.8-workspace-integration-report.json',
       'qa/v0.8-personal-integration-report.json','qa/v0.8-direct-integration-report.json']

qa += ['qa/guiyu-v0.9-showcase.png','qa/guiyu-v0.9-statistics.png','qa/guiyu-v0.9-writing.png','qa/guiyu-v0.9-preview.png',
       'qa/v0.9-gui-report.json','qa/v0.9-date-boundary-daily-office-report.json','qa/v0.9-statistics-daily-office-report.json','qa/v0.9-daily-office-report.json','qa/v0.8-baseline-daily-office-report.json',
       'qa/v0.9-repair-matrix-report.json','qa/v0.8-baseline-repair-matrix-report.json','qa/v0.9-quality-comparison.json',
       'qa/v0.9-direct-integration-report.json','qa/v0.9-personal-integration-report.json','qa/v0.9-query-integration-report.json',
       'qa/v0.9-office-integration-report.json','qa/v0.9-workspace-integration-report.json','qa/v0.9-adaptive-gpt-oss-20b-report.json']

qa += ['qa/guiyu-v0.10-models.png','qa/guiyu-v0.10-delivery.png','qa/v0.10-gui-report.json',
       'qa/v0.10-qwen3.5-9b-daily-office-report.json','qa/v0.10-qwen3-4b-daily-office-report.json',
       'qa/v0.10-qwen3.5-9b-general-agent-report.json','qa/v0.10-native-runtime-report.json',
       'qa/v0.10-adaptive-qwen3.5-9b-report.json','qa/v0.10-final-qwen3.5-9b-general-agent-report.json',
       'qa/v0.10-followup-qwen3.5-9b-daily-office-report.json','qa/v0.10-final-qwen3.5-9b-daily-office-report.json']

qa += ['qa/guiyu-v0.11-conversation.png','qa/guiyu-v0.11-mixed.png','qa/v0.11-gui-report.json',
       'qa/v0.11-qwen3.5-9b-routing-report.json','qa/v0.11-qwen3-4b-routing-report.json']

qa += ['qa/guiyu-v0.12-calculation.png','qa/guiyu-v0.12-calendar.png','qa/v0.12-gui-report.json',
       'qa/v0.12-qwen3.5-9b-general-tools-report.json','qa/v0.12-qwen3-4b-general-tools-report.json',
       'qa/v0.12-initial-qwen3.5-9b-general-tools-report.json',
       'qa/v0.12-prefinal-qwen3.5-9b-general-tools-report.json','qa/v0.12-prefinal-qwen3-4b-general-tools-report.json']

qa += ['qa/guiyu-v0.13-privacy.png','qa/guiyu-v0.13-composed.png','qa/v0.13-gui-report.json',
       'qa/v0.13-composed-report.json','qa/v0.13-initial-composed-report.json','qa/v0.13-prefinal-composed-report.json','qa/v0.13-intermediate-composed-report.json','qa/v0.13-before-subtotals-composed-report.json','qa/v0.13-privacy-guard-evaluation.json']

qa += ['qa/guiyu-v0.14-privacy.png','qa/guiyu-v0.14-autonomous.png',
       'qa/v0.14-gui-report.json','qa/v0.14-astrlink-guard-report.json','qa/v0.14-openai-privacy-filter-report.json']

qa += ['qa/v0.15-share-agent-report.json','qa/v0.15-initial-share-agent-report.json',
       'qa/v0.15-prefinal-share-agent-report.json','qa/v0.15-before-editorial-repair-report.json',
       'qa/v0.15-before-budget-label-report.json','qa/v0.15-native-report.json']

qa += ['qa/v0.16-roster-agent-report.json','qa/v0.16-initial-roster-agent-report.json',
       'qa/v0.16-before-delivery-roster-agent-report.json','qa/v0.16-before-provenance-roster-agent-report.json','qa/v0.16-before-planner-roster-agent-report.json','qa/v0.16-before-condition-review-roster-agent-report.json','qa/v0.16-native-report.json',
       'qa/guiyu-v0.16-roster.png','qa/guiyu-v0.16-followup.png','qa/guiyu-v0.16-columns.png']

qa += ['qa/v0.17-qwen3.5-9b-workbook-report.json','qa/v0.17-qwen3.5-9b-transfer-report.json',
       'qa/v0.17-initial-qwen3.5-9b-workbook-report.json','qa/v0.17-before-repair-qwen3.5-9b-workbook-report.json',
       'qa/v0.17-before-summary-qwen3.5-9b-workbook-report.json','qa/v0.17-before-output-normalization-workbook-report.json',
       'qa/v0.17-before-fact-writer-probe-report.json','qa/v0.17-qwen3.5-9b-workbook-probe-report.json',
       'qa/v0.17-before-projection-workbook-report.json','qa/v0.17-before-binding-validation-workbook-report.json',
       'qa/v0.17-before-preprocessing-review-workbook-report.json',
       'qa/v0.17-before-indexed-repair-workbook-report.json',
       'qa/v0.17-before-alternative-plan-workbook-report.json',
       'qa/v0.17-native-report.json','qa/guiyu-v0.17-workbooks.png',
       'qa/guiyu-v0.17-result.png','qa/guiyu-v0.17-followup.png']

qa += ['qa/v0.18','qa/v0.18-evaluation.json','qa/v0.18-native-report.json',
       'qa/guiyu-v0.18-result.png','qa/guiyu-v0.18-followup.png','qa/guiyu-v0.18-followup-failure.png']

qa += ['qa/v0.19','qa/v0.19-evaluation.json','qa/v0.19-native-report.json',
       'qa/guiyu-v0.19-result.png','qa/guiyu-v0.19-followup.png','qa/guiyu-v0.19-new-workbook-failure.png']

qa += ['qa/v0.20','qa/v0.20-evaluation.json','qa/v0.20-native-report.json',
       'qa/guiyu-v0.20-result.png','qa/guiyu-v0.20-followup.png','qa/guiyu-v0.20-dates.png']

qa += ['qa/v0.21','qa/v0.21-evaluation.json','qa/v0.21-native-report.json','qa/guiyu-v0.21-workbook.png','qa/guiyu-v0.21-followup.png']
qa += ['qa/v0.22','qa/v0.22-evaluation.json','qa/v0.22-native-report.json','qa/guiyu-v0.22-word-preview.png']
native_v22 = json.loads((root/'qa/v0.22-native-report.json').read_text())
if native_v22.get('status') == 'BLOCKED_MAC_LOCKED':
    assert native_v22['attempted_task_count'] == 0 and native_v22['completed_task_count'] == 0
else:
    qa += ['qa/guiyu-v0.22-workbook.png','qa/guiyu-v0.22-followup.png']

def gather(items):
    result = []
    for name in items:
        path = root/name
        if not path.exists():raise FileNotFoundError(f'Missing release input: {name}')
        candidates = path.rglob('*') if path.is_dir() else [path]
        result.extend(p for p in candidates if p.is_file() and not p.is_symlink()
                      and '__pycache__' not in p.parts and p.name != '.DS_Store')
    return sorted(set(result))

source = gather(['README.md','LICENSE','.gitignore','requirements.lock',
                 '准备归屿.command','打开归屿.command','Sources','backend','tests',
                 'scripts','fixtures','assets','packaging','docs',
                 *qa,*[str(p.relative_to(root)) for p in (root/'grant').glob('*.md')],
                 'research/2026-10-20-gcc-cohort4/sources.csv'])
grant = gather(['grant','docs',*qa,
                'research/2026-10-20-gcc-cohort4/sources.csv'])

def package(name, files):
    target = release/name
    entries = [(p, 'Guiyu/'+p.relative_to(root).as_posix()) for p in files]
    manifest = '\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+key for p,key in entries)+'\n'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for path,key in entries:
            archive.write(path,key)
        archive.writestr('Guiyu/SHA256SUMS',manifest)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for line in archive.read('Guiyu/SHA256SUMS').decode().splitlines():
            expected,key = line.split('  ',1)
            assert hashlib.sha256(archive.read(key)).hexdigest() == expected
        assert not any('/.venv/' in k or '/.runtime/' in k or '/qa/private/' in k
                       or k.endswith('.safetensors') for k in archive.namelist())
    print(f'{name}: {len(entries)} files, {target.stat().st_size} bytes, CRC and hashes passed')

package(f'Guiyu-{version}-source.zip',source)
package(f'Guiyu-{version}-AppleSilicon-demo.zip',sorted(set(source+grant+gather(['dist/Guiyu.app']))))
package(f'Guiyu-GCC-Cohort4-application-v{version}-update.zip',grant)
checksums = '\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name
                      for p in sorted(release.glob('*.zip')))+'\n'
(release/'SHA256SUMS').write_text(checksums)
