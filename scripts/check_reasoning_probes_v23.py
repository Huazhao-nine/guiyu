"""Separate raw JSON probes for native thinking; not an Agent completion score."""
import argparse
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def same(actual, expected):
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual == expected
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float)) and not isinstance(actual, bool) and Decimal(str(actual)) == Decimal(str(expected))
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(same(a, e) for a, e in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def native_low(model, system, user):
    from mlx_lm import stream_generate
    from mlx_lm.sample_utils import make_sampler
    from model_output import visible_text
    prompt = model.tokenizer.apply_chat_template(
        [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
        tokenize=False, add_generation_prompt=True, enable_thinking=True, reasoning_effort='low')
    ids = model.tokenizer.encode(prompt, add_special_tokens=False)
    started = time.perf_counter()
    responses = stream_generate(model.model, model.tokenizer, prompt=ids, max_tokens=1600,
                                sampler=make_sampler(temp=0), prefill_step_size=256)
    raw, last = '', None
    try:
        for response in responses:
            raw += response.text
            last = response
    finally:
        responses.close()
        model.mx.clear_cache()
    stats = {'seconds': round(time.perf_counter() - started, 3),
             'input_tokens': len(ids), 'tokens': last.generation_tokens if last else 0,
             'tokens_per_second': round(last.generation_tps, 2) if last else 0,
             'finish_reason': last.finish_reason if last else None,
             'peak_memory_gb': round(model.mx.get_peak_memory() / 1e9, 3)}
    # The opening think tag is already in the native generation prompt.
    # Only the final answer is retained in the report.
    try:
        text = visible_text(raw if raw.lstrip().startswith('<think>') else '<think>\n' + raw, 'qwen3_5')
    except ValueError:
        return '', stats
    return text, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--isolated', action='store_true')
    args = parser.parse_args()
    if not args.isolated:
        command = ['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)',
                   sys.executable, str(Path(__file__).resolve()), '--isolated']
        raise SystemExit(subprocess.run(command).returncode)
    sys.path.insert(0, str(ROOT / 'backend'))
    from worker import LocalModel, network_probe, parse_json
    assert network_probe()['blocked']
    protocol = json.loads((ROOT / 'qa/v0.23/protocol.json').read_text())
    frozen = json.loads((ROOT / 'qa/v0.23/thinking-probe-freeze.json').read_text())
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert frozen['runner_sha256'] == digest(Path(__file__))
    fixture = ROOT / 'fixtures/model_comparison_v23/reasoning-probes.json'
    assert protocol['thinking_probe_sha256'] == digest(fixture)
    assert protocol['backend_hashes'] == {p.name: digest(p) for p in (ROOT / 'backend').glob('*.py')}
    model = LocalModel(Path.home() / '.lmstudio/models/lmstudio-community/Qwen3.8-27B-MLX-4bit')
    report = {'version': '0.23-comparison', 'time': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'model': 'Qwen3.8 27B MLX4bit', 'network_denied': True, 'total_output_budget': 1600,
              'fixture_sha256': digest(fixture), 'runner_sha256': frozen['runner_sha256'],
              'source_hashes': protocol['backend_hashes'], 'modes': {},
              'limits': 'Four known synthetic single-request JSON probes, not file tasks or an Agent success rate. Native-low uses the model template with thinking enabled; deterministic sampling, same1600 total generated-token budget. Reasoning consumes part of that budget. Final answers only are retained.'}
    system = '你是本地中文资料助手。严格按用户给定事实和条件，只返回要求的JSON对象。'
    for mode in protocol['thinking_probe_modes']:
        model.mx.random.seed(protocol['seed'])
        model.mx.reset_peak_memory()
        rows = []
        for case in json.loads(fixture.read_text()):
            began = time.perf_counter()
            try:
                if mode == 'disabled':
                    text, stats = model.generate(system, case['prompt'], max_tokens=1600, temperature=0)
                else:
                    text, stats = native_low(model, system, case['prompt'])
                try:
                    parsed = parse_json(text)
                except (ValueError, TypeError):
                    parsed = None
                row = {'id': case['id'], 'answer': text, 'stats': stats,
                       'passed': same(parsed, case['expected']) and stats.get('finish_reason') != 'length'}
            except Exception as exc:
                row = {'id': case['id'], 'passed': False, 'error': str(exc)[:300]}
            row['wall_seconds'] = round(time.perf_counter() - began, 3)
            rows.append(row)
            print(mode, case['id'], row['passed'], row['wall_seconds'], flush=True)
        report['modes'][mode] = {'cases': rows, 'passed': sum(r['passed'] for r in rows), 'total': len(rows),
                                 'peak_mlx_gb': round(model.mx.get_peak_memory() / 1e9, 3)}
    report['peak_process_rss_gb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 3)
    report['source_hashes_unchanged'] = protocol['backend_hashes'] == {
        p.name: digest(p) for p in (ROOT / 'backend').glob('*.py')}
    (ROOT / 'qa/v0.23/thinking-probe-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print({mode: str(r['passed']) + '/' + str(r['total']) for mode, r in report['modes'].items()}, flush=True)


if __name__ == '__main__':
    main()
