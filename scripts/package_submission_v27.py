"""Package the submission demonstration and explicit public review sources."""
import hashlib,json
from pathlib import Path
from package_model_demo_v24 import files_in,archive
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def collect(names):
    paths=[]
    for name in names:
        p=ROOT/name;assert p.exists(),name
        for f in p.rglob('*') if p.is_dir() else [p]:
            if not f.is_file() or f.is_symlink() or '__pycache__' in f.parts:continue
            if f==ROOT/'fixtures/office_novel_v26/workspace/公开项目需求.docx':continue
            paths.append(str(f.relative_to(ROOT)))
    return files_in(paths)
def main():
    e=json.loads((ROOT/'qa/v0.27/evaluation.json').read_text());p=json.loads((ROOT/'qa/v0.27/final-protocol.json').read_text())
    assert e['submission_latest']['passed']==e['submission_latest']['total']==5
    assert e['known_regression']['passed']==e['known_regression']['total']==7
    assert e['unit_tests']==701 and p['backend_hashes']=={f.name:sha(f) for f in (ROOT/'backend').glob('*.py')}
    common=['README.md','LICENSE','打开归屿.command','准备归屿.command','打开归屿32GB模型版.command','准备归屿32GB模型版.command']
    current_grant=['grant/FORM_DRAFT_COHORT4_V0_27.md','grant/BUDGET_COHORT4_V0_27.md','grant/DEMO_SCRIPT_V0_27.md','grant/PROGRESS_V0_27.md','grant/归屿_GCC_Cohort4_申请说明_v0.27.docx','grant/归屿_GCC_Cohort4_申请说明_v0.27.pdf','grant/归屿_GCC_Cohort4_路演_v0.27.pptx','grant/归屿_GCC_Cohort4_路演_v0.27.pdf']
    evidence=['qa/v0.27','qa/v0.27-native-report.json']
    source=collect(common+['Sources','backend','packaging','fixtures','scripts','tests','assets','requirements.lock','docs','qa/v0.26','qa/v0.25','qa/v0.24']+current_grant+evidence)
    for original,label in [('.build/v0.26-before-v27/backend','baseline-before-v0.27'),('.build/v0.27-before-delivery-fix/backend','baseline-v0.27-first'),('.build/v0.27-before-semantic-check/backend','baseline-v0.27-before-content-review')]:
        for f in (ROOT/original).glob('*.py'):source[label+'/backend/'+f.name]=(f.read_bytes(),0o644)
    f=ROOT/'.build/v0.27-before-delivery-fix/scripts/check_submission_v27.py'
    source['baseline-v0.27-first/scripts/check_submission_v27.py']=(f.read_bytes(),0o644)
    demo=collect(common+['dist/Guiyu-0.27.0.app','requirements.lock','packaging','scripts/prepare_model.py','scripts/prepare_local_model.py','docs/SUBMISSION_DEMO_V0_27.md','docs/PRIVACY.md']+evidence)
    attachments=collect(current_grant+['qa/v0.27/examples','qa/v0.27/evaluation.json','qa/v0.27/word-validation.json','qa/v0.27/materials-validation.json','qa/v0.27-native-report.json','docs/SUBMISSION_DEMO_V0_27.md','submission/Guiyu-GCC-Cohort4-20261031/提交前请读.md'])
    attachments['README.md']=('''# 归屿 GCC Cohort 4 提交审阅附件

申请说明PDF用于快速阅读，逐字段Markdown用于粘贴表单；八页路演有PDF与可编辑PPTX。实际成果使用虚构资料，在qa/v0.27/examples中。应用与源码为单独同版本ZIP，模型与运行环境另行准备。

公开仓库、EVM地址、每周投入、资助/GCC历史和未来承诺仍需本人确认。此包是本地审阅附件，没有提交申请或发布外部链接。不要将本机路径填入网页链接字段。原生点击因锁屏未执行，未伪造界面截图或视频。
'''.encode(),0o644)
    outputs={'source':archive(ROOT/'releases/Guiyu-0.27.0-source.zip','Guiyu-0.27.0/',source),'demo':archive(ROOT/'releases/Guiyu-0.27.0-AppleSilicon-32GB.zip','Guiyu-0.27.0/',demo),'application':archive(ROOT/'releases/Guiyu-GCC-Cohort4-application-v0.27.0.zip','Guiyu-GCC-Cohort4-v0.27.0/',attachments)}
    old=json.loads((ROOT/'qa/v0.27/preservation.json').read_text())
    assert all(sha(ROOT/n)==h for n,h in old['archives'].items())
    for n,key in [('dist/Guiyu.app/Contents/MacOS/Guiyu','old_app_binary'),('dist/Guiyu-0.26.0.app/Contents/MacOS/Guiyu','v26_app_binary')]:
        assert sha(ROOT/n)==old[key],key
    result={'version':'0.27.0','archives':outputs,'old_archives_and_apps_preserved':True,'model_runtime_user_history_private_traces_and_original_third_party_doc_excluded':True,'distribution':'Apple Silicon32GB baseline; ad hoc signed; not Apple-notarized; no external publication or application submission.'}
    (ROOT/'qa/v0.27-package.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
