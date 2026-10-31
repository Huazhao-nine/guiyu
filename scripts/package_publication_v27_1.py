"""Package the native-verified patch without replacing any completed release."""
import hashlib
import json
from pathlib import Path

from package_model_demo_v24 import archive
from package_submission_v27 import collect

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.27.1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = json.loads((ROOT/'qa/v0.27.1/publication-protocol.json').read_text())
    native = json.loads((ROOT/'qa/v0.27.1/native-evaluation.json').read_text())
    hashes = {p.name:sha(p) for p in (ROOT/'backend').glob('*.py')}
    assert protocol['tests'] == 741 and protocol['backend_hashes'] == hashes
    assert native['backend_hashes'] == hashes and native['passed'] == native['total'] == 6
    assert native['source_mutations'] is False
    regression = json.loads((ROOT/'qa/v0.27.1/format-reuse-regression.json').read_text())
    assert regression['passed'] and regression['backend_hashes'] == hashes
    assert json.loads((ROOT/'qa/v0.27.1/materials-validation.json').read_text())['passed']
    common = ['README.md','LICENSE','打开归屿.command','准备归屿.command',
              '打开归屿32GB模型版.command','准备归屿32GB模型版.command']
    grants = ['grant/'+name for name in (
        'FORM_DRAFT_COHORT4_V0_27_1.md','BUDGET_COHORT4_V0_27_1.md',
        'DEMO_SCRIPT_V0_27_1.md','PROGRESS_V0_27_1.md',
        '归屿_GCC_Cohort4_申请说明_v0.27.1.docx','归屿_GCC_Cohort4_申请说明_v0.27.1.pdf',
        '归屿_GCC_Cohort4_路演_v0.27.1.pptx','归屿_GCC_Cohort4_路演_v0.27.1.pdf')]
    evidence = ['qa/v0.27.1','qa/v0.27','qa/v0.27-native-report.json']
    source = collect(common+['Sources','backend','packaging','fixtures','scripts','tests','assets',
        'requirements.lock','docs','qa/v0.26','qa/v0.25','qa/v0.24']+grants+evidence)
    snapshots = [
        ('.build/v0.26-before-v27/backend','baseline-before-v0.27'),
        ('.build/v0.27-before-delivery-fix/backend','baseline-v0.27-first'),
        ('.build/v0.27-before-semantic-check/backend','baseline-v0.27-before-content-review'),
        ('.build/v0.27-before-format-reuse/backend','baseline-v0.27-before-export-reuse'),
        ('.build/v0.27-before-native-date-audit/backend','baseline-v0.27-published'),
        ('.build/v0.27.1-before-adaptive-normalization/backend','baseline-v0.27.1-date-only'),
        ('.build/v0.27.1-before-calculation-objectives/backend','baseline-v0.27.1-before-objectives'),
        ('.build/v0.27.1-before-review-format/backend','baseline-v0.27.1-before-review-format'),
        ('.build/v0.27.1-before-producer-stop/backend','baseline-v0.27.1-before-producer-stop'),
        ('.build/v0.27.1-before-writing-review/backend','baseline-v0.27.1-before-writing-review'),
        ('.build/v0.27.1-before-focused-review/backend','baseline-v0.27.1-before-focused-review'),
        ('.build/v0.27.1-before-calendar-proof/backend','baseline-v0.27.1-before-calendar-proof'),
        ('.build/v0.27.1-before-review-claim/backend','baseline-v0.27.1-before-review-claim'),
        ('.build/v0.27.1-before-payment-condition/backend','baseline-v0.27.1-before-payment-condition'),
    ]
    for directory,label in snapshots:
        files=list((ROOT/directory).glob('*.py'));assert files,directory
        for file in files:source[label+'/backend/'+file.name]=(file.read_bytes(),0o644)
    old_runner=ROOT/'.build/v0.27-before-delivery-fix/scripts/check_submission_v27.py'
    source['baseline-v0.27-first/scripts/check_submission_v27.py']=(old_runner.read_bytes(),0o644)
    demo = collect(common+['dist/Guiyu-0.27.1.app','requirements.lock','packaging',
        'scripts/prepare_model.py','scripts/prepare_local_model.py','docs/SUBMISSION_DEMO_V0_27_1.md',
        'docs/PRIVACY.md']+evidence)
    attachments = collect(grants+['qa/v0.27.1/native','qa/v0.27.1/outputs',
        'qa/v0.27.1/native-evaluation.json','qa/v0.27.1/word-validation.json',
        'qa/v0.27.1/publication-protocol.json','qa/v0.27.1/materials-validation.json',
        'docs/SUBMISSION_DEMO_V0_27_1.md'])
    attachments['README.md'] = ('''# 归屿 GCC Cohort 4 申请附件

申请说明PDF供阅读，逐字段Markdown用于填写表单；八页路演提供PDF和可编辑PPTX。native是真实界面证据与压缩等待的截图演示序列，outputs是本机实际生成的虚构资料成果。源码和Apple Silicon32GB应用分别打包，模型与运行环境另行准备。

公开仓库：https://github.com/Huazhao-nine/guiyu
演示版本：https://github.com/Huazhao-nine/guiyu/releases/tag/v0.27.1

申请8,000 U、12周、每周计划20小时，资助后维护至少六个月。无其他资助、并行申请或GCC经历。EVM地址由申请人另行提供。网页申请尚未提交。
'''.encode(),0o644)
    target=ROOT/'releases/v0.27.1-published';target.mkdir(parents=True,exist_ok=True)
    outputs={
        'source':archive(target/'Guiyu-0.27.1-source.zip','Guiyu-0.27.1/',source),
        'demo':archive(target/'Guiyu-0.27.1-AppleSilicon-32GB.zip','Guiyu-0.27.1/',demo),
        'application':archive(target/'Guiyu-GCC-Cohort4-application-v0.27.1.zip','Guiyu-GCC-Cohort4-v0.27.1/',attachments),
    }
    preservation=json.loads((ROOT/'qa/v0.27.1/preservation.json').read_text())
    assert all(sha(ROOT/n)==v for n,v in preservation['files'].items())
    report={'version':VERSION,'archives':outputs,'historical_archives_and_apps_preserved':True,
        'models_runtime_private_traces_and_user_history_excluded':True,'native_passed':native['passed'],
        'scope':'Known fictional task native acceptance; not arbitrary new-data success. Ad hoc signed, not Apple-notarized. GCC application not submitted.'}
    (ROOT/'qa/v0.27.1/package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
