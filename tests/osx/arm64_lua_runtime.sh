#!/bin/bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
build=${AEGISUB_LUA_BUILD_DIR:-"$root/build-arm64"}
includes=${AEGISUB_LUA_INCLUDE_DIR:-"$build/automation/include"}
scratch=$(mktemp -d "${TMPDIR:-/tmp}/aegisub-arm64-lua.XXXXXX")
trap 'rm -rf "$scratch"' EXIT
export PKG_CONFIG_PATH="/opt/homebrew/opt/icu4c@78/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"

flags=()
read -r -a flags <<< "$(pkg-config --cflags --libs icu-i18n icu-uc)"
boost_libraries=()
for library in filesystem locale regex thread chrono; do
  boost_libraries+=("$build/subprojects/boost_1_83_0/libs/$library/libboost_$library.a")
done
"${CXX:-c++}" -std=c++17 -O2 -arch arm64 -Wall -Wextra -DBOOST_ALL_NO_LIB \
  -I"$root/libaegisub/include" -I"$root/subprojects/boost_1_83_0" \
  -I"$build/subprojects/luajit/src" -I"$root/subprojects/luajit/src" \
  "$root/tests/osx/arm64_lua_runtime.cpp" "$build/libaegisub/libaegisub.a" \
  "${boost_libraries[@]}" "$build/vendor/luabins/src/libluabins.a" \
  "$build/subprojects/luajit/src/libluajit.a" "${flags[@]}" -liconv \
  -Wl,-dead_strip -o "$scratch/arm64_lua_runtime"

if [[ ${1:-} == --help ]]; then "$scratch/arm64_lua_runtime" --help; exit; fi
if [[ $# -gt 0 ]]; then
  "$scratch/arm64_lua_runtime" "$includes" "$@"
else
  "$scratch/arm64_lua_runtime" "$includes" "$root/tests/osx/arm64_smoke_driver.lua" "$root/tests/osx/arm64_smoke.lua"
fi
