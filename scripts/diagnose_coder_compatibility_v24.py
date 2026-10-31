"""Observe a source-free generation without changing the shipped model wrapper."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    if '--isolated' not in sys.argv:
        raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)',
                                        sys.executable, str(Path(__file__).resolve()), '--isolated']).returncode)
    sys.path.insert(0, str(ROOT / 'backend'))
    from worker import LocalModel, network_probe
    from structured_output import JSONLogitsProcessor
    from mlx_lm import stream_generate
    from mlx_lm.sample_utils import make_sampler
    target = ROOT / 'qa/v0.24/coder-compatibility-diagnostic.json'
    assert not target.exists()
    model = LocalModel(Path.home() / 'Library/Application Support/GuiyuModels/Research/qwen3-coder-30b-a3b')
    assert network_probe()['blocked']
    system = '你是本地工具助手，只返回指定JSON。calculate的expression参数只能包含十进制数字、加减乘除符号和括号；不包含货币符号、中文单位、等号、函数或解释。'
    user = '把180元与25元相加。返回calculate工具和expression，不计算答案。'
    schema = {'type': 'object', 'properties': {'tool': {'const': 'calculate'}, 'expression': {'type': 'string'}},
              'required': ['tool', 'expression'], 'additionalProperties': False}
    prompt = model.tokenizer.apply_chat_template([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                                                 tokenize=False, add_generation_prompt=True, enable_thinking=False, reasoning_effort='low')
    ids = model.tokenizer.encode(prompt)
    processor = JSONLogitsProcessor(model.tokenizer, schema, len(ids))
    last_prefix = []
    choose = processor.choose

    def observed(generated, ranked):
        last_prefix[:] = [model.tokenizer.decode(generated)]
        return choose(generated, ranked)

    processor.choose = observed
    began = time.monotonic()
    raw, last, error = '', None, None
    responses = stream_generate(model.model, model.tokenizer, prompt=ids, max_tokens=120,
                                sampler=make_sampler(temp=0), prefill_step_size=model.policy.prefill_tokens,
                                logits_processors=[processor])
    try:
        for response in responses:
            last = response
            raw += response.text
    except Exception as exc:
        error = repr(exc)
    finally:
        responses.close()
    result = {'network_denied': True, 'raw_text': raw, 'last_processor_prefix': last_prefix,
              'valid_complete_raw': processor.grammar.status(raw), 'error': error,
              'tokens': getattr(last, 'generation_tokens', None), 'finish': getattr(last, 'finish_reason', None),
              'seconds': round(time.monotonic() - began, 3), 'scope': 'Source-free interface diagnostic; no office prompts or backend changed.'}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
