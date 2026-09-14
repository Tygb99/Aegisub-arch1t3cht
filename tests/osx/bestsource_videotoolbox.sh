#!/bin/bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
build=${BESTSOURCE_BUILD_DIR:-"$root/build-arm64"}
ffmpeg=${BESTSOURCE_FFMPEG_PREFIX:-"$root/.deps/ffmpeg"}
scratch=$(mktemp -d "${TMPDIR:-/tmp}/bestsource-videotoolbox.XXXXXX")
trap 'rm -rf "$scratch"' EXIT
export PKG_CONFIG_PATH="$ffmpeg/lib/pkgconfig:/opt/homebrew/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"

flags=()
read -r -a flags <<< "$(pkg-config --cflags --libs libavformat libavcodec libavutil libswscale libxxhash)"
"${CXX:-c++}" -std=c++17 -O2 -g -Wall -Wextra \
  -I"$root/subprojects/bestsource/src" "$root/tests/osx/bestsource_videotoolbox.cpp" \
  "$build/subprojects/bestsource/libbestsource.a" "$build/subprojects/bestsource/libp2p_main.a" \
  "${flags[@]}" -Wl,-rpath,"$ffmpeg/lib" -o "$scratch/bestsource_videotoolbox"
"$scratch/bestsource_videotoolbox" "$@"
