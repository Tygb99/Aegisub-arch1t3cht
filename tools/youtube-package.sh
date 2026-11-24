#!/bin/bash
set -euo pipefail
TASK_ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$TASK_ROOT"
if [[ "${1:-}" != "--reuse-core" ]]; then
    meson compile -C build
    AEGISUB_BUNDLE_SIGNATURE=- meson compile -C build osx-bundle
fi
bash tools/youtube-build.sh
STAMP=$(date +%Y-%m-%d-%H-%M-%S)
DELIVERY="$TASK_ROOT/artifacts/$STAMP-aegisub-youtube-arm64"
APP="$DELIVERY/Aegisub YouTube.app"
mkdir -p "$DELIVERY"
ditto build/Aegisub.app "$APP"
ditto build-youtube "$APP/Contents/MacOS/youtube"
/usr/libexec/PlistBuddy -c 'Set :CFBundleIdentifier com.aegisub.youtube-preview' "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :CFBundleName Aegisub YouTube' "$APP/Contents/Info.plist"
codesign --force --deep --sign - "$APP"
env -u DOTNET_ROOT PATH=/usr/bin:/bin "$APP/Contents/MacOS/youtube/aegisub-youtube" --help
mkdir -p artifacts/logs
ruby tools/youtube-test.rb "$APP/Contents/MacOS/youtube/aegisub-youtube" > artifacts/logs/youtube-regression-final.log
RESULTS=$(tail -1 artifacts/logs/youtube-regression-final.log)
cp "$RESULTS/results.json" artifacts/youtube-regression-final.json
ditto tests/youtube-fixtures "$DELIVERY/Samples"
mkdir -p "$DELIVERY/Source"
git archive HEAD | tar -x -C "$DELIVERY/Source"
while IFS= read -r -d '' changed; do
    if [[ -f "$changed" ]]; then
        mkdir -p "$DELIVERY/Source/$(dirname "$changed")"
        cp "$changed" "$DELIVERY/Source/$changed"
    fi
done < <(git diff --name-only -z HEAD)
cp src/dialog_youtube* src/youtube_diagnostics.cpp src/youtube_process.h "$DELIVERY/Source/src/"
cp tools/youtube-build.sh tools/youtube-build.ps1 tools/youtube-package.sh tools/youtube-test.rb "$DELIVERY/Source/tools/"
rsync -a --exclude bin --exclude obj tools/youtube/ "$DELIVERY/Source/tools/youtube/"
ditto tests/youtube-fixtures "$DELIVERY/Source/tests/youtube-fixtures"
mkdir -p "$DELIVERY/Source/artifacts/logs"
cp artifacts/youtube-regression-final.json "$DELIVERY/Source/artifacts/"
cp artifacts/logs/youtube-regression-final.log "$DELIVERY/Source/artifacts/logs/"
ditto .deps/src/YTSubConverter-b186a40bc21e58a8c9651cf616cbb5e80425dfc6 "$DELIVERY/Source/YTSubConverter"
for document in docs/*youtube-guide*.md docs/*youtube-verification*.md; do
    if [[ -f "$document" ]]; then
        cp "$document" "$DELIVERY/Source/docs/"
        sed 's#](../#](Source/#g' "$document" > "$DELIVERY/$(basename "$document")"
    fi
done
ditto -c -k --sequesterRsrc --keepParent "$DELIVERY" "$DELIVERY.zip"
shasum -a 256 "$DELIVERY.zip" > "$DELIVERY.zip.sha256"
echo "$DELIVERY"
