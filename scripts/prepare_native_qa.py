#!/usr/bin/env python3
"""Prepare an isolated, signed native QA bundle without launching it.

Only the built app, bundled fictional examples, and installed-model metadata
are used. Existing QA app/data/example folders are never overwritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashes(directory):
    return {p.relative_to(directory).as_posix(): digest(p)
            for p in sorted(directory.rglob("*")) if p.is_file()}


def executable_sections(path):
    """Hash file-backed Mach-O sections, excluding the replaceable signature."""
    image = path.read_bytes()
    if struct.unpack_from("<I", image)[0] != 0xFEEDFACF:
        raise ValueError("Expected an Apple Silicon 64-bit Mach-O executable")
    count = struct.unpack_from("<I", image, 16)[0]
    position, result = 32, {}
    for _ in range(count):
        command, size = struct.unpack_from("<II", image, position)
        if command == 0x19:  # LC_SEGMENT_64
            section_count = struct.unpack_from("<I", image, position + 64)[0]
            for i in range(section_count):
                section = position + 72 + i * 80
                name = image[section:section + 16].rstrip(b"\0").decode()
                segment = image[section + 16:section + 32].rstrip(b"\0").decode()
                length = struct.unpack_from("<Q", image, section + 40)[0]
                offset = struct.unpack_from("<I", image, section + 48)[0]
                section_type = struct.unpack_from("<I", image, section + 64)[0] & 0xFF
                if section_type not in (0x1, 0xC, 0x12) and length:
                    if offset + length > len(image):
                        raise ValueError("Invalid Mach-O section bounds")
                    result[segment + "/" + name] = hashlib.sha256(image[offset:offset + length]).hexdigest()
        position += size
    if not result:
        raise ValueError("Expected file-backed Mach-O sections")
    return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="release version, e.g. 0.12")
    parser.add_argument("--temporary-data",action="store_true",help="Use an isolated temporary data/examples root for ad-hoc QA bundles.")
    parser.add_argument("--source-app",type=Path,help="Explicit built app to copy; never changes or launches the source app.")
    args = parser.parse_args()
    if not re.fullmatch(r"0\.[1-9][0-9]*", args.version):
        parser.error("--version must have the form 0.12")
    os.umask(0o077)
    qa = ROOT / "qa/private" / ("v" + args.version)
    source = args.source_app.resolve() if args.source_app else ROOT / "dist/Guiyu.app"
    app = qa / "GuiyuQA.app"
    data_root=Path(tempfile.mkdtemp(prefix="guiyu-native-v"+args.version+"-")) if args.temporary_data else qa
    data = data_root / "gui"
    examples = data_root / "GuiyuExamples"
    setup = qa / "setup.json"
    for target in (app, data, examples, setup):
        if target.exists() or target.is_symlink():
            raise SystemExit(f"Preserving existing QA state; destination exists: {target}")
    with (source / "Contents/Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    if info["CFBundleShortVersionString"] != args.version + ".0":
        raise SystemExit("Built app version does not match requested QA version")
    resources = source / "Contents/Resources"
    backend_hashes = {p.name: digest(p) for p in sorted((ROOT / "backend").glob("*.py"))}
    if any(not (resources / name).is_file() or digest(resources / name) != value
           for name, value in backend_hashes.items()):
        raise SystemExit("Built app backend differs from source; build it before QA preparation")
    if any(p.name == "history.json" or p.suffix == ".safetensors"
           for p in source.rglob("*") if p.is_file()):
        raise SystemExit("Built app unexpectedly contains history or model weights")
    model_id="qwen3.6-35b-a3b"
    storage=Path.home()/"Library/Application Support/GuiyuModels"
    model=next((storage/kind/model_id for kind in ("Installed","Research") if (storage/kind/model_id/"guiyu-install.json").is_file()),storage/"Installed"/model_id)
    config = json.loads((model / "config.json").read_text())
    weights = list(model.glob("*.safetensors"))
    if not weights or any(p.is_symlink() for p in weights) or not (model / "tokenizer_config.json").is_file():
        raise SystemExit("A prepared local Qwen3.6 35B A3B model is required; no downloads are performed")
    bundled_examples = resources / "office-showcase"
    original_hashes = hashes(bundled_examples)
    if len(original_hashes) != 18 or original_hashes != hashes(ROOT / "fixtures/office_showcase/workspace"):
        raise SystemExit("Expected 18 unchanged fictional office files in the built app")
    workspace_id = str(uuid.uuid4()).upper()
    workspace = examples / workspace_id / "日常办公示例"
    workspace_data = data / "Workspaces" / workspace_id
    qa.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, app, symlinks=True)
    copied_executable_matches = digest(app / "Contents/MacOS/Guiyu") == digest(source / "Contents/MacOS/Guiyu")
    info["CFBundleIdentifier"] = "org.guiyu.qa.v" + args.version.split(".")[1]
    info["CFBundleName"] = info["CFBundleDisplayName"] = "归屿验收"
    info["LSEnvironment"] = {"GUIYU_DATA_DIR": str(data)}
    with (app / "Contents/Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)
    shutil.copytree(bundled_examples, workspace)
    workspace_data.mkdir(parents=True)
    quantization = config.get("quantization", config.get("quantization_config", {}))
    registered_model = {"id": model_id, "name": "Qwen3.6 35B A3B", "path": str(model),
                        "architecture": config["model_type"], "bits": quantization.get("bits"),
                        "bytes": sum(p.stat().st_size for p in weights)}
    write_json(data / "local-models.json", {"models": [registered_model], "selectedID": model_id})
    write_json(data / "workspaces.json", {"selectedID": workspace_id, "workspaces": [
        {"id": workspace_id, "name": "日常办公示例", "path": str(workspace)}]})
    write_json(workspace_data / "scope.json", {"paths": [], "automatic": True, "indexPaused": True})
    write_json(workspace_data / "history.json", [])
    for marker, text in (("office-showcase-v0.9", workspace_id), ("primary-32gb-v0.25", model_id), ("welcomed", "")):
        (data / marker).write_text(text)
    (workspace_data / "workspace-initialized").touch()
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(app)], check=True)
    subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    checks = {
        "separate_bundle_id": info["CFBundleIdentifier"] != "org.guiyu.localdemo",
        "isolated_environment": info["LSEnvironment"]["GUIYU_DATA_DIR"] == str(data),
        "18_fictional_files_unchanged": hashes(workspace) == original_hashes,
        "empty_history": json.loads((workspace_data / "history.json").read_text()) == [],
        "index_initially_paused": json.loads((workspace_data / "scope.json").read_text())["indexPaused"],
        "copied_executable_matches_dist_before_signing": copied_executable_matches,
        "signed_executable_sections_match_dist": executable_sections(app / "Contents/MacOS/Guiyu") == executable_sections(source / "Contents/MacOS/Guiyu"),
        "backend_matches_source": all(digest(app / "Contents/Resources" / k) == v for k, v in backend_hashes.items()),
        "signed_bundle_verified": True,
        "no_user_history_or_preferences_copied": True,
        "app_not_launched": True,
    }
    result = {"version": args.version + ".0", "app": str(app), "data": str(data),
              "bundle_id": info["CFBundleIdentifier"], "workspace_id": workspace_id,
              "workspace": str(workspace), "model_id": model_id,
              "original_hashes": original_hashes, "backend_hashes": backend_hashes,
              "dist_executable_sha256": digest(source / "Contents/MacOS/Guiyu"),
              "executable_sha256": digest(app / "Contents/MacOS/Guiyu"), "checks": checks}
    write_json(setup, result)
    print(json.dumps({k: v for k, v in result.items() if not k.endswith("hashes")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
