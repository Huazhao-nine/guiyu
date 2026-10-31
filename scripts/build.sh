#!/bin/zsh
set -eu
TASK_ROOT="${0:A:h:h}"
export CLANG_MODULE_CACHE_PATH="$TASK_ROOT/.build/ModuleCache"
mkdir -p "$CLANG_MODULE_CACHE_PATH"
APP_DIR="${GUIYU_APP_OUTPUT:-$TASK_ROOT/dist/Guiyu-0.27.0.app}"
APP_VERSION="${GUIYU_APP_VERSION:-0.27.0}"
APP_BUILD="${GUIYU_APP_BUILD:-27}"
[[ "$APP_DIR" == /*.app && "$APP_VERSION" =~ '^[0-9]+\.[0-9]+\.[0-9]+$' && "$APP_BUILD" =~ '^[0-9]+$' ]] || { print '构建输出或版本无效'; exit 1; }
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp "$TASK_ROOT/assets/Guiyu.icns" "$APP_DIR/Contents/Resources/AppIcon.icns"
cp "$TASK_ROOT"/backend/*.py "$APP_DIR/Contents/Resources/"
mkdir -p "$APP_DIR/Contents/Resources/demo"
cp "$TASK_ROOT"/fixtures/demo/*.txt "$APP_DIR/Contents/Resources/demo/"
mkdir -p "$APP_DIR/Contents/Resources/office"
cp "$TASK_ROOT"/fixtures/office/* "$APP_DIR/Contents/Resources/office/"
mkdir -p "$APP_DIR/Contents/Resources/query"
cp "$TASK_ROOT"/fixtures/query/* "$APP_DIR/Contents/Resources/query/"
mkdir -p "$APP_DIR/Contents/Resources/personal"
cp "$TASK_ROOT"/fixtures/personal/* "$APP_DIR/Contents/Resources/personal/"
mkdir -p "$APP_DIR/Contents/Resources/office-showcase"
cp -R "$TASK_ROOT/fixtures/office_showcase/workspace/" "$APP_DIR/Contents/Resources/office-showcase/"
cp "$TASK_ROOT/fixtures/office_showcase/tasks.json" "$APP_DIR/Contents/Resources/office-showcase-tasks.json"
mkdir -p "$APP_DIR/Contents/Resources/composed-showcase"
cp "$TASK_ROOT"/fixtures/composed/workspace/* "$APP_DIR/Contents/Resources/composed-showcase/"
mkdir -p "$APP_DIR/Contents/Resources/share-showcase"
cp "$TASK_ROOT"/fixtures/share/workspace/* "$APP_DIR/Contents/Resources/share-showcase/"
mkdir -p "$APP_DIR/Contents/Resources/roster-showcase"
cp "$TASK_ROOT"/fixtures/roster/workspace/* "$APP_DIR/Contents/Resources/roster-showcase/"
mkdir -p "$APP_DIR/Contents/Resources/workbook-showcase"
cp "$TASK_ROOT"/fixtures/workbook_general/workspace/* "$APP_DIR/Contents/Resources/workbook-showcase/"
mkdir -p "$APP_DIR/Contents/Resources/novel-office-showcase"
for example in 公开台账_虚构填报.xlsx 公开报价_虚构填报.xlsx 服务记录.xlsx 读书会方案.md 读书会变更记录.txt; do
    cp "$TASK_ROOT/fixtures/office_novel_v26/workspace/$example" "$APP_DIR/Contents/Resources/novel-office-showcase/"
done
mkdir -p "$APP_DIR/Contents/Resources/submission-showcase"
for example in 支持日志.xlsx 共享工位安排.md 共享工位最新通知.txt 客户跟进纪要.md; do
    cp "$TASK_ROOT/fixtures/submission_v27/workspace/$example" "$APP_DIR/Contents/Resources/submission-showcase/"
done
swiftc -module-cache-path "$CLANG_MODULE_CACHE_PATH" -swift-version 5 -O -target arm64-apple-macosx14.0 \
  "$TASK_ROOT"/Sources/Guiyu/*.swift "$TASK_ROOT"/Sources/Shared/*.swift \
  -o "$APP_DIR/Contents/MacOS/Guiyu" \
  -framework SwiftUI -framework AppKit -framework UniformTypeIdentifiers
cp "$TASK_ROOT/packaging/model-catalog.json" "$APP_DIR/Contents/Resources/"
HELPER_DIR="$APP_DIR/Contents/Helpers/GuiyuModelDownloader.app"
mkdir -p "$HELPER_DIR/Contents/MacOS" "$HELPER_DIR/Contents/Resources"
cp "$TASK_ROOT/packaging/model-catalog.json" "$HELPER_DIR/Contents/Resources/"
swiftc -module-cache-path "$CLANG_MODULE_CACHE_PATH" -swift-version 5 -O -target arm64-apple-macosx14.0 \
  "$TASK_ROOT"/Sources/ModelDownloader/main.swift "$TASK_ROOT"/Sources/Shared/*.swift \
  -o "$HELPER_DIR/Contents/MacOS/GuiyuModelDownloader" -framework AppKit -framework CryptoKit
cat > "$HELPER_DIR/Contents/Info.plist" <<'HELPER'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>归屿模型下载</string>
<key>CFBundleIdentifier</key><string>org.guiyu.modeldownloader</string>
<key>CFBundleExecutable</key><string>GuiyuModelDownloader</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.22.0</string>
<key>LSUIElement</key><true/>
<key>LSMinimumSystemVersion</key><string>14.0</string>
</dict></plist>
HELPER
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$HELPER_DIR/Contents/Info.plist"
codesign --force --sign - "$HELPER_DIR"
cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>归屿</string>
<key>CFBundleDisplayName</key><string>归屿</string>
<key>CFBundleIdentifier</key><string>org.guiyu.localdemo</string>
<key>CFBundleExecutable</key><string>Guiyu</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.22.0</string>
<key>CFBundleVersion</key><string>22</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSDesktopFolderUsageDescription</key><string>读取你选作工作区的桌面文件夹，在本机查找和处理资料。原文件修改前会先预览。</string>
<key>NSDocumentsFolderUsageDescription</key><string>读取你选作工作区的文稿文件夹，在本机查找和处理资料。原文件修改前会先预览。</string>
<key>NSDownloadsFolderUsageDescription</key><string>读取你选作工作区的下载文件夹，在本机查找和处理资料。原文件修改前会先预览。</string>
<key>NSHumanReadableCopyright</key><string>Copyright 2026 Huazhao. Apache 2.0.</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>NSPrincipalClass</key><string>NSApplication</string>
</dict></plist>
PLIST
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$APP_DIR/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_BUILD" "$APP_DIR/Contents/Info.plist"
rm -rf "$APP_DIR/Contents/Resources/__pycache__"
codesign --force --sign - "$APP_DIR"
print "BUILD_READY $APP_DIR"
