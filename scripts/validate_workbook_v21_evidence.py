"""Validate complete declared v0.21 measurement scope, independently of scores."""
import hashlib
import json
from pathlib import Path

SUITES = ('regression', 'known', 'adaptation', 'followups', 'variants', 'prior_new', 'fresh', 'confirmation')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def scope(root, label):
    groups = {
        'regression': ['workbook_general'],
        'known': ['workbook_general', 'workbook_transfer'],
        'adaptation': ['workbook_adaptation'],
        'followups': ['workbook_adaptation'],
        'variants': ['workbook_variants_v19'],
        'prior_new': ['workbook_variants_v20'],
        'fresh': ['workbook_variants_v21'],
        'confirmation': ['workbook_confirmation_v21'],
    }[label]
    folders = [root / 'fixtures' / group for group in groups]
    task_paths = [folder / 'tasks.json' for folder in folders]
    if label == 'followups':
        task_paths.append(root / 'fixtures/workbook_followups/tasks.json')
        tasks = json.loads(task_paths[-1].read_text())['cases']
    else:
        tasks = [case for path in task_paths for case in json.loads(path.read_text())['cases']]
    if label == 'known':
        # The other two default known cases are already in regression.
        tasks = [case for case in tasks if case['id'] in ('renamed_units', 'chinese_goal_english_fields')]
    fixtures = {path.name: digest(path) for folder in folders for path in (folder / 'workspace').iterdir()
                if path.is_file() and path.suffix.lower() in ('.csv', '.xlsx')}
    return [case['id'] for case in tasks], fixtures, {str(path.relative_to(root)): digest(path) for path in task_paths}

def validate(root, label, report):
    assert label in SUITES and report['suite'] == label
    ids, fixtures, task_hashes = scope(root, label)
    assert [case['id'] for case in report['cases']] == ids, (label, 'incomplete or reordered case set')
    assert report['total'] == len(ids)
    assert report['passed'] == sum(bool(case['passed']) for case in report['cases'])
    assert report['fixture_hashes'] == fixtures, (label, 'fixture mismatch')
    assert report['suite_hashes'] == task_hashes, (label, 'task mismatch')
    assert not report.get('interrupted') and not report.get('superseded_snapshot')
    return True
