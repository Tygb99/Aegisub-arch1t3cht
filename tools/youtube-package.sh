#!/bin/bash
set -euo pipefail
TASK_ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$TASK_ROOT"
if [[ "${1:-}" != "--reuse-core" ]]; then
    bash tools/macos-arm64-build.sh
    PATH="$TASK_ROOT/.deps/wx/bin:$TASK_ROOT/.venv/bin:$PATH" .venv/bin/meson compile -C build-arm64 osx-bundle
fi
bash tools/youtube-build.sh
STAMP=$(date +%Y-%m-%d-%H-%M-%S)
DELIVERY="$TASK_ROOT/artifacts/$STAMP-aegisub-youtube-arm64"
APP="$DELIVERY/Aegisub YouTube.app"
mkdir -p "$DELIVERY"
ditto build-arm64/Aegisub.app "$APP"
ditto build-youtube "$APP/Contents/MacOS/youtube"
/usr/libexec/PlistBuddy -c 'Set :CFBundleIdentifier com.aegisub.youtube-preview' "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :CFBundleName Aegisub YouTube' "$APP/Contents/Info.plist"
codesign --force --deep --sign - "$APP"
.venv/bin/python tools/macos-arm64-audit.py "$APP" --output "$DELIVERY/arm64-audit.json"
env -u DOTNET_ROOT PATH=/usr/bin:/bin "$APP/Contents/MacOS/youtube/aegisub-youtube" --help
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
mkdir -p "$DELIVERY/Source/artifacts/screenshots" "$DELIVERY/Source/artifacts/logs"
cp artifacts/youtube-regression-final.json "$DELIVERY/Source/artifacts/"
cp "$DELIVERY/arm64-audit.json" "$DELIVERY/Source/artifacts/arm64-youtube-audit.json"
ditto artifacts/player-final-evidence "$DELIVERY/Source/artifacts/player-final-evidence"
cp artifacts/screenshots/capture-metadata.json "$DELIVERY/Source/artifacts/screenshots/"
for capture in artifacts/screenshots/final-*.jpg; do
    [[ ! -f "$capture" ]] || cp "$capture" "$DELIVERY/Source/artifacts/screenshots/"
done
for log in artifacts/logs/final-existing-tests.log artifacts/logs/youtube-regression-final.log artifacts/*diagnostics-locale.log; do
    [[ ! -f "$log" ]] || cp "$log" "$DELIVERY/Source/$log"
done
for document in docs/*youtube-guide*.md docs/*youtube-verification*.md; do
    if [[ -f "$document" ]]; then
        cp "$document" "$DELIVERY/Source/docs/"
        sed 's#](../#](Source/#g' "$document" > "$DELIVERY/$(basename "$document")"
    fi
done
ditto -c -k --sequesterRsrc --keepParent "$DELIVERY" "$DELIVERY.zip"
shasum -a 256 "$DELIVERY.zip" > "$DELIVERY.zip.sha256"
echo "$DELIVERY"
