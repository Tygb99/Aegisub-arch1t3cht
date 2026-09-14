#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
SHA=b186a40bc21e58a8c9651cf616cbb5e80425dfc6
SOURCE=".deps/src/YTSubConverter-$SHA"
mkdir -p .deps/src build-youtube
if ! test -d "$SOURCE"; then
    curl -fL "https://github.com/arcusmaximus/YTSubConverter/archive/$SHA.tar.gz" -o .deps/src/ytsubconverter.tar.gz
    echo '9ef9a800669ce64cb5249bd662d898b95715e9af443aecbbeed1806f6983ad69  .deps/src/ytsubconverter.tar.gz' | shasum -a 256 -c -
    tar -xf .deps/src/ytsubconverter.tar.gz -C .deps/src
fi
PATCHED="$ROOT/tools/youtube/obj/upstream"
mkdir -p "$PATCHED/YTSubConverter.Shared"
rsync -a --delete --exclude bin --exclude obj "$SOURCE/YTSubConverter.Shared/" "$PATCHED/YTSubConverter.Shared/"
echo 'b7c89b0744bf16e1997ca3ac3036a925a90c94ef6f7b0570950784e2b23390cf  tools/youtube/patches/independent-justification.patch' | shasum -a 256 -c -
patch --batch --forward -p1 -d "$PATCHED" < tools/youtube/patches/independent-justification.patch
patch --batch --forward -p1 -d "$PATCHED" < tools/youtube/patches/ass-justification.patch
cp tools/youtube/upstream-support/AssJustificationTagHandler.cs "$PATCHED/YTSubConverter.Shared/Formats/Ass/Tags/"
(cd tools/youtube && dotnet publish Aegisub.Youtube.csproj -c Release -r osx-arm64 --self-contained true -o "$ROOT/build-youtube")
RUNTIME=.deps/dotnet-runtime-10.0.9
if ! test -d "$RUNTIME"; then
    curl -fL 'https://builds.dotnet.microsoft.com/dotnet/Runtime/10.0.9/dotnet-runtime-10.0.9-osx-arm64.tar.gz' -o .deps/src/dotnet-runtime-10.0.9-osx-arm64.tar.gz
    echo 'e8aac8c57d2015af8ba3f09a9a887bd4692da1725fb15c355280712169cb9b504502cab4dcddaf2d13be97329dc5527813bceea65fbfbce589215be4f1597ceb  .deps/src/dotnet-runtime-10.0.9-osx-arm64.tar.gz' | shasum -a 512 -c -
    mkdir -p "$RUNTIME"
    tar -xf .deps/src/dotnet-runtime-10.0.9-osx-arm64.tar.gz -C "$RUNTIME"
fi
cp -R "$RUNTIME/shared/Microsoft.NETCore.App/10.0.9/." build-youtube/
cp "$RUNTIME/host/fxr/10.0.9/libhostfxr.dylib" build-youtube/
clang -arch arm64 -dynamiclib -fobjc-arc -framework AppKit tools/youtube/text-measurer.m -o build-youtube/libaegisub-text.dylib
for library in build-youtube/*.dylib; do
    install_name_tool -id "@rpath/$(basename "$library")" "$library"
    codesign --force --sign - "$library"
done
cp "$SOURCE/LICENSE" build-youtube/YTSubConverter-LICENSE
curl -fL 'https://raw.githubusercontent.com/dotnet/runtime/v10.0.9/LICENSE.TXT' -o build-youtube/DOTNET-LICENSE.txt
curl -fL 'https://raw.githubusercontent.com/dotnet/runtime/v10.0.9/THIRD-PARTY-NOTICES.TXT' -o build-youtube/DOTNET-THIRD-PARTY-NOTICES.txt
build-youtube/aegisub-youtube --help
