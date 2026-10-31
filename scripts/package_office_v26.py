"""Package the 32GB office iteration, preserving first failures and sources."""
import hashlib,json
from pathlib import Path
from package_model_demo_v24 import files_in,archive
ROOT=Path(__file__).resolve().parents[1]

def collect(names):
    paths=[]
    for name in names:
        path=ROOT/name
        assert path.exists(),name
        for p in path.rglob('*') if path.is_dir() else [path]:
            if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts:continue
            if p==ROOT/'fixtures/office_novel_v26/workspace/公开项目需求.docx':continue
            paths.append(str(p.relative_to(ROOT)))
    return files_in(paths)

def main():
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    evaluation=json.loads((ROOT/'qa/v0.26/evaluation.json').read_text())
    assert evaluation['initial']['passed']==1 and evaluation['initial']['total']==8
    assert evaluation['development_latest']['total']==8 and evaluation['confirmation_first']['total']==5
    protocol=json.loads((ROOT/'qa/v0.26/final-protocol.json').read_text())
    assert protocol['backend_hashes']=={p.name:sha(p) for p in (ROOT/'backend').glob('*.py')}
    evidence=['qa/v0.26','qa/v0.26-native-report.json']
    common=['README.md','LICENSE','打开归屿.command','准备归屿.command','打开归屿32GB模型版.command','准备归屿32GB模型版.command']
    source=collect(common+['Sources','backend','packaging','fixtures','scripts','tests','assets','requirements.lock','docs','grant','qa/v0.25','qa/v0.24']+evidence)
    snapshots=[('.build/v0.25-before-v26/backend','baseline-before-v0.26'),
               ('.build/v0.26-before-second-fix/backend','baseline-v0.26-first-adaptation'),
               ('.build/v0.26-before-dependency-fix/backend','baseline-v0.26-recovery'),
               ('.build/v0.26-before-followup-focus/backend','baseline-v0.26-dependency'),
               ('.build/v0.26-before-final-review/backend','baseline-v0.26-focused'),
               ('.build/v0.26-before-output-boundary/backend','baseline-v0.26-first-confirmation'),
               ('.build/v0.26-before-scope-interpretation/backend','baseline-v0.26-output-boundary'),
               ('.build/v0.26-before-condition-proof/backend','baseline-v0.26-pre-condition-proof')]
    for path,label in snapshots:
        for p in (ROOT/path).glob('*.py'):source[label+'/backend/'+p.name]=(p.read_bytes(),0o644)
    p=ROOT/'.build/v0.25-before-v26/scripts/check_office_novel_v26.py'
    source['baseline-before-v0.26/scripts/check_office_novel_v26.py']=(p.read_bytes(),0o644)
    demo=collect(common+['dist/Guiyu-0.26.0.app','requirements.lock','packaging','scripts/prepare_model.py','docs/GENERAL_WORK_V0_26.md','docs/PRIVACY.md']+evidence)
    demo['README.md']=('''# 归屿 0.26 32GB本地版

先退出当前归屿，再双击“打开归屿.command”。已有运行环境时直接使用Qwen3.6 35B A3B。新机器至少需要32GB内存的Apple芯片Mac，先运行“准备归屿.command”；准备阶段联网下载公开组件，处理资料时全程本地。原文件修改前仍先预览并单独确认。

首页“体验办公资料”提供台账、报价、混合单位记录和活动资料。直接说目标，完成后可接着追问。结果预览与导出为独立副本。

使用与证据范围见docs/GENERAL_WORK_V0_26.md、qa/v0.26/evaluation.json和qa/v0.26/examples/README.md。首次与中间失败均保留，开发复测与保留资料的首次结果分开记录，不代表任意资料成功率。桌面点击验证另见qa/v0.26-native-report.json。

包内不含模型权重、运行环境或工作记录。应用使用临时签名，未做Apple公证。源码、构建和复现脚本见同版本源码包。
'''.encode(),0o644)
    outputs={'source':archive(ROOT/'releases/Guiyu-0.26.0-source.zip','Guiyu-0.26.0/',source),
             'demo':archive(ROOT/'releases/Guiyu-0.26.0-AppleSilicon-32GB.zip','Guiyu-0.26.0/',demo)}
    old=json.loads((ROOT/'qa/v0.26/preservation.json').read_text())
    assert all(sha(ROOT/name)==h for name,h in old['archives'].items())
    assert sha(ROOT/'dist/Guiyu-0.25.0.app/Contents/MacOS/Guiyu')==old['v25_app_binary']
    assert sha(ROOT/'dist/Guiyu.app/Contents/MacOS/Guiyu')==old['running_app_binary']
    report={'version':'0.26.0','archives':outputs,'previous_archives_and_apps_preserved':True,
            'models_runtime_history_private_traces_and_original_public_document_excluded':True,
            'distribution':'Ad hoc signed Apple Silicon app;32GB baseline; not Apple-notarized.'}
    (ROOT/'qa/v0.26-package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
