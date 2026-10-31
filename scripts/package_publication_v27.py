"""Package the authorized public release without replacing the earlier candidate."""
import argparse
import hashlib
import json
from pathlib import Path

from package_model_demo_v24 import archive
from package_submission_v27 import collect

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-pending-native-retest", action="store_true",
                        help="Ship a prerelease with the Mac-lock UI gap explicitly retained; never mark that test passed.")
    args = parser.parse_args()
    protocol = json.loads((ROOT / "qa/v0.27/publication-protocol.json").read_text())
    native = json.loads((ROOT / "qa/v0.27-native-report.json").read_text())
    assert protocol["tests"] == 707
    assert protocol["backend_hashes"] == {f.name: sha(f) for f in (ROOT / "backend").glob("*.py")}
    assert native["backend_hashes"] == protocol["backend_hashes"]
    pending = native["status"] == "PARTIAL_NATIVE_PATCH_RETEST_PENDING_LOCK"
    assert native["status"] == "PASS_NATIVE_PUBLICATION_SCENARIOS" or (args.allow_pending_native_retest and pending)
    regression = json.loads((ROOT / "qa/v0.27/format-reuse-regression.json").read_text())
    assert regression["passed"] and regression["backend_hashes"] == protocol["backend_hashes"]
    if pending:
        assert native["patch_native_retest_executed"] is False and native["passed_task_count"] == 3
        assert native["patch_unit_tests"] == 707
    assert json.loads((ROOT / "qa/v0.27/materials-publication-validation.json").read_text())["passed"]
    common = ["README.md", "LICENSE", "打开归屿.command", "准备归屿.command",
              "打开归屿32GB模型版.command", "准备归屿32GB模型版.command"]
    grants = ["grant/" + name for name in (
        "FORM_DRAFT_COHORT4_V0_27.md", "BUDGET_COHORT4_V0_27.md",
        "DEMO_SCRIPT_V0_27.md", "PROGRESS_V0_27.md",
        "归屿_GCC_Cohort4_申请说明_v0.27.docx", "归屿_GCC_Cohort4_申请说明_v0.27.pdf",
        "归屿_GCC_Cohort4_路演_v0.27.pptx", "归屿_GCC_Cohort4_路演_v0.27.pdf")]
    evidence = ["qa/v0.27", "qa/v0.27-native-report.json"]
    source = collect(common + ["Sources", "backend", "packaging", "fixtures", "scripts", "tests",
                               "assets", "requirements.lock", "docs", "qa/v0.26", "qa/v0.25", "qa/v0.24"]
                     + grants + evidence)
    snapshots = [
        (".build/v0.26-before-v27/backend", "baseline-before-v0.27"),
        (".build/v0.27-before-delivery-fix/backend", "baseline-v0.27-first"),
        (".build/v0.27-before-semantic-check/backend", "baseline-v0.27-before-content-review"),
        (".build/v0.27-before-format-reuse/backend", "baseline-v0.27-before-export-reuse"),
    ]
    for directory, label in snapshots:
        for file in (ROOT / directory).glob("*.py"):
            source[label + "/backend/" + file.name] = (file.read_bytes(), 0o644)
    file = ROOT / ".build/v0.27-before-delivery-fix/scripts/check_submission_v27.py"
    source["baseline-v0.27-first/scripts/check_submission_v27.py"] = (file.read_bytes(), 0o644)
    demo = collect(common + ["dist/Guiyu-0.27.0.app", "requirements.lock", "packaging",
                             "scripts/prepare_model.py", "scripts/prepare_local_model.py",
                             "docs/SUBMISSION_DEMO_V0_27.md", "docs/PRIVACY.md"] + evidence)
    attachments = collect(grants + ["qa/v0.27/examples", "qa/v0.27/evaluation.json",
        "qa/v0.27/publication-protocol.json", "qa/v0.27/format-reuse-regression.json",
        "qa/v0.27/word-validation.json", "qa/v0.27/materials-publication-validation.json",
        "qa/v0.27/native", "qa/v0.27-native-report.json", "docs/SUBMISSION_DEMO_V0_27.md"])
    attachments["README.md"] = ("""# 归屿 GCC Cohort 4 申请附件

申请说明PDF供快速阅读，逐字段Markdown用于填写表单；八页路演提供PDF与可编辑PPTX。qa/v0.27/examples是虚构资料的实际导出成果。native中是真实界面截图与操作节选，等待阶段已压缩。应用和源码为同版本独立ZIP，模型与运行环境另行准备。

公开仓库：https://github.com/Huazhao-nine/guiyu
演示版本：https://github.com/Huazhao-nine/guiyu/releases/tag/v0.27.0

申请8,000 U、12周、每周计划20小时，资助后维护至少6个月。无其他资助、并行申请或GCC经历。EVM地址由申请人另行提供。此附件不表示网页申请已经提交。
""".encode(), 0o644)
    target = ROOT / "releases/v0.27.0-published"
    target.mkdir(parents=True, exist_ok=True)
    outputs = {
        "source": archive(target / "Guiyu-0.27.0-source.zip", "Guiyu-0.27.0/", source),
        "demo": archive(target / "Guiyu-0.27.0-AppleSilicon-32GB.zip", "Guiyu-0.27.0/", demo),
        "application": archive(target / "Guiyu-GCC-Cohort4-application-v0.27.0.zip",
                               "Guiyu-GCC-Cohort4-v0.27.0/", attachments),
    }
    candidate = json.loads((ROOT / "qa/v0.27-package.json").read_text())
    assert all(sha(ROOT / x["path"]) == x["sha256"] for x in candidate["archives"].values())
    old = json.loads((ROOT / "qa/v0.27/preservation.json").read_text())
    assert all(sha(ROOT / name) == value for name, value in old["archives"].items())
    for name, key in [("dist/Guiyu.app/Contents/MacOS/Guiyu", "old_app_binary"),
                      ("dist/Guiyu-0.26.0.app/Contents/MacOS/Guiyu", "v26_app_binary")]:
        assert sha(ROOT / name) == old[key]
    report = {"version": "0.27.0", "archives": outputs, "candidate_and_historical_archives_preserved": True,
              "models_runtime_user_history_and_private_traces_excluded": True,
              "native_status": native["status"], "native_ui_gap_explicitly_retained": pending,
              "distribution": "Apple Silicon32GB prerelease; ad hoc signed, not Apple-notarized. Public release authorized; GCC application not submitted."}
    (ROOT / "qa/v0.27-publication-package.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
