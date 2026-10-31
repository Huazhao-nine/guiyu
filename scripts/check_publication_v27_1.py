"""Verify the exact public release by clean extraction, tests and a native rebuild."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import tempfile

from check_submission_release_v27 import extract

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    package = json.loads((ROOT / "qa/v0.27.1/package.json").read_text())
    for item in package["archives"].values():
        assert sha(ROOT / item["path"]) == item["sha256"]

    def run(command, cwd, label, env):
        result = subprocess.run(command, cwd=cwd, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (ROOT / "qa/private/v0.27.1" / ("publication-extracted-" + label + ".log")).write_text(result.stdout)
        assert result.returncode == 0, label + ": " + result.stdout[-1800:]
        return result.stdout

    def probe(app, cwd, label, env):
        run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], cwd, label + "-signature", env)
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
        assert info["CFBundleShortVersionString"] == "0.27.1" and info["CFBundleVersion"] == "271"
        result = json.loads(run([str(app / "Contents/MacOS/Guiyu"), "--privacy-probe"], cwd,
                                label + "-network", env).strip().splitlines()[-1])
        assert result["sandbox"] and all(x["denied"] for x in result["probes"])
        helper = app / "Contents/Helpers/GuiyuModelDownloader.app/Contents/MacOS/GuiyuModelDownloader"
        result = json.loads(run([str(helper), "--boundary-probe"], cwd, label + "-helper", env).strip().splitlines()[-1])
        assert result["sandbox"] and all(x["denied"] for x in result["private_reads"])
        return {"signature_verified": True, "network_denied": True, "helper_private_reads_denied": True}

    with tempfile.TemporaryDirectory(prefix="guiyu-v27-publication-check-") as temporary:
        base = Path(temporary)
        src = extract(ROOT / package["archives"]["source"]["path"], base / "source", "Guiyu-0.27.1")
        demo = extract(ROOT / package["archives"]["demo"]["path"], base / "demo", "Guiyu-0.27.1")
        extract(ROOT / package["archives"]["application"]["path"], base / "application", "Guiyu-GCC-Cohort4-v0.27.1")
        protocol = json.loads((src / "qa/v0.27.1/publication-protocol.json").read_text())
        assert protocol["backend_hashes"] == {f.name: sha(f) for f in (src / "backend").glob("*.py")}
        failed_versions = [
            ('native-review-format-failure.json','before-review-format'),
            ('native-producer-stop-failure.json','before-producer-stop'),
            ('native-writing-repair-failure.json','before-writing-review'),
            ('writing-review-replay-failure.json','before-focused-review'),
            ('writing-calendar-review-failure.json','before-calendar-proof'),
            ('native-review-claim-failure.json','before-review-claim'),
            ('writing-payment-condition-review.json','before-payment-condition'),
        ]
        for filename,label in failed_versions:
            failure=json.loads((src/'qa/v0.27.1'/filename).read_text())
            assert failure['backend_hashes']=={f.name:sha(f) for f in (src/('baseline-v0.27.1-'+label)/'backend').glob('*.py')},filename
        old_protocol = json.loads((src / "qa/v0.27/final-protocol.json").read_text())
        assert old_protocol["backend_hashes"] == {f.name: sha(f) for f in (src / "baseline-v0.27-before-export-reuse/backend").glob("*.py")}
        for name, label in [("qa/v0.27/reports/first-20261031T101720-c6e32a.json", "baseline-v0.27-first"),
                            ("qa/v0.27/reports/adapted-20261031T102446-2dcf4f.json", "baseline-v0.27-before-content-review")]:
            report = json.loads((src / name).read_text())
            assert report["backend_hashes"] == {f.name: sha(f) for f in (src / label / "backend").glob("*.py")}
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["GUIYU_DATA_DIR"] = str(base / "isolated-data")
        output = run([os.sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], src, "unit", env)
        count = int(re.search(r"Ran (\d+) tests", output)[1])
        assert count == 741
        replay = json.loads(run([os.sys.executable, "scripts/check_delivery_reuse_v27.py"], src, "export-replay", env))
        assert replay["passed"] and replay["backend_hashes"] == protocol["backend_hashes"]
        run(["/bin/zsh", "scripts/check_native.sh"], src, "native", env)
        shipped = demo / "dist/Guiyu-0.27.1.app"
        shipped_checks = probe(shipped, demo, "shipped", env)
        run(["/bin/zsh", "scripts/build_model_demo_v27_1.sh"], src, "build", env)
        rebuilt = src / "dist/Guiyu-0.27.1.app"
        rebuilt_checks = probe(rebuilt, src, "rebuilt", env)
        for app in (shipped, rebuilt):
            assert protocol["backend_hashes"] == {f.name: sha(f) for f in (app / "Contents/Resources").glob("*.py")}
            assert sha(app / "Contents/Resources/model-catalog.json") == sha(src / "packaging/model-catalog.json")
            showcase = app / "Contents/Resources/submission-showcase"
            assert len(list(showcase.iterdir())) == 4
            assert all(sha(f) == sha(src / "fixtures/submission_v27/workspace" / f.name) for f in showcase.iterdir())
        native = json.loads((src / "qa/v0.27.1/native-evaluation.json").read_text())
        assert native["passed"] == native["total"] == 6 and native["backend_hashes"] == protocol["backend_hashes"]
        assert native["source_mutations"] is False
        assert json.loads((src / "qa/v0.27.1/format-reuse-regression.json").read_text())["passed"]
        assert json.loads((src / "qa/v0.27.1/materials-validation.json").read_text())["passed"]
    result = {"version": "0.27.1", "status": "PASS_PUBLICATION_ARCHIVES_EXTRACTED_SOURCE_TESTS_NATIVE_REBUILD_AND_PRIVACY_PROBES",
              "unit_tests": count, "shipped_app": shipped_checks, "independently_rebuilt_app": rebuilt_checks,
              "portable_office_agent_xlsx_word_replay": True,
              "all_archive_crcs_and_hashes_verified": True, "historical_source_snapshots_verified": True,
              "four_bundled_fictional_sources_match": True, "normal_user_data_not_opened": True,
              "native_passed": native["passed"],
              "native_execution": "qa/v0.27.1/native-evaluation.json; actual native execution of six known fictional goals; failures preserved separately."}
    (ROOT / "qa/v0.27.1/delivery-checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
