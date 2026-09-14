#!/bin/bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
wx_config=${SCINTILLA_IME_WX_CONFIG:-"$root/.deps/wx/bin/wx-config"}
scratch=$(mktemp -d "${TMPDIR:-/tmp}/scintilla-ime.XXXXXX")
cleanup() {
  local result=$?
  find "$scratch" -depth -type f -exec unlink {} \;
  find "$scratch" -depth -type d -exec rmdir {} \;
  exit "$result"
}
trap cleanup EXIT

if [[ -n ${SCINTILLA_IME_REVISION:-} ]]; then
  git -C "$root" show "$SCINTILLA_IME_REVISION:src/osx/scintilla_ime.mm" > "$scratch/bridge.mm"
else
  cp "${SCINTILLA_IME_SOURCE:-$root/src/osx/scintilla_ime.mm}" "$scratch/bridge.mm"
fi
printf 'source_revision=%s source_file=%s wx_version=%s\n' "${SCINTILLA_IME_REVISION:-working-tree}" "${SCINTILLA_IME_SOURCE:-$root/src/osx/scintilla_ime.mm}" "$("$wx_config" --version)"
shasum -a 256 "$scratch/bridge.mm" "$root/tests/osx/scintilla_ime.mm"
printf 'CXXFLAGS=%s\n' "${CXXFLAGS:-}"
cxxflags=()
read -r -a cxxflags <<< "$("$wx_config" --cxxflags)"
libraries=()
read -r -a libraries <<< "$("$wx_config" --libs std,stc)"
extra_flags=()
read -r -a extra_flags <<< "${CXXFLAGS:-}"
"${CXX:-c++}" -std=c++17 -O0 -arch arm64 -fno-objc-arc -Wall -Wextra \
  "${cxxflags[@]}" ${extra_flags[@]+"${extra_flags[@]}"} "$root/tests/osx/scintilla_ime.mm" "$scratch/bridge.mm" \
  "${libraries[@]}" -Wl,-dead_strip -o "$scratch/scintilla_ime"
xcrun lldb --batch --no-lldbinit \
  -o 'settings set auto-confirm true' -o run \
  -k 'thread backtrace all' -k 'quit 1' \
  -o 'script p = lldb.debugger.GetSelectedTarget().GetProcess(); lldb.debugger.HandleCommand("quit %d" % (p.GetExitStatus() if p.GetState() == lldb.eStateExited else 1))' \
  -- "$scratch/scintilla_ime" "$@"
