#!/bin/zsh
set -eu
TASK_ROOT="${0:A:h}"
cd "$TASK_ROOT"
UV_BIN="$(command -v uv || true)"
if [[ -z "$UV_BIN" && -x /opt/homebrew/bin/uv ]]; then UV_BIN=/opt/homebrew/bin/uv; fi
if [[ -z "$UV_BIN" ]]; then
  print '请先从 https://docs.astral.sh/uv/getting-started/installation/ 安装 uv，再打开本文件。'
  exit 1
fi
if [[ "$(uname -m)" != arm64 ]]; then print '当前 Demo 面向 Apple 芯片 Mac。'; exit 1; fi
if (( $(/usr/sbin/sysctl -n hw.memsize) < 34359738368 )); then print '当前默认模型需要至少 32 GB 内存。'; exit 1; fi
RUNTIME_DIR="$HOME/Library/Application Support/GuiyuRuntime"
mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"
print '正在准备本地运行环境。此阶段只下载程序和模型，不读取你的任务资料。'
if [[ ! -x "$RUNTIME_DIR/python/bin/python" ]]; then
  "$UV_BIN" venv --python 3.13 "$RUNTIME_DIR/python"
fi
"$UV_BIN" pip sync --python "$RUNTIME_DIR/python/bin/python" "$TASK_ROOT/requirements.lock"
"$RUNTIME_DIR/python/bin/python" "$TASK_ROOT/scripts/prepare_model.py" --root "$TASK_ROOT" --runtime "$RUNTIME_DIR"
if [[ ! -x "$TASK_ROOT/dist/Guiyu-0.27.0.app/Contents/MacOS/Guiyu" ]]; then zsh "$TASK_ROOT/scripts/build.sh"; fi
"$TASK_ROOT/dist/Guiyu-0.27.0.app/Contents/MacOS/Guiyu" --privacy-probe
print '准备完成。现在可以双击「打开归屿.command」，以后处理资料无需联网。'
