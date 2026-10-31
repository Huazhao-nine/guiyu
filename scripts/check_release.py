"""Verify versioned archives and rebuild the source package in an isolated directory."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--skip-build',action='store_true',help='Recheck archives after documentation-only packaging changes.')
args=parser.parse_args()
report={'version':'0.22.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'checks':{},'archives':{}}
check=report['checks']
names=['Guiyu-0.22.0-source.zip','Guiyu-0.22.0-AppleSilicon-demo.zip','Guiyu-GCC-Cohort4-application-v0.22.0-update.zip']
for name in names:
    path=root/'releases'/name
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None, name
        members=archive.namelist()
        assert len(set(members))==len(members)
        for info in archive.infolist():
            parts=PurePosixPath(info.filename).parts
            assert parts[0]=='Guiyu' and '..' not in parts
            assert not stat.S_ISLNK(info.external_attr>>16)
            assert not any(p in ('.venv','.runtime','.build','__pycache__','GuiyuRuntime') for p in parts)
            assert '/qa/private/' not in info.filename
            assert not info.filename.endswith(('.safetensors','.onnx','.onnx_data','.jsonl','.pyc','.stderr','.sample.txt'))
            assert not any(p in ('history.json','pending-plan.json','preferences.json','workspace-index.sqlite3') for p in parts)
        manifest={key:digest for digest,key in (line.split('  ',1) for line in archive.read('Guiyu/SHA256SUMS').decode().splitlines())}
        assert set(manifest)==set(members)-{'Guiyu/SHA256SUMS'}
        for key,digest in manifest.items():assert hashlib.sha256(archive.read(key)).hexdigest()==digest
        if name.endswith('source.zip'):
            for key in manifest:
                relative=key.removeprefix('Guiyu/')
                assert archive.read(key)==(root/relative).read_bytes(), relative
            for relative in ['backend/office_agent.py','backend/personal_tools.py','backend/agent_control.py','tests/test_agent_control.py','docs/ADAPTIVE_AGENT_V0_7.md','Sources/Guiyu/PersonalViews.swift','Sources/Guiyu/PersonalStore.swift','tests/test_personal.py','docs/PERSONAL_AGENT_V0_6.md','fixtures/personal/01_梧桐空间.txt','tests/test_office.py','fixtures/statistics/费用明细.csv']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/fact_guard.py','backend/model_output.py','tests/test_fact_guard.py',
                             'tests/test_model_output.py','tests/test_quality_oracle.py',
                             'fixtures/quality/cases.json','scripts/benchmark_models.py','scripts/check_repair.py',
                             'docs/QUALITY_AND_MODELS_V0_8.md','docs/MODEL_SELECTION_V0_8.md',
                             'qa/v0.8-repair-integration-report.json','qa/v0.8-model-comparison-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['Sources/Guiyu/OfficeShowcase.swift','fixtures/office_showcase/tasks.json','docs/QUALITY_V0_9.md',
                             'docs/OFFICE_SHOWCASE_V0_9.md','scripts/check_daily_office.py','scripts/check_repair_matrix.py',
                             'qa/v0.9-daily-office-report.json','qa/v0.9-repair-matrix-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/privacy_filter.py','backend/money_subtotals.py','tests/test_privacy_filter.py','tests/test_composed_tools.py','tests/test_money_subtotals.py','Sources/Guiyu/PrivacyRedactionView.swift','Sources/Guiyu/ComposedShowcase.swift','scripts/check_composed.py','scripts/evaluate_privacy_guard.py','docs/PRIVACY_AND_COMPOSITION_V0_13.md','backend/general_tools.py','backend/general_assistant.py','tests/test_general_tools.py','tests/test_general_assistant.py',
                             'fixtures/general_tools/tasks.json','scripts/check_general_tools_agent.py','Sources/Guiyu/GeneralToolViews.swift','docs/LOCAL_TOOLS_V0_12.md']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/privacy_models.py','Sources/Guiyu/PrivacyScanWorker.swift','tests/test_privacy_models.py','tests/privacy_scan_checks.swift','scripts/check_privacy_components.py','docs/PRIVACY_COMPONENTS_V0_14.md','qa/v0.14-astrlink-guard-report.json','qa/v0.14-openai-privacy-filter-report.json','qa/v0.14-gui-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/share_agent.py','tests/test_share_agent.py','Sources/Guiyu/ShareDeliveryView.swift','Sources/Guiyu/ShareShowcase.swift','fixtures/share/workspace/客户跟进纪要.md','docs/SHARE_AGENT_V0_15.md','scripts/check_share_agent.py','qa/v0.15-share-agent-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/request_router.py','tests/test_request_router.py','fixtures/routing/tasks.json','scripts/check_routing.py','docs/GENERAL_CONVERSATION_V0_11.md']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/runtime_policy.py','Sources/Guiyu/DevicePolicy.swift','tests/test_runtime_policy.py',
                             'fixtures/general_agent/tasks.json','scripts/check_general_agent.py','docs/BASELINE_16GB_V0_10.md',
                             'qa/v0.10-qwen3.5-9b-general-agent-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/structured_tables.py','Sources/Guiyu/RosterShowcase.swift','Sources/Guiyu/MessageEditor.swift','tests/test_structured_tables.py','tests/message_editor_checks.swift','fixtures/roster/workspace/工作簿1.xlsx','scripts/check_roster_agent.py','docs/WORKBOOK_AGENT_V0_16.md','qa/v0.16-roster-agent-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/table_program.py','backend/workbook_data.py','backend/workbook_agent.py','backend/workbook_export.py','backend/workbook_writing.py',
                             'Sources/Guiyu/WorkbookShowcase.swift','tests/test_table_program.py','tests/test_workbook_agent.py',
                             'fixtures/workbook_general/tasks.json','fixtures/workbook_transfer/tasks.json',
                             'scripts/check_workbook_agent.py','scripts/check_workbook_transfer.py','docs/WORKBOOK_ENGINE_V0_17.md',
                             'qa/v0.17-qwen3.5-9b-workbook-report.json','qa/v0.17-qwen3.5-9b-transfer-report.json','qa/v0.17-native-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/workbook_flow.py','backend/table_semantics.py','backend/workbook_intent.py',
                             'tests/test_workbook_flow.py','scripts/check_workbook_flow.py','fixtures/workbook_adaptation/tasks.json',
                             'docs/WORKFLOW_V0_18.md','qa/v0.18-evaluation.json','qa/v0.18-native-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/workbook_revision.py','tests/test_workbook_revision.py','scripts/check_workbook_v19.py',
                             'fixtures/workbook_followups/tasks.json','fixtures/workbook_variants_v19/tasks.json',
                             'docs/WORKFLOW_V0_19.md','qa/v0.19-evaluation.json','qa/v0.19-native-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/workbook_edits.py','tests/test_workbook_recovery.py','scripts/check_workbook_v20.py',
                             'fixtures/workbook_variants_v20/tasks.json','docs/WORKFLOW_V0_20.md',
                             'qa/v0.20-evaluation.json','qa/v0.20-native-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['tests/test_workbook_units_v21.py','tests/test_workbook_compound_v21.py','scripts/check_workbook_v21.py','scripts/validate_workbook_v21_evidence.py','fixtures/workbook_variants_v21/tasks.json','fixtures/workbook_confirmation_v21/tasks.json','qa/v0.21/first-evaluation.json','qa/v0.21/confirmation-input-freeze.json','docs/WORKFLOW_V0_21.md','qa/v0.21-evaluation.json','qa/v0.21-native-report.json']:
                assert 'Guiyu/'+relative in manifest
            for relative in ['backend/structured_output.py','backend/workbook_schema.py','backend/workbook_requirements.py','backend/workbook_qualifiers.py','tests/test_structured_output.py','tests/test_workbook_schema_v22.py','tests/test_workbook_contracts_v22.py','scripts/check_workbook_v22.py','scripts/check_workbook_v22_plan_replay.py','scripts/validate_workbook_v22_evidence.py','fixtures/workbook_variants_v22/tasks.json','fixtures/workbook_confirmation_v22/tasks.json','fixtures/workbook_plan_replay_v22/cases.json','docs/WORKFLOW_V0_22.md','qa/v0.22/first-evaluation.json','qa/v0.22-evaluation.json','qa/v0.22-native-report.json']:
                assert 'Guiyu/'+relative in manifest
            text_members=[k for k in manifest if k.endswith(('.py','.swift','.md','.json','.sh','.command','.csv'))]
            machine_path=rb'/Users/[A-Za-z0-9][^/\s\x22\x27]*/'
            assert not any(re.search(machine_path,archive.read(k)) for k in text_members)
    report['archives'][name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,'crc_and_member_hashes':True}
check['archives_safe_and_complete']=True
check['source_matches_current_files']=True
check['no_model_runtime_or_user_history']=True
(root/'.build').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='v0.22-demo-replay-',dir=root/'.build') as temp:
    with zipfile.ZipFile(root/'releases/Guiyu-0.22.0-AppleSilicon-demo.zip') as archive:
        for entry in archive.infolist():
            if not entry.filename.startswith('Guiyu/dist/Guiyu.app/'):continue
            path=Path(archive.extract(entry,temp))
            path.chmod((entry.external_attr>>16)&0o777)
    distributed=Path(temp)/'Guiyu/dist/Guiyu.app'
    subprocess.run(['codesign','--verify','--deep','--strict',str(distributed)],check=True)
    subprocess.run([str(distributed/'Contents/MacOS/Guiyu'),'--privacy-probe'],check=True,capture_output=True,text=True)
check['demo_archive_signature_and_network_probe']=True
backend_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'backend').glob('*.py')}
report['model_task_validation']={}
evaluation=json.loads((root/'qa/v0.22-evaluation.json').read_text())
from validate_workbook_v22_evidence import SUITES,validate
assert set(evaluation['final_reports'])==set(SUITES)
for label,filename in evaluation['final_reports'].items():
    assert filename.startswith('qa/v0.22/reports/') and '..' not in Path(filename).parts
    measurement=json.loads((root/filename).read_text())
    validate(root,label,measurement)
    assert measurement['source_hashes']==backend_hashes and measurement['source_hashes_unchanged'] and measurement['network_denied']
    assert measurement['runner_sha256']==hashlib.sha256((root/'scripts/check_workbook_v22.py').read_bytes()).hexdigest()
    assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==v for f,v in measurement['suite_hashes'].items())
    report['model_task_validation'][label]={'passed':measurement['passed'],'total':measurement['total'],
        'failures':[c['id'] for c in measurement['cases'] if not c['passed']],
        'scope':measurement['limits']}
check['real_model_reports_match_current_backend']=True
first_phase=json.loads((root/'qa/v0.22/first-evaluation.json').read_text())
first_freeze=json.loads((root/'qa/v0.22/first-freeze.json').read_text())
assert first_phase['new_passed']==0 and first_phase['new_total']==4
assert first_freeze['runner_sha256']==hashlib.sha256((root/'qa/v0.22/first-runner-snapshot.txt').read_bytes()).hexdigest()
assert first_freeze['backend_hashes']=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'qa/v0.22/first-backend').glob('*.py')}
for label,filename in first_phase['final_reports'].items():
    old=json.loads((root/filename).read_text());validate(root,label,old)
    assert old['source_hashes']==first_freeze['backend_hashes'] and old['source_hashes_unchanged'] and old['network_denied']
check['first_frozen_failure_phase_preserved']=True
plan_replay=json.loads((root/'qa/v0.22/verified-plan-replay.json').read_text())
assert plan_replay['source_hashes']==backend_hashes and plan_replay['passed']==plan_replay['total']==32 and plan_replay['model_calls']==0
assert plan_replay['fixture_sha256']==hashlib.sha256((root/'fixtures/workbook_plan_replay_v22/cases.json').read_bytes()).hexdigest()
check['verified_old_plans_match_current_backend']=True

native_evidence=json.loads((root/'qa/v0.22-native-report.json').read_text())
assert native_evidence['source_hashes']==backend_hashes
if native_evidence.get('status')=='BLOCKED_MAC_LOCKED':
    assert native_evidence['planned_task_count']==5
    assert native_evidence['attempted_task_count']==native_evidence['completed_task_count']==0
    assert all(native_evidence['preflight_checks'].values()) and native_evidence['blocker']
    report['native_gui_acceptance']={'status':'BLOCKED_MAC_LOCKED','attempted_tasks':0,
        'note':'Manual unlock required. Executable/preflight and CLI document checks are separate; no GUI acceptance claim.'}
else:
    assert native_evidence['attempted_task_count']==native_evidence['planned_task_count']
    assert all(native_evidence['checks'].values())
    report['native_gui_acceptance']={'status':'EXECUTED','completed_tasks':native_evidence['completed_task_count'],
        'attempted_tasks':native_evidence['attempted_task_count']}
word_render=json.loads((root/'qa/v0.22/word-render-report.json').read_text())
assert len(word_render['documents'])==4 and word_render['total_pages']==4
assert all(c['exit_code']==0 and c['source_unchanged'] and c['all_pages_visually_inspected'] for c in word_render['documents'])
check['native_and_cli_evidence_scopes_recorded']=True

app=root/'dist/Guiyu.app'
subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
check['native_signature']=True
info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
assert info['CFBundleShortVersionString']=='0.22.0'
assert all(info.get(key) for key in ('NSDesktopFolderUsageDescription','NSDocumentsFolderUsageDescription','NSDownloadsFolderUsageDescription'))
check['workspace_folder_access_explanations']=True
for path in (root/'backend').glob('*.py'):
    assert path.read_bytes()==(app/'Contents/Resources'/path.name).read_bytes()
check['bundled_backend_matches_source']=True
probe=subprocess.run([str(app/'Contents/MacOS/Guiyu'),'--privacy-probe'],capture_output=True,text=True,check=True)
report['native_network_probe']=json.loads(probe.stdout)
check['native_network_denied']=True

legacy=root/'qa/delivery-checks.json'
if legacy.exists():
    for name,digest in json.loads(legacy.read_text()).get('release_sha256',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    check['v0_1_archives_preserved']=True
previous_version=root/'qa/v0.2-delivery-checks.json'
if previous_version.exists():
    for name,info in json.loads(previous_version.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_2_archives_preserved']=True

previous_v3=root/'qa/v0.3-delivery-checks.json'
if previous_v3.exists():
    for name,info in json.loads(previous_v3.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_3_archives_preserved']=True

previous_v4=root/'qa/v0.4-delivery-checks.json'
if previous_v4.exists():
    for name,info in json.loads(previous_v4.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_4_archives_preserved']=True
previous_v5=root/'qa/v0.5-delivery-checks.json'
if previous_v5.exists():
    for name,info in json.loads(previous_v5.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_5_archives_preserved']=True
previous_v6=root/'qa/v0.6-delivery-checks.json'
if previous_v6.exists():
    for name,info in json.loads(previous_v6.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_6_archives_preserved']=True
previous_v8=root/'qa/v0.8-delivery-checks.json'
if previous_v8.exists():
    for name,info in json.loads(previous_v8.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_8_archives_preserved']=True
previous_v9=root/'qa/v0.9-delivery-checks.json'
if previous_v9.exists():
    for name,info in json.loads(previous_v9.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_9_archives_preserved']=True
previous_v10=root/'qa/v0.10-delivery-checks.json'
if previous_v10.exists():
    for name,info in json.loads(previous_v10.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_10_archives_preserved']=True
previous_v11=root/'qa/v0.11-delivery-checks.json'
if previous_v11.exists():
    for name,info in json.loads(previous_v11.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_11_archives_preserved']=True
previous_v12=root/'qa/v0.12-delivery-checks.json'
if previous_v12.exists():
    for name,info in json.loads(previous_v12.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_12_archives_preserved']=True
previous_v13=root/'qa/v0.13-delivery-checks.json'
if previous_v13.exists():
    for name,info in json.loads(previous_v13.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_13_archives_preserved']=True
previous_v14=root/'qa/v0.14-delivery-checks.json'
if previous_v14.exists():
    for name,info in json.loads(previous_v14.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_14_archives_preserved']=True
previous_v15=root/'qa/v0.15-delivery-checks.json'
if previous_v15.exists():
    for name,info in json.loads(previous_v15.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_15_archives_preserved']=True
previous_v16=root/'qa/v0.16-delivery-checks.json'
if previous_v16.exists():
    for name,info in json.loads(previous_v16.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_16_archives_preserved']=True
previous_v17=root/'qa/v0.17-delivery-checks.json'
if previous_v17.exists():
    for name,info in json.loads(previous_v17.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_17_archives_preserved']=True
helper=app/'Contents/Helpers/GuiyuModelDownloader.app'
previous_v7=root/'qa/v0.7-delivery-checks.json'
if previous_v7.exists():
    for name,info in json.loads(previous_v7.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_7_archives_preserved']=True
assert helper.is_dir()
subprocess.run(['codesign','--verify','--strict',str(helper)],check=True)
assert (helper/'Contents/Resources/model-catalog.json').read_bytes()==(root/'packaging/model-catalog.json').read_bytes()
assert (app/'Contents/Resources/model-catalog.json').read_bytes()==(root/'packaging/model-catalog.json').read_bytes()
check['download_helper_signed_and_catalog_pinned']=True
catalog=json.loads((root/'packaging/model-catalog.json').read_text())
assert {m['id'] for m in catalog}=={'qwen3.5-9b','qwen3-4b','bge-small-zh-v1.5','astrlink-guard','openai-privacy-filter'}
assert [m['id'] for m in catalog if m.get('recommended')]==['qwen3.5-9b']
check['two_chat_choices_and_automatic_retrieval_component']=True
sample_sources=root/'fixtures/office_showcase/workspace'
sample_bundle=app/'Contents/Resources/office-showcase'
expected_samples={str(p.relative_to(sample_sources)):p for p in sample_sources.rglob('*') if p.is_file()}
assert len(expected_samples)==18
assert {str(p.relative_to(sample_bundle)) for p in sample_bundle.rglob('*') if p.is_file()}==set(expected_samples)
for relative,path in expected_samples.items():assert path.read_bytes()==(sample_bundle/relative).read_bytes()
assert (root/'fixtures/office_showcase/tasks.json').read_bytes()==(app/'Contents/Resources/office-showcase-tasks.json').read_bytes()
check['bundled_office_examples_match_frozen_sources']=True
composed_sources=root/'fixtures/composed/workspace'
composed_bundle=app/'Contents/Resources/composed-showcase'
assert len(list(composed_sources.iterdir()))==2
assert {p.name for p in composed_bundle.iterdir()}=={p.name for p in composed_sources.iterdir()}
for source in composed_sources.iterdir():assert source.read_bytes()==(composed_bundle/source.name).read_bytes()
check['bundled_composed_examples_match_frozen_sources']=True
workbook_sources=root/'fixtures/workbook_general/workspace'
workbook_bundle=app/'Contents/Resources/workbook-showcase'
assert len(list(workbook_sources.iterdir()))==4
assert {p.name for p in workbook_bundle.iterdir()}=={p.name for p in workbook_sources.iterdir()}
for source in workbook_sources.iterdir():assert source.read_bytes()==(workbook_bundle/source.name).read_bytes()
check['bundled_workbooks_match_frozen_sources']=True
redaction=subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,'-I','-B',str(app/'Contents/Resources/privacy_filter.py')],input=json.dumps({'text':'邮箱a@example.com，预算1280元。'}),capture_output=True,text=True,check=True,timeout=10)
redacted=json.loads(redaction.stdout)
assert redacted['count']==1 and 'a@example.com' not in redacted['text'] and '1280元' in redacted['text'] and redacted['saved'] is False
check['bundled_rule_redaction_without_model_dependency']=True
assert not any(app.rglob('*.pyc'))
subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
check['rule_preview_preserves_bundle_signature']=True

previous_v18=root/'qa/v0.18-delivery-checks.json'
if previous_v18.exists():
    for name,info in json.loads(previous_v18.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_18_archives_preserved']=True

previous_v19=root/'qa/v0.19-delivery-checks.json'
if previous_v19.exists():
    for name,info in json.loads(previous_v19.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_19_archives_preserved']=True

previous_v20=root/'qa/v0.20-delivery-checks.json'
if previous_v20.exists():
    for name,info in json.loads(previous_v20.read_text()).get('archives',{}).items():
        path=root/'releases'/name
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_20_archives_preserved']=True

previous_v21=root/'qa/v0.21-delivery-checks.json'
if previous_v21.exists():
    old=json.loads(previous_v21.read_text())
    for name,info in old['archives'].items():
        path=root/'releases'/name
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    check['v0_21_archives_preserved']=True

if not args.skip_build:
    (root/'.build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='v0.22-source-rebuild-',dir=root/'.build') as temp:
        with zipfile.ZipFile(root/'releases/Guiyu-0.22.0-source.zip') as archive:archive.extractall(temp)
        project=Path(temp)/'Guiyu'
        subprocess.run(['zsh','scripts/build.sh'],cwd=project,check=True,capture_output=True,text=True)
        rebuilt=project/'dist/Guiyu.app'
        assert plistlib.loads((rebuilt/'Contents/Info.plist').read_bytes())['CFBundleShortVersionString']=='0.22.0'
        subprocess.run(['codesign','--verify','--deep','--strict',str(rebuilt)],check=True)
        subprocess.run([str(rebuilt/'Contents/MacOS/Guiyu'),'--privacy-probe'],check=True,capture_output=True,text=True)
        for source in (project/'backend').glob('*.py'):
            assert source.read_bytes()==(rebuilt/'Contents/Resources'/source.name).read_bytes()
        subprocess.run([sys.executable,'scripts/check_workbook_v22_plan_replay.py'],cwd=project,check=True,capture_output=True,text=True)
    check['source_archive_plan_replay']=True
    check['source_archive_clean_rebuild']=True
else:
    previous=json.loads((root/'qa/v0.22-delivery-checks.json').read_text())
    current_hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('Sources','backend') for p in (root/folder).rglob('*') if p.suffix in ('.swift','.py')}
    assert previous['source_hashes']==current_hashes
    assert previous['checks']['source_archive_clean_rebuild']
    check['source_archive_clean_rebuild']=True
    report['rebuild_note']='Reused successful clean rebuild; all Swift and Python source hashes unchanged.'

report['source_hashes']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('Sources','backend') for p in (root/folder).rglob('*') if p.suffix in ('.swift','.py')}
report['status']=('V0_22_CLI_DELIVERY_VERIFIED_GUI_BLOCKED_APPLICATION_NOT_SUBMITTED'
                  if native_evidence.get('status')=='BLOCKED_MAC_LOCKED'
                  else 'V0_22_LOCAL_DELIVERY_VERIFIED_APPLICATION_NOT_SUBMITTED')
(root/'qa/v0.22-delivery-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':report['status'],'checks':check},ensure_ascii=False,indent=2))
