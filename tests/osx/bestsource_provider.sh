#!/bin/bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
build=${BESTSOURCE_BUILD_DIR:-"$root/build-arm64"}
ffmpeg=${BESTSOURCE_FFMPEG_PREFIX:-"$root/.deps/ffmpeg"}
wx_config=${BESTSOURCE_WX_CONFIG:-wx-config}
movie=${1:-}
if [[ -n "$movie" && "$movie" != --help && "$movie" != /* ]]; then movie="$PWD/$movie"; fi
scratch=$(mktemp -d "${TMPDIR:-/tmp}/bestsource-provider.XXXXXX")
trap 'rm -rf "$scratch"' EXIT
export PKG_CONFIG_PATH="$ffmpeg/lib/pkgconfig:/opt/homebrew/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"

args=()
while IFS= read -r -d '' arg; do args+=("$arg"); done < <(
  jq -r '.[] | select(.file | endswith("/video_provider_bestsource.cpp")) | .command' "$build/compile_commands.json" |
  perl -MText::ParseWords=shellwords -e '
    @args = shellwords(<>); shift @args;
    while (@args) {
      $arg = shift @args;
      if ($arg =~ /^(?:-o|-MF|-MQ)$/) { shift @args; next; }
      next if $arg =~ /^(?:-c|-MD)$/ || $arg =~ /video_provider_bestsource.cpp$/;
      print "$arg\0";
    }'
)
cd "$build"
"${CXX:-c++}" "${args[@]}" -c "$root/src/video_provider_bestsource.cpp" -o "$scratch/provider.o"
"${CXX:-c++}" "${args[@]}" -c "$root/tests/osx/bestsource_provider.cpp" -o "$scratch/driver.o"
flags=()
read -r -a flags <<< "$(pkg-config --libs libavformat libavcodec libavutil libswscale libxxhash)"
wxlibs=()
read -r -a wxlibs <<< "$("$wx_config" --libs)"
"${CXX:-c++}" "$scratch/provider.o" "$scratch/driver.o" \
  "$build/aegisub.p/src_video_provider_manager.cpp.o" "$build/aegisub.p/src_compat.cpp.o" \
  "$build/libaegisub/libaegisub.a" "$build/subprojects/bestsource/libbestsource.a" \
  "$build/subprojects/bestsource/libp2p_main.a" \
  "$build/subprojects/boost_1_83_0/libs/filesystem/libboost_filesystem.a" \
  "${flags[@]}" "${wxlibs[@]}" -Wl,-dead_strip -Wl,-rpath,"$ffmpeg/lib" -o "$scratch/bestsource_provider"
if [[ ${1:-} == --help ]]; then "$scratch/bestsource_provider" --help; exit; fi
"$scratch/bestsource_provider" "${movie:?Pass a test movie}" "$root/src/libresrc/osx/default_config.json" "$scratch"
