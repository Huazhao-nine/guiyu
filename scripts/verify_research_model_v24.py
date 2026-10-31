"""Verify a pinned public model download before any local inference."""
import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODELS = {'glm-4.7-flash': 'GLM-4.7-Flash-4bit',
          'qwen3-coder-30b-a3b': 'Qwen3-Coder-30B-A3B-Instruct-4bit',
          'qwen3.6-35b-a3b': 'Qwen3.6-35B-A3B-4bit'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', required=True, choices=MODELS)
    args = parser.parse_args()
    meta = json.loads((ROOT / 'qa/private/v0.24' / (MODELS[args.id] + '-metadata.json')).read_text())
    folder = Path.home() / 'Library/Application Support/GuiyuModels/Research' / args.id
    patterns = ['*.safetensors', '*.json', '*.model', '*.txt', '*.tiktoken', '*.jinja']
    rows = []
    for file in meta['siblings']:
        name = file['rfilename']
        if not any(fnmatch.fnmatch(name, pattern) for pattern in patterns):
            continue
        assert Path(name).name == name
        path = folder / name
        assert path.is_file() and not path.is_symlink() and path.stat().st_size == file['size'], name
        sha = hashlib.sha256()
        git = hashlib.sha1(('blob ' + str(file['size']) + '\0').encode())
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
                sha.update(chunk)
                git.update(chunk)
        expected = file.get('lfs', {}).get('sha256')
        if expected:
            assert sha.hexdigest() == expected, name
        else:
            assert git.hexdigest() == file['blobId'], name
        rows.append({'name': name, 'bytes': file['size'], 'sha256': sha.hexdigest()})
    sys.path.insert(0, str(ROOT / 'backend'))
    from model_info import describe_model
    info = describe_model(folder)
    report = {'model_id': args.id, 'repository': meta['repository'], 'revision': meta['revision'],
              'upstream_hashes_verified': True, 'architecture': info['architecture'],
              'bits': info['bits'], 'weight_bytes': info['bytes'], 'files': rows,
              'location': 'GuiyuModels/Research/' + args.id,
              'inference_not_yet_claimed': True}
    (ROOT / 'qa/v0.24' / (args.id + '-manifest.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['model_id', 'revision', 'architecture', 'weight_bytes', 'upstream_hashes_verified']}))


if __name__ == '__main__':
    main()
