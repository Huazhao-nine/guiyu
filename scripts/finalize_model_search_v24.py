"""Verify every used model again and register only the selected local preview model."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def main():
    folder=ROOT/'qa/v0.24'
    evaluation=json.loads((folder/'adaptation/evaluation.json').read_text())
    assert evaluation['selected']=='qwen3.6-35b-a3b'
    assert evaluation['confirmation']['new']['total']==4
    final=json.loads((folder/'release/evaluation.json').read_text())
    assert final['summary']['passed']==final['summary']['total']==5
    rows=[]
    ids=['glm-4.7-flash','qwen3-coder-30b-a3b','qwen3.6-35b-a3b','qwen3.5-9b']
    storage=Path.home()/'Library/Application Support/GuiyuModels'
    for model in ids:
        manifest=json.loads((folder/('adaptation/baseline-manifest.json' if model=='qwen3.5-9b' else model+'-manifest.json')).read_text())
        directory=storage/('Installed' if model=='qwen3.5-9b' else 'Research')/model
        for item in manifest['files']:
            p=directory/item['name']
            assert p.is_file() and not p.is_symlink() and p.stat().st_size==item['bytes']
            assert sha(p)==item['sha256'],model+'/'+item['name']
        rows.append({'id':model,'files':len(manifest['files']),'all_sha256_unchanged':True})
    selected=json.loads((folder/'qwen3.6-35b-a3b-manifest.json').read_text())
    marker=storage/'Research/qwen3.6-35b-a3b/guiyu-install.json'
    created=False
    if marker.exists():assert not marker.is_symlink() and json.loads(marker.read_text())['revision']==selected['revision']
    else:
        fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump({'modelID':selected['model_id'],'revision':selected['revision'],'repository':selected['repository']},stream)
        created=True
    old=json.loads((folder/'pre-final-preservation.json').read_text())
    assert all(sha(ROOT/name)==h for name,h in old['archives'].items())
    assert sha(ROOT/'dist/Guiyu.app/Contents/MacOS/Guiyu')==old['production_binary_sha256']
    assert sha(ROOT/'dist/Guiyu.app/Contents/Resources/worker.py')==old['production_backend_sha256']
    result={'time':datetime.now().astimezone().isoformat(),'models':rows,
            'hardware':{'cpu':subprocess.check_output(['/usr/sbin/sysctl','-n','machdep.cpu.brand_string'],text=True).strip(),
                        'memory_bytes':int(subprocess.check_output(['/usr/sbin/sysctl','-n','hw.memsize'],text=True)),
                        'macos':platform.mac_ver()[0]},
            'selected_model_registered_for_new_preview':True,'registration_marker_created':created,
            'existing_selection_and_history_not_modified':True,'old_application_and_archives_unchanged':True,
            'scope':'Registration writes only verified public model metadata in Research. The new app discovers it at next launch; existing app/model preference/history remain untouched.'}
    target=folder/'model-integrity-after.json';assert not target.exists()
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
