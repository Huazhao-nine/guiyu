"""Package the32GB preview and its model evidence; never include weights or history."""
import hashlib
import json
from pathlib import Path
import re
import stat
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def sha(data):return hashlib.sha256(data).hexdigest()


def files_in(items):
    found={}
    for name in items:
        path=ROOT/name;assert path.exists(),name
        for p in path.rglob('*') if path.is_dir() else [path]:
            if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or p.name=='.DS_Store':continue
            assert not p.name.endswith(('.safetensors','.onnx','.onnx_data','.pyc','.jsonl','.whl'))
            assert '/qa/private/' not in str(p)
            if p.suffix in ('.py','.json','.md','.sh','.command','.lock','.swift','.txt'):
                assert not re.search(rb'/Users/[A-Za-z0-9][^/\s\x22\x27]*/',p.read_bytes()),str(p)
            found[str(p.relative_to(ROOT))]=(p.read_bytes(),stat.S_IMODE(p.stat().st_mode))
    return found


def archive(target,prefix,entries):
    assert not target.exists(),'Preserve completed bundles.'
    sums=''.join(sha(data)+'  '+prefix+name+'\n' for name,(data,mode) in sorted(entries.items()))
    all_entries=entries|{'SHA256SUMS':(sums.encode(),0o644)}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name,(data,mode) in sorted(all_entries.items()):
            info=zipfile.ZipInfo(prefix+name);info.create_system=3;info.external_attr=(stat.S_IFREG|mode)<<16
            info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in sums.splitlines():
            h,name=line.split('  ',1);assert sha(z.read(name))==h
    return {'path':str(target.relative_to(ROOT)),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes()),
            'members':len(all_entries),'crc_and_hashes_verified':True}


def main():
    result=json.loads((ROOT/'qa/v0.24/adaptation/evaluation.json').read_text())
    assert result['selected']=='qwen3.6-35b-a3b'
    assert result['confirmation']['known']['total']==18 and result['confirmation']['new']['total']==4
    final=json.loads((ROOT/'qa/v0.24/release/evaluation.json').read_text())
    assert final['summary']['total']==5 and final['summary']['passed']==5
    source=files_in(['Sources','backend','packaging','fixtures','scripts','tests','assets','requirements.lock','LICENSE',
                     'docs','grant','qa/v0.24','qa/v0.23','qa/v0.22/freeze.json','qa/v0.22-delivery-checks.json','qa/v0.24-native-report.json',
                     '打开归屿32GB模型版.command','准备归屿32GB模型版.command'])
    # Reproduce the original model-only phase in a separate checkout with this backend.
    for p in (ROOT/'.build/v0.22-before-v24-adaptation/backend').glob('*.py'):
        source['baseline-v0.22/backend/'+p.name]=(p.read_bytes(),0o644)
    for p in (ROOT/'.build/v0.24-before-boundary-fix/backend').glob('*.py'):
        source['baseline-v0.24-adapted/backend/'+p.name]=(p.read_bytes(),0o644)
    for p in (ROOT/'.build/v0.24-before-month-scope/backend').glob('*.py'):
        source['baseline-v0.24-before-month-scope/backend/'+p.name]=(p.read_bytes(),0o644)
    readme='''# 归屿32GB本地模型预览版0.24.0\n\n本机已准备Qwen3.6 35B A3B。先退出当前归屿，再运行“打开归屿32GB模型版.command”，在模型库切换使用。资料与推理全部本地，原文件修改前先预览确认。\n\n[模型选择、使用与证据范围](docs/MODEL_SELECTION_V0_24.md) · [复现方法](docs/MODEL_SEARCH_REPRODUCE_V0_24.md)\n\n相同六项困难目标：9B2/6、35B6/6。35B扩展已知目标17/18，四项新资料首次1/4；修正通用流程后的五项开发补测5/5。后续补测不能替代首次成绩。GUI点击因锁屏未执行，原生代码与模型信息检查另计。\n\n已备运行环境时直接打开。新设备先运行“准备归屿32GB模型版.command”。分发包不含权重或运行环境，完整源码与重建脚本见源码包。\n\n源码构建使用 `zsh scripts/build_model_demo_v24.sh`，生成独立的 `dist/Guiyu-0.24.0.app`。旧源码快照用于独立目录复现，不覆盖当前后端。\n'''
    source['README.md']=(readme.encode(),0o644)
    source['docs/MODEL_SEARCH_REPRODUCE_V0_24.md']=((ROOT/'docs/MODEL_SEARCH_REPRODUCE_V0_24.md').read_bytes(),0o644)
    demo=files_in(['dist/Guiyu-0.24.0.app','打开归屿32GB模型版.command','准备归屿32GB模型版.command',
                   'requirements.lock','packaging','scripts/prepare_model.py','scripts/prepare_local_model.py',
                   'backend/model_info.py','backend/runtime_policy.py',
                   'docs/MODEL_SELECTION_V0_24.md','docs/MODEL_SEARCH_REPRODUCE_V0_24.md','docs/PRIVACY.md',
                   'qa/v0.24','qa/v0.24-native-report.json','LICENSE'])
    demo['README.md']=source['README.md']
    outputs={
        'source':archive(ROOT/'releases/Guiyu-0.24.0-source.zip','Guiyu-0.24.0/',source),
        'demo':archive(ROOT/'releases/Guiyu-0.24.0-AppleSilicon-32GB-preview.zip','Guiyu-0.24.0/',demo)}
    old=json.loads((ROOT/'qa/v0.24/pre-final-preservation.json').read_text())
    assert all(sha((ROOT/name).read_bytes())==h for name,h in old['archives'].items())
    assert sha((ROOT/'dist/Guiyu.app/Contents/MacOS/Guiyu').read_bytes())==old['production_binary_sha256']
    assert sha((ROOT/'dist/Guiyu.app/Contents/Resources/worker.py').read_bytes())==old['production_backend_sha256']
    report={'archives':outputs,'previous_archives_and_running_app_files_preserved':True,
            'no_models_runtime_history_or_private_traces':True,'version':'0.24.0','distribution':'Separate32GB preview, requires the local runtime; not Apple-notarized.'}
    (ROOT/'qa/v0.24-package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
