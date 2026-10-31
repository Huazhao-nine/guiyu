"""Verify the observed candidate month graph on CPU; never change Agent scores."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
import worker as core
from workbook_data import inspect_documents, prepare_table
from workbook_flow import TableFlow
from check_workbook_v22_plan_replay import action
from check_model_comparison_v23 import equal_rows


def main():
    observed = json.loads((ROOT / 'qa/v0.23/intermediate-month-replay.json').read_text())
    assert not observed['counts_as_completed_agent_task']
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert observed['source_hashes'] == {p.name: digest(p) for p in (ROOT / 'backend').glob('*.py')}
    source_path = ROOT / observed['source_fixture']
    assert digest(source_path) == observed['source_fixture_sha256']
    source = prepare_table(inspect_documents([{'path': str(source_path), 'name': source_path.name}], core),
                           observed['selection']['tables'])
    flow = TableFlow(source, observed['goal'])
    mapping = {'V0': 'V0', 'P0': 'P0'}
    for step in observed['graph']:
        event = flow.apply(dict(action(step['operation']), input=mapping[step['input']]))
        mapping[step['id']] = event['view']
    finish = deepcopy(observed['finish'])
    finish['result'] = mapping[finish['result']]
    finish['summaries'] = [mapping[v] for v in finish.get('summaries', [])]
    result = flow.finish(finish, observed['contract'])
    assert equal_rows(result['rows'], observed['expected_rows'])
    assert result['columns'] == observed['columns'] and result['rows'] == observed['rows']
    assert digest(source_path) == observed['source_fixture_sha256']
    print(json.dumps({'intermediate_rows_verified': True, 'model_calls': 0,
                      'counts_as_completed_agent_task': False, 'rows': result['rows']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
