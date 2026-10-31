"""Prepare the pinned primary model; never read documents, history or credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import os


def verify(directory, manifest):
    if directory.is_symlink() or not directory.is_dir():return False
    for item in manifest['files']:
        path=directory/item['name']
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=item['bytes']:return False
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(4*1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=item['sha256']:return False
    return True


def mark(directory, manifest):
    temporary=directory/('.guiyu-install-'+os.urandom(8).hex())
    with temporary.open('x') as stream:
        json.dump({k:manifest[k] for k in ('repository','revision')},stream)
    temporary.chmod(0o600)
    temporary.replace(directory/'guiyu-install.json')


def prepare(root, storage, download=None):
    manifest=json.loads((root/'packaging/model-manifest.json').read_text())
    # Reuse a complete research download in place; do not duplicate 20 GB or
    # recreate the old runtime/model default.
    target=storage/'Installed'/manifest['id']
    for directory in (target,storage/'Research'/manifest['id']):
        if verify(directory,manifest):
            mark(directory,manifest)
            return directory,True
    if target.is_symlink():raise ValueError('模型目录不能是符号链接。')
    target.mkdir(parents=True,exist_ok=True,mode=0o700)
    missing=[f['name'] for f in manifest['files'] if not (target/f['name']).exists()]
    if missing:
        if download is None:
            from huggingface_hub import snapshot_download
            download=snapshot_download
        download(repo_id=manifest['repository'],revision=manifest['revision'],local_dir=target,
                 allow_patterns=missing,token=False)
    if not verify(target,manifest):raise ValueError('模型文件校验未通过，请移走损坏文件后重新准备。')
    mark(target,manifest)
    return target,False


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True,help='Python runtime location; no model is copied there.')
    parser.add_argument('--storage',type=Path,default=Path.home()/'Library/Application Support/GuiyuModels')
    args=parser.parse_args()
    directory,reused=prepare(args.root,args.storage)
    print(('已复用本机模型，未重复下载。' if reused else '模型下载完成。')+'全部文件 SHA256 校验通过。')
    print('MODEL_READY',directory)


if __name__=='__main__':main()
