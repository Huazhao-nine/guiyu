"""Serial real-model QA for bounded local tools, using fictional prompts only.

Runs are opt-in: this module never loads a model when imported. The entry point
reexecutes under macOS deny-network sandbox, uses installed models only, and
preserves each run's traces and failure reports in a distinct private directory.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import uuid
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / 'fixtures/general_tools/tasks.json'
NUMBER = re.compile(r'(?<![0-9A-Za-z_.])[-+]?\d+(?:\.\d+)?(?![0-9A-Za-z_.])')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalized(text):
    text = str(text).replace('％', '%').replace('，', ',')
    text = re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))', '', text)
    return re.sub(r'[\s*`]', '', text)


def numeric_text(text):
    """Remove display markup without joining numbers across token boundaries."""
    text = str(text).replace('％', '%').replace('，', ',')
    text = re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))', '', text)
    return re.sub(r'[*`_]', ' ', text)


def decimal_key(value):
    try:
        number = Decimal(str(value))
        return number.normalize() if number.is_finite() else None
    except InvalidOperation:
        return None


def literal_values(text):
    return {key for match in NUMBER.findall(numeric_text(text)) if (key := decimal_key(match)) is not None}


def tool_data(call):
    result = call.get('result')
    return result.get('data', {}) if isinstance(result, dict) else {}


def expected_call(call, expected):
    alternatives = expected.get('data_any', [expected.get('data', {})])
    return (call.get('state') == 'completed' and call.get('tool') == expected['tool']
            and any(all(tool_data(call).get(key) == value for key, value in data.items()) for data in alternatives))


def contains_fact(text, token):
    compact = normalized(token)
    if re.fullmatch(r'[-+]?\d+(?:\.\d+)?', compact):
        return decimal_key(compact) in literal_values(text)
    if re.fullmatch(r'[-+]?\d+(?:\.\d+)?%', compact):
        target = decimal_key(compact[:-1])
        return any(decimal_key(match) == target for match in re.findall(r'(?<![\d.])([-+]?\d+(?:\.\d+)?)\s*%', numeric_text(text)))
    return compact in normalized(text)


def forbidden_assertion(text, token):
    """A prohibition or denial does not assert that an external action occurred."""
    text = re.sub(r'[*`]', '', str(text))
    for match in re.finditer(re.escape(normalized(token)), text, re.I):
        prefix = re.split(r'[。；;！？!?\n]', text[max(0, match.start() - 24):match.start()])[-1]
        if not re.search(r'不(?:表示|代表|意味着|等于|能|要|应|会|可|虚构|是|可声称)|并非|没有|未曾|尚未|不得|禁止', prefix):
            return True
    return False


def select_cases(cases, requested):
    by_id = {case['id']: case for case in cases}
    if len(by_id) != len(cases):
        raise ValueError('Fixture case IDs must be unique.')
    wanted = set(by_id) if not requested else set(requested)
    unknown = wanted - set(by_id)
    if unknown:
        raise ValueError('Unknown case IDs: ' + ', '.join(sorted(unknown)))
    selected = set(wanted)
    for identifier in list(wanted):
        visited = set()
        current = by_id[identifier]
        while current.get('after'):
            previous = current['after']
            if previous in visited or previous not in by_id:
                raise ValueError('Fixture dependency cycle or missing case: ' + previous)
            visited.add(previous)
            selected.add(previous)
            current = by_id[previous]
    return [case for case in cases if case['id'] in selected], wanted


def write_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o600)


def public_value(value):
    """Publish repository-relative paths; private copies retain the raw records."""
    if isinstance(value, dict):
        return {key: public_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public_value(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(ROOT) + '/', '').replace(str(ROOT), '.')
    return value


def report_counts(report):
    evaluated = [row for row in report['cases'] if not row.get('context_only')]
    report.update(case_count=len(evaluated), passed_cases=sum(row.get('passed', False) for row in evaluated),
                  all_checks_passed=bool(evaluated) and all(row.get('passed', False) for row in evaluated)
                  and report.get('source_hashes_unchanged', True))


def check_result(case, request, result, prior_allowed, private_case):
    """Independent frozen assertions; never grades only the assistant's prose."""
    calls = result.get('tool_calls', [])
    successful = [call for call in calls if call.get('state') == 'completed']
    text = str(result.get('text', ''))
    checks = {
        'chat_result': result.get('kind') == 'chat',
        'no_document_sources': result.get('sources', []) == [],
        'no_original_file_transaction': not result.get('transaction'),
        'bounded_calls': len(calls) <= 4,
        'allowed_tools_only': all(call.get('tool') in ('calculate', 'calendar') for call in calls),
        'local_tool_audit': all(call.get('result', {}).get('audit', {}).get('local_only') is True for call in successful),
        'known_call_states': all(call.get('state') in ('completed', 'failed') for call in calls),
        'nonempty_answer': bool(text.strip()),
        'no_claimed_external_action': not any(forbidden_assertion(text, token) for token in
                                             ('已发送邮件', '已上传资料', '已修改原文件',
                                              '已成功发送邮件', '已成功上传资料', '已成功修改原文件')),
    }
    if request.get('conversation_parent_id'):
        checks['conversation_parent_preserved'] = result.get('parent_id') == request['conversation_parent_id']
        checks['thread_preserved'] = result.get('thread_id') == request['thread_id']
    else:
        checks['new_thread_recorded'] = bool(result.get('thread_id'))
    for index, expected in enumerate(case.get('tool_expectations', []), 1):
        checks[f'canonical_tool_result_{index}'] = any(expected_call(call, expected) for call in calls)
    for index, token in enumerate(case.get('final_contains', []), 1):
        checks[f'final_fact_{index}'] = contains_fact(text, token)
    for index, options in enumerate(case.get('final_contains_any', []), 1):
        checks[f'final_fact_group_{index}'] = any(contains_fact(text, token) for token in options)
    checks['no_forbidden_claims'] = not any(forbidden_assertion(text, token) for token in case.get('final_forbidden', []))
    if case.get('expect_tool_failure'):
        failed = [call for call in calls if call.get('tool') == case['expect_tool_failure'] and call.get('state') == 'failed']
        checks['invalid_operation_recorded'] = bool(failed)
        checks['invalid_operation_not_successful'] = not successful
        checks['failure_has_explanation'] = any(call.get('output') or call.get('summary') for call in failed)
        token = case.get('failure_argument_contains', '')
        checks['failed_original_expression'] = any(token in re.sub(r'\s', '', str(call.get('arguments', {}).get('expression', ''))) for call in failed)

    # For arithmetic-only cases, input literals must come from this chain's user
    # facts or earlier successful tools. Their outputs are not preapproved inputs
    # until the relevant tool actually executes. Structural list markers 0..8 are
    # admitted in final prose, never as arbitrary calculator input magnitudes.
    allowed = set(prior_allowed)
    allowed.update(decimal_key(value) for value in case.get('numeric_inputs', []))
    allowed.discard(None)
    unsupported_operands = []
    for call in calls:
        if call.get('state') != 'completed':
            continue
        actual = call.get('result', {})
        if call.get('tool') == 'calculate' and case.get('numeric_inputs'):
            for operand in actual.get('audit', {}).get('operands', []):
                if decimal_key(operand) not in allowed:
                    unsupported_operands.append(str(operand))
        if call.get('tool') == 'calculate':
            allowed.update(literal_values(tool_data(call).get('result', '')))
            allowed.update(literal_values(tool_data(call).get('exact_result', '')))
        else:
            allowed.update(literal_values(json.dumps(tool_data(call), ensure_ascii=False)))
    if case.get('numeric_inputs') and not case.get('expect_tool_failure'):
        checks['no_unsupported_calculation_operands'] = not unsupported_operands
        final_allowed = allowed | {Decimal(i) for i in range(9)}
        # Decimal display rounding requested by the user is an allowed rendering
        # of a canonical fraction; all required final values remain fixed above.
        for token in case.get('final_contains', []):
            final_allowed.update(literal_values(token))
        for options in case.get('final_contains_any', []):
            for token in options:
                final_allowed.update(literal_values(token))
        unsupported_final = sorted(str(value) for value in literal_values(text) - final_allowed)
        checks['no_unsupported_final_numbers'] = not unsupported_final
    else:
        unsupported_final = []

    artifacts = result.get('artifacts', [])
    checks['all_artifacts_exist'] = all(Path(item.get('path', '')).is_file() for item in artifacts)
    checks['editable_document_delivered'] = sum(item.get('type') == 'docx' for item in artifacts) >= case.get('minimum_docx', 0)
    artifact_texts, saved_artifacts = [], []
    for index, item in enumerate(artifacts):
        source = Path(item.get('path', ''))
        if not source.is_file():
            continue
        target = private_case / 'artifacts' / f'{index + 1}-{source.name}'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        target.chmod(0o600)
        saved_artifacts.append({'type': item.get('type'), 'path': str(target), 'sha256': digest(target)})
        if item.get('type') == 'docx':
            from docx import Document
            document = Document(source)
            artifact_texts.append('\n'.join(paragraph.text for paragraph in document.paragraphs)
                                  + '\n' + '\n'.join(cell.text for table in document.tables for row in table.rows for cell in row.cells))
    if case.get('artifact_contains'):
        doc_text = '\n'.join(artifact_texts)
        checks['word_contains_verified_amounts'] = all(contains_fact(doc_text, token) for token in case['artifact_contains'])
    return checks, allowed, {'unsupported_operands': unsupported_operands, 'unsupported_final_numbers': unsupported_final,
                            'artifacts': saved_artifacts}


def grader_probes():
    """CPU-only regression probes, with no model or backend imports."""
    case = next(item for item in json.loads(SUITE.read_text())['cases'] if item['id'] == 'remaining_budget')
    text = '4500-(180×12+320+750) = 1270.00\n\n180×12+320+750 = 3230.00'
    calls = []
    for expression, value, operands in (
        ('4500-(180*12+320+750)', '1270', ['4500', '180', '12', '320', '750']),
        ('180*12+320+750', '3230', ['180', '12', '320', '750']),
    ):
        calls.append({'tool': 'calculate', 'state': 'completed', 'arguments': {'expression': expression},
                      'result': {'data': {'result': value + '.00', 'exact_result': value},
                                 'audit': {'local_only': True, 'operands': operands}}})
    result = {'kind': 'chat', 'thread_id': 'probe-thread', 'text': text, 'tool_calls': calls, 'sources': []}
    with tempfile.TemporaryDirectory(prefix='guiyu-grader-probe-') as temporary:
        checks, _, _ = check_result(case, {}, result, set(), Path(temporary))
        assert all(checks.values()), checks
        bad = dict(result, text=text.replace('1270.00', '1527.45'))
        bad_checks, _, _ = check_result(case, {}, bad, set(), Path(temporary))
        assert not bad_checks['final_fact_2'] and not bad_checks['no_unsupported_final_numbers'], bad_checks
    assert Decimal('1270') in literal_values(text) and Decimal('3230') in literal_values(text)
    assert Decimal('1270.00180') not in literal_values(text)
    assert contains_fact('**1270.00**\n\n**180**', '1270')
    assert literal_values('2520\n\n1080') == {Decimal('2520'), Decimal('1080')}
    assert not contains_fact('总额1281元', '281')
    assert contains_fact('通过率80.00 %', '80%')
    assert not contains_fact('通过率180%', '80%')
    assert not forbidden_assertion('这并不代表已付款', '已付款')
    assert forbidden_assertion('现在已付款', '已付款')
    print('PASS: CPU grader probes preserve adjacent equation/paragraph numeric boundaries; wrong amounts still fail; no model loaded.')
    return 0


def resolve_saved_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def regrade(model_id):
    """Recheck preserved outputs only. Never imports backend or loads a model."""
    output = ROOT / 'qa' / f'v0.12-{model_id}-general-tools-report.json'
    original_bytes = output.read_bytes()
    report = json.loads(original_bytes)
    if report.get('state') != 'completed':
        raise ValueError('Latest report has not completed. Refusing to regrade or alter an active run.')
    if report.get('protocol', {}).get('fixture_sha256') != digest(SUITE):
        raise ValueError('Frozen fixture hash differs from inference run; no regrade performed.')
    private = resolve_saved_path(report['protocol']['trace_directory']).resolve(strict=True)
    if not private.is_relative_to((ROOT / 'qa/private/v0.12').resolve()):
        raise ValueError('Preserved trace directory is outside this QA protocol.')
    grade_id = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    grading_directory = private / 'regrades' / grade_id
    grading_directory.mkdir(parents=True, exist_ok=False)
    grading_directory.chmod(0o700)
    backup = grading_directory / 'original-public-report.json'
    backup.write_bytes(original_bytes)
    backup.chmod(0o600)
    case_by_id = {case['id']: case for case in json.loads(SUITE.read_text())['cases']}
    chains = {}
    changed = []
    reconstructed_requests = []
    for row in report['cases']:
        case = case_by_id[row['id']]
        chain = chains.setdefault(case.get('chain', row['id']), {'history': [], 'previous': None, 'allowed': set()})
        private_case = private / row['id']
        old_checks = dict(row.get('checks', {}))
        checks = {'expected_route': row.get('decision', {}).get('mode') == case['mode']}
        result_path = private_case / 'result.json'
        if result_path.is_file():
            raw_result = json.loads(result_path.read_text())
            saved_request = private_case / 'request.json'
            if saved_request.is_file():
                request = json.loads(saved_request.read_text())
            else:
                # Older v0.12 runs saved every result but omitted request.json.
                # Reconstruct only deterministic runner context from that same
                # run's preceding results; no assistant content is regenerated.
                request = {'id': raw_result['id'], 'kind': 'auto', 'prompt': case['prompt'],
                           'history': chain['history'][-8:], 'workspace_available': True, 'files_selected': True,
                           'paths': ['/nonexistent-fixture-path'], 'workspace_root': '/nonexistent-fixture-workspace'}
                if chain['previous']:
                    previous = chain['previous']
                    request.update(conversation_parent_id=previous['id'], thread_id=previous['thread_id'])
                reconstructed_requests.append(row['id'])
                write_private(grading_directory / row['id'] / 'reconstructed-request.json', request)
            result = json.loads(json.dumps(raw_result))
            # Temporary original task directories are removed after inference.
            # Grade the byte-for-byte archived artifacts, retaining raw paths in
            # result.json and preserving their saved hashes.
            saved_artifacts = row.get('artifacts', [])
            for index, artifact in enumerate(result.get('artifacts', [])):
                current = Path(artifact.get('path', ''))
                if current.is_file():
                    continue
                candidates = [private_case / 'artifacts' / f'{index + 1}-{current.name}']
                if index < len(saved_artifacts):
                    candidates.insert(0, resolve_saved_path(saved_artifacts[index]['path']))
                replacement = next((path for path in candidates if path.is_file()), None)
                if replacement is not None:
                    expected_hash = saved_artifacts[index].get('sha256') if index < len(saved_artifacts) else None
                    if expected_hash and digest(replacement) != expected_hash:
                        raise ValueError('Preserved artifact hash mismatch: ' + row['id'])
                    artifact['path'] = str(replacement)
            try:
                fresh, allowed, evidence = check_result(case, request, result, chain['allowed'], private_case)
                checks.update(fresh)
                row.update(evidence)
                chain.update(previous=raw_result, allowed=allowed)
                chain['history'] += [{'role': 'user', 'text': case['prompt']}, {'role': 'assistant', 'text': raw_result.get('text', '')}]
            except Exception as error:
                checks['regrade_completed'] = False
                row['grading_error'] = type(error).__name__ + ': ' + str(error)[:600]
        elif not case.get('route_only'):
            checks['tools_executed'] = False
        row['checks'] = checks
        row['passed'] = bool(checks) and all(checks.values()) and 'error' not in row and 'grading_error' not in row
        if old_checks != checks:
            changed.append({'id': row['id'], 'previous_checks': old_checks, 'updated_checks': checks})
        write_private(grading_directory / row['id'] / 'graded.json', row)
    report['grading_note'] = ('Regraded preserved outputs without model execution or changed prompts/expected outcomes. '
                              'Numeric scanning now retains whitespace and Markdown token boundaries between adjacent equations/paragraphs; '
                              'public QA paths are repository-relative. Original inference source hashes and runner hash remain preserved.')
    report['grading_runner_sha256'] = digest(__file__)
    report['grading_date'] = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    report['grading_directory'] = str(grading_directory)
    report['grading_request_context'] = {'reconstructed_from_preserved_chain': reconstructed_requests,
                                         'method': 'Existing request.json when available; otherwise original deterministic request fields and preceding raw result.json records.'}
    report['grading_changed_cases'] = [item['id'] for item in changed]
    report_counts(report)
    write_private(grading_directory / 'changes.json', changed)
    write_private(grading_directory / 'report.json', report)
    output.write_text(json.dumps(public_value(report), ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('passed_cases', 'case_count', 'all_checks_passed', 'grading_changed_cases')}, ensure_ascii=False))
    return 0 if report['all_checks_passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-id', choices=('qwen3.5-9b', 'qwen3-4b'), default='qwen3.5-9b')
    parser.add_argument('--cases', nargs='+', help='Fixed case IDs; prerequisite conversation turns are included automatically.')
    parser.add_argument('--regrade', action='store_true', help='Regrade the latest completed preserved report; no model loaded or outputs regenerated.')
    parser.add_argument('--check-grader', action='store_true', help='Run CPU-only grading regression probes; no model loaded.')
    parser.add_argument('--isolated', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check_grader:
        return grader_probes()
    if args.regrade:
        if args.cases:
            parser.error('--regrade preserves the latest run case set; do not combine it with --cases.')
        try:
            return regrade(args.model_id)
        except (OSError, ValueError, KeyError) as error:
            parser.error(str(error))
    suite = json.loads(SUITE.read_text())
    try:
        cases, wanted = select_cases(suite['cases'], args.cases)
    except ValueError as error:
        parser.error(str(error))
    if not args.isolated:
        command = ['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)',
                   sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], '--isolated']
        return subprocess.run(command).returncode
    sys.path.insert(0, str(ROOT / 'backend'))
    import worker as core
    from general_assistant import GeneralAssistant
    from request_router import RequestRouter
    import mlx.core as mx

    clock = date.fromisoformat(suite['clock']['date'])
    run_id = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    private = ROOT / 'qa/private/v0.12' / f'{args.model_id}-general-tools-{run_id}'
    private.mkdir(parents=True, exist_ok=False)
    private.chmod(0o700)
    output = ROOT / 'qa' / f'v0.12-{args.model_id}-general-tools-report.json'
    if output.exists():
        shutil.copy2(output, private / 'previous-report.json')
        (private / 'previous-report.json').chmod(0o600)
    report = {
        'version': '0.12.0', 'state': 'running', 'run_id': run_id, 'date': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'model_id': args.model_id, 'network_denied': core.network_probe()['blocked'], 'cases': [],
        'source_hashes': {path.name: digest(path) for path in (ROOT / 'backend').glob('*.py')},
        'protocol': {'seed': 133, 'fixture_sha256': digest(SUITE), 'runner_sha256': digest(__file__),
                     'clock': suite['clock'], 'selected_cases': sorted(wanted),
                     'method': 'Fixed expected tool outcomes; one serial real-model execution per case, normal bounded repair, no injected model outputs. Source controls test route decisions only.',
                     'limits': 'Developer tasks on Apple M5 32 GB under standard 16 GB policy; not an actual 16 GB device, user study, complete workspace regression, or held-out benchmark.',
                     'trace_directory': str(private)},
    }

    def save():
        report_counts(report)
        write_private(private / 'report.json', report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(public_value(report), ensure_ascii=False, indent=2) + '\n')

    save()
    if not report['network_denied']:
        report['fatal_error'] = 'Deny-network probe failed; no model loaded.'
        report['state'] = 'failed'
        save()
        return 1
    model_path = Path.home() / 'Library/Application Support' / (
        'GuiyuRuntime/model' if args.model_id == 'qwen3-4b' else 'GuiyuModels/Installed/' + args.model_id)
    if not model_path.is_dir():
        report['fatal_error'] = 'Installed model unavailable; no download attempted.'
        report['state'] = 'failed'
        save()
        return 1
    try:
        model = core.LocalModel(model_path)
    except Exception as error:
        report['fatal_error'] = type(error).__name__ + ': ' + str(error)[:500]
        report['state'] = 'failed'
        save()
        return 1
    report['runtime_policy'] = model.policy.object()
    generate_original = model.generate
    active_case = ''
    trace = private / 'model-trace.jsonl'

    def generate(system, user, **kwargs):
        started = time.perf_counter()
        item = {'case': active_case, 'system': system, 'user': user, 'kwargs': kwargs}
        try:
            answer, stats = generate_original(system, user, **kwargs)
            item.update(text=answer, stats=stats)
            return answer, stats
        except Exception as error:
            item['error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            item['seconds'] = round(time.perf_counter() - started, 3)
            with trace.open('a') as stream:
                stream.write(json.dumps(item, ensure_ascii=False) + '\n')
            trace.chmod(0o600)

    model.generate = generate
    chains = {}
    with tempfile.TemporaryDirectory(prefix='guiyu-general-tools-') as temporary:
        agent = core.Agent(model, Path(temporary) / 'fictional-data')
        router = RequestRouter(agent, core)
        assistant = GeneralAssistant(agent, core)
        for case in cases:
            active_case = case['id']
            mx.random.seed(133)
            started = time.perf_counter()
            row = {'id': active_case, 'prompt': case['prompt'], 'expected_mode': case['mode'],
                   'context_only': active_case not in wanted, 'checks': {}}
            chain = chains.setdefault(case.get('chain', active_case), {'history': [], 'previous': None, 'allowed': set()})
            request = {'id': str(uuid.uuid4()), 'kind': 'auto', 'prompt': case['prompt'],
                       'history': chain['history'][-8:], 'workspace_available': True, 'files_selected': True,
                       'paths': ['/nonexistent-fixture-path'], 'workspace_root': '/nonexistent-fixture-workspace'}
            if chain['previous']:
                previous = chain['previous']
                request.update(conversation_parent_id=previous['id'], thread_id=previous['thread_id'])
            events = io.StringIO()
            private_case = private / active_case
            private_case.mkdir()
            private_case.chmod(0o700)
            write_private(private_case / 'request.json', request)
            try:
                if case.get('after') and not chain['previous']:
                    raise ValueError('Required preceding conversation failed; no invented context was supplied.')
                with patch.object(core, 'Scope', side_effect=AssertionError('General request opened document scope')), redirect_stdout(events):
                    decision = router.decide(request)
                    row['decision'] = decision
                    row['checks']['expected_route'] = decision.get('mode') == case['mode']
                    if decision.get('mode') == 'tools':
                        result = assistant.run(request, now=clock)
                        write_private(private_case / 'result.json', result)
                        row.update(text=result.get('text', ''), tool_calls=result.get('tool_calls', []),
                                   parent_id=result.get('parent_id'), thread_id=result.get('thread_id'))
                        checks, allowed, evidence = check_result(case, request, result, chain['allowed'], private_case)
                        row['checks'].update(checks)
                        row.update(evidence)
                        chain.update(previous=result, allowed=allowed)
                        chain['history'] += [{'role': 'user', 'text': case['prompt']}, {'role': 'assistant', 'text': result.get('text', '')}]
                    elif not case.get('route_only'):
                        row['checks']['tools_executed'] = False
            except Exception as error:
                row['error'] = type(error).__name__ + ': ' + str(error)[:600]
            finally:
                (private_case / 'worker-events.jsonl').write_text(events.getvalue())
                (private_case / 'worker-events.jsonl').chmod(0o600)
            row['seconds'] = round(time.perf_counter() - started, 2)
            row['passed'] = bool(row['checks']) and all(row['checks'].values()) and 'error' not in row
            write_private(private_case / 'graded.json', row)
            report['cases'].append(row)
            save()
            print('GENERAL_TOOLS', active_case, row['passed'], row.get('error', ''), flush=True)
    report.update(state='completed', peak_mlx_gb=round(mx.get_peak_memory() / 1e9, 3),
                  peak_process_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 3),
                  source_hashes_unchanged=report['source_hashes'] == {path.name: digest(path) for path in (ROOT / 'backend').glob('*.py')})
    save()
    print(json.dumps({key: report[key] for key in ('passed_cases', 'case_count', 'all_checks_passed', 'peak_mlx_gb', 'peak_process_rss_gb')}, ensure_ascii=False))
    return 0 if report['all_checks_passed'] and report['source_hashes_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
