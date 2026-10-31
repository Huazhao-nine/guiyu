#!/bin/zsh
set -eu
TASK_ROOT="${0:A:h:h}"
swiftc -module-cache-path "$TASK_ROOT/.build/ModuleCache" -swift-version 5 -O \
  "$TASK_ROOT/Sources/Guiyu/QueryModels.swift" "$TASK_ROOT/Sources/Guiyu/PrimaryModel.swift" "$TASK_ROOT/Sources/Guiyu/DevicePolicy.swift" \
  "$TASK_ROOT/Sources/Shared/ModelCatalog.swift" "$TASK_ROOT/tests/native_model_preparation_v25.swift" \
  -o "$TASK_ROOT/.build/model-preparation-v25"
"$TASK_ROOT/.build/model-preparation-v25" \
  "$TASK_ROOT/dist/Guiyu-0.25.0.app/Contents/Resources/model-catalog.json" \
  "$HOME/Library/Application Support/GuiyuModels/Research/qwen3.6-35b-a3b"
