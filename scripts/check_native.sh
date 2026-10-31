#!/bin/zsh
set -eu
TASK_ROOT="${0:A:h:h}"
export CLANG_MODULE_CACHE_PATH="$TASK_ROOT/.build/ModuleCache"
mkdir -p "$CLANG_MODULE_CACHE_PATH"
mkdir -p "$TASK_ROOT/.build"
swiftc -module-cache-path "$CLANG_MODULE_CACHE_PATH" -swift-version 5 \
  "$TASK_ROOT"/Sources/Guiyu/{ShareDeliveryView,Models,PrimaryModel,DevicePolicy,AgentModels,QueryModels,Store,WorkspaceModels,WorkspaceStore,ModelDownloadStore,WorkspaceIndexStore,WorkspaceIndexModels,PersonalModels,PersonalStore}.swift \
  "$TASK_ROOT/Sources/Shared/ModelCatalog.swift" "$TASK_ROOT/tests/native_workspace_checks.swift" \
  -o "$TASK_ROOT/.build/native-workspace-checks" -framework AppKit -framework SwiftUI -framework CoreServices
"$TASK_ROOT/.build/native-workspace-checks"

swiftc -module-cache-path "$CLANG_MODULE_CACHE_PATH" -swift-version 5 \
  "$TASK_ROOT/Sources/Guiyu/PrivacyScanWorker.swift" "$TASK_ROOT/tests/privacy_scan_checks.swift" \
  -o "$TASK_ROOT/.build/privacy-scan-checks" -framework Foundation -framework Combine
"$TASK_ROOT/.build/privacy-scan-checks"

swiftc -module-cache-path "$CLANG_MODULE_CACHE_PATH" -swift-version 5 \
  "$TASK_ROOT/Sources/Guiyu/MessageEditor.swift" "$TASK_ROOT/tests/message_editor_checks.swift" \
  -o "$TASK_ROOT/.build/message-editor-checks" -framework AppKit -framework SwiftUI
"$TASK_ROOT/.build/message-editor-checks"
