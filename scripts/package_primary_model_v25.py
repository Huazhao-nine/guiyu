"""Package the primary-model build and evidence, excluding weights and user data."""
import hashlib
import json
from pathlib import Path
from package_model_demo_v24 import files_in,archive

ROOT=Path(__file__).resolve().parents[1]


def main():
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    evaluation=json.loads((ROOT/'qa/v0.25/evaluation.json').read_text())
    assert evaluation['final']['passed']==evaluation['final']['total']==7
    cleanup=json.loads((ROOT/'qa/v0.25/model-cleanup.json').read_text())
    assert cleanup['executed'] and cleanup['all_targets_absent'] and cleanup['protected_models_verified']
    protocol=json.loads((ROOT/'qa/v0.25/final-protocol.json').read_text())
    assert protocol['backend_hashes']=={p.name:sha(p) for p in (ROOT/'backend').glob('*.py')}
    evidence=['qa/v0.25','qa/v0.25-native-report.json','qa/v0.25-native-model-report.json']
    source=files_in(['README.md','Sources','backend','packaging','fixtures','scripts','tests','assets','requirements.lock','LICENSE',
                     'docs','grant','qa/v0.24']+evidence+
                    ['打开归屿.command','准备归屿.command','打开归屿32GB模型版.command','准备归屿32GB模型版.command'])
    for folder,label in [('.build/v0.24-before-v25/backend','baseline-before-v0.25'),
                         ('.build/v0.25-before-delivery-guard/backend','baseline-v0.25-intermediate')]:
        for p in (ROOT/folder).glob('*.py'):
            source[label+'/backend/'+p.name]=(p.read_bytes(),0o644)
    demo=files_in(['dist/Guiyu-0.25.0.app','README.md','LICENSE','打开归屿.command','准备归屿.command',
                   '打开归屿32GB模型版.command','准备归屿32GB模型版.command','requirements.lock','packaging',
                   'scripts/prepare_model.py','docs/PRIMARY_MODEL_V0_25.md','docs/PRIVACY.md']+evidence)
    demo_readme='''# 归屿0.25 32GB本地版

先退出当前打开的归屿，再双击“打开归屿.command”。本机已准备Qwen3.6 35B A3B，新版会直接使用它。资料、推理与工具全部本地，原文件改动前先预览并单独确认。

新设备需要至少32GB内存的Apple芯片Mac，先运行“准备归屿.command”。准备阶段需要网络、uv和建议至少35GB可用存储；该包不含模型权重与Python环境。本机已有完整环境时不需要重新准备。从源码重建需另取源码包并安装Xcode Command Line Tools。

[本版说明](docs/PRIMARY_MODEL_V0_25.md) · [实际虚构交付](qa/v0.25/examples/README.md) · [评测记录](qa/v0.25/evaluation.json) · [隐私设计](docs/PRIVACY.md)

最终7项开发补测通过，首次五项3/5与中间5/7均保留。这不是任意资料成功率。实际GUI点击因Mac锁屏未执行；原生状态、键盘和命令行任务另计。应用为临时签名，未做Apple公证。

本次只在用户明确授权的这台机器清理其他对话模型，旧模型文件不包含在本包内。工作记录保留，检索与隐私识别仍作为独立组件使用。
'''
    demo['README.md']=(demo_readme.encode(),0o644)
    outputs={
        'source':archive(ROOT/'releases/Guiyu-0.25.0-source.zip','Guiyu-0.25.0/',source),
        'demo':archive(ROOT/'releases/Guiyu-0.25.0-AppleSilicon-32GB.zip','Guiyu-0.25.0/',demo)}
    old=json.loads((ROOT/'qa/v0.25/preservation.json').read_text())
    assert all(sha(ROOT/name)==h for name,h in old['archives'].items())
    assert sha(ROOT/'dist/Guiyu.app/Contents/MacOS/Guiyu')==old['production_binary_sha256']
    assert sha(ROOT/'dist/Guiyu.app/Contents/Resources/worker.py')==old['production_backend_sha256']
    report={'version':'0.25.0','archives':outputs,'previous_archives_and_running_app_preserved':True,
            'weights_runtime_history_and_private_traces_excluded':True,'distribution':'Ad hoc signed Apple Silicon demo;32GB baseline; no Apple notarization.'}
    (ROOT/'qa/v0.25-package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
