"""Separate source-free control: does the rejected coder work without JSON masking?"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if '--isolated' not in sys.argv:
        raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)',
                                        sys.executable, str(Path(__file__).resolve()), '--isolated']).returncode)
    sys.path.insert(0, str(ROOT / 'backend'))
    from worker import LocalModel, network_probe
    target = ROOT / 'qa/v0.24/coder-raw-control.json'
    assert not target.exists()
    model = LocalModel(Path.home() / 'Library/Application Support/GuiyuModels/Research/qwen3-coder-30b-a3b')
    assert network_probe()['blocked']
    controls = []
    for system, user in [
            ('你是本地工具助手，只返回指定JSON。calculate的expression参数只能包含十进制数字、加减乘除符号和括号；不包含货币符号、中文单位、等号、函数或解释。',
             '把180元与25元相加。返回calculate工具和expression，不计算答案。'),
            ('你是归屿，面向华语用户的本地隐私助手。用简洁中文直接回答。', '你是谁？请用一句话回答。')]:
        try:
            text, stats = model.generate(system, user, max_tokens=120, temperature=0)
            controls.append({'prompt': user, 'text': text, 'stats': stats})
        except Exception as error:
            controls.append({'prompt': user, 'error': str(error)})
    target.write_text(json.dumps({'network_denied': True, 'controls': controls,
                                 'scope': 'Source-free unmasked control only; does not replace failed compatibility or establish office quality.'},
                                ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(controls, ensure_ascii=False))


if __name__ == '__main__':
    main()
