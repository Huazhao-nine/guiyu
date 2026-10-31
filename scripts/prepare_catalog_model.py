"""Download a pinned catalog model without access to the document application."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.request


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(4*1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--id',required=True);parser.add_argument('--verify-existing',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    catalog=json.loads((root/'packaging/model-catalog.json').read_text())
    model=next((m for m in catalog if m['id']==args.id and m.get('purpose','chat')=='chat'),None)
    if not model:parser.error('未知对话模型')
    assert re.fullmatch(r'[a-z0-9.-]+',model['id']) and re.fullmatch(r'[a-f0-9]{40}',model['revision'])
    storage=Path.home()/'Library/Application Support/GuiyuModels'
    stage=storage/'Preparing'/model['id'];target=storage/'Installed'/model['id']
    stage.mkdir(parents=True,exist_ok=True,mode=0o700)
    if target.exists():
        if not args.verify_existing:raise SystemExit('模型已存在；使用 --verify-existing 核验现有模型，不覆盖权重。')
        for file in model['files']:
            path=target/file['name']
            assert not path.is_symlink() and path.stat().st_size==file['bytes'] and digest(path)==file['sha256']
        marker=target/'guiyu-install.json';marker.write_text(json.dumps({'revision':model['revision'],'repository':model['repository']}));marker.chmod(0o600)
        print('EXISTING_MODEL_VERIFIED',model['id'],flush=True);return
    print('PINNED_MODEL_DOWNLOAD',model['id'],sum(f['bytes'] for f in model['files']),flush=True)
    for file in model['files']:
        name=file['name'];assert Path(name).name==name and not name.startswith('.')
        path=stage/name
        for attempt in range(3):
            try:
                offset=path.stat().st_size if path.exists() else 0
                if offset==file['bytes'] and digest(path)==file['sha256']:break
                if offset>=file['bytes']:raise ValueError('现有下载未通过校验，请单独检查该文件。')
                request=urllib.request.Request(f'https://huggingface.co/{model["repository"]}/resolve/{model["revision"]}/{name}',headers={'Range':f'bytes={offset}-'} if offset else {})
                with urllib.request.urlopen(request,timeout=90) as response:
                    if offset and response.status==206:
                        if not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise ValueError('续传范围不一致')
                    elif response.status==200:offset=0
                    else:raise ValueError('模型源返回异常状态')
                    last=time.monotonic()
                    with path.open('ab' if offset else 'wb') as handle:
                        path.chmod(0o600)
                        for chunk in iter(lambda:response.read(1024*1024),b''):
                            offset+=len(chunk)
                            if offset>file['bytes']:raise ValueError('模型文件超过固定大小')
                            handle.write(chunk)
                            if time.monotonic()-last>=10:
                                print(model['id'],name,offset,'/',file['bytes'],flush=True);last=time.monotonic()
                if path.stat().st_size!=file['bytes'] or digest(path)!=file['sha256']:raise ValueError('文件大小或SHA256未通过')
                break
            except Exception as error:
                print('RETRY',model['id'],name,type(error).__name__,str(error)[:120],flush=True)
                if attempt==2:raise
                time.sleep(2+attempt*2)
        print('VERIFIED',model['id'],name,file['bytes'],flush=True)
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    marker=stage/'guiyu-install.json';marker.write_text(json.dumps({'revision':model['revision'],'repository':model['repository']}));marker.chmod(0o600)
    os.rename(stage,target)
    print('MODEL_READY',model['id'],str(target),flush=True)


if __name__=='__main__':main()
