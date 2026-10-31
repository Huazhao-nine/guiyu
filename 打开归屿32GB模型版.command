#!/bin/zsh
set -eu
TASK_ROOT="${0:A:h}"
if pgrep -x Guiyu >/dev/null; then
  print '请先退出当前打开的归屿，再打开32GB模型版。工作记录会继续保存在本机。'
  exit 0
fi
if [[ ! -x "$TASK_ROOT/dist/Guiyu-0.27.0.app/Contents/MacOS/Guiyu" ]]; then
  print '请先运行 scripts/build_model_demo_v27.sh。'
  exit 1
fi
open "$TASK_ROOT/dist/Guiyu-0.27.0.app"
