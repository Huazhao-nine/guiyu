"""Native-template and constrained-output compatibility without any user files."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', choices=['glm-4.7-flash', 'qwen3-coder-30b-a3b'], required=True)
    parser.add_argument('--isolated', action='store_true')
    args = parser.parse_args()
    if not args.isolated:
        raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)',
                                        sys.executable, str(Path(__file__).resolve()), '--id', args.id, '--isolated']).returncode)
    sys.path.insert(0, str(ROOT / 'backend'))
    from worker import LocalModel, network_probe, parse_json
    target = ROOT / 'qa/v0.24' / (args.id + '-compatibility.json')
    assert not target.exists(), 'Do not overwrite the first compatibility result.'
    manifest = json.loads((ROOT / 'qa/v0.24' / (args.id + '-manifest.json')).read_text())
    assert manifest['upstream_hashes_verified']
    assert network_probe()['blocked']
    started = time.perf_counter()
    model = LocalModel(Path.home() / 'Library/Application Support/GuiyuModels/Research' / args.id)
    load = time.perf_counter() - started
    schema = {'type': 'object', 'properties': {'tool': {'const': 'calculate'}, 'expression': {'type': 'string'}},
              'required': ['tool', 'expression'], 'additionalProperties': False}
    answer, stats = model.generate('你是本地工具助手，只返回指定JSON。calculate的expression参数只能包含十进制数字、加减乘除符号和括号；不包含货币符号、中文单位、等号、函数或解释。',
                                   '把180元与25元相加。返回calculate工具和expression，不计算答案。',
                                   max_tokens=120, temperature=0, response_schema=schema)
    parsed = parse_json(answer)
    assert parsed['tool'] == 'calculate' and isinstance(parsed['expression'], str)
    from general_tools import run_tool
    calculator_error = None
    try:
        result = run_tool('calculate', {'expression': parsed['expression']})
        correct_expression = result['data']['result'] == '205'
    except ValueError as error:
        calculator_error = str(error)
        correct_expression = False
    checks = {'native_template_nonthinking': True, 'schema_complete': stats.get('structure_enforced', False),
              'calculator_expression_correct': correct_expression}
    chat, chat_stats = model.generate('你是归屿，面向华语用户的本地隐私助手。用简洁中文直接回答。',
                                     '你是谁？请用一句话回答。', max_tokens=100, temperature=0)
    checks['chinese_identity'] = '归屿' in chat and any('\u4e00' <= c <= '\u9fff' for c in chat)
    report = {'model': args.id, 'time': datetime.now().astimezone().isoformat(), 'passed': all(checks.values()),
              'checks': checks, 'network_denied': True, 'load_seconds': round(load, 3),
              'structured_answer': answer, 'calculator_error': calculator_error, 'stats': stats, 'identity': chat, 'identity_stats': chat_stats,
              'peak_process_rss_gb': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 3),
              'model_info': {k: v for k, v in model.info.items() if k not in ['path', 'key']},
              'backend_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'backend').glob('*.py')},
              'scope': 'Two source-free requests only. This establishes local parser/template compatibility, not office quality.'}
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
