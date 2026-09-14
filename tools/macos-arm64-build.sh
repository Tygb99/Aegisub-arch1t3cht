#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
BUILD_DIR=${1:-build-arm64}
JOBS=${AEGISUB_JOBS:-8}
UV_BIN=$(command -v uv)
test "$(uname -m)" = arm64
test "$(sysctl -in sysctl.proc_translated 2>/dev/null || true)" != 1
test "$(brew --prefix)" = /opt/homebrew
export MACOSX_DEPLOYMENT_TARGET=26.0
export PATH="$ROOT/.deps/wx/bin:$ROOT/.venv/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PKG_CONFIG_PATH="$ROOT/.deps/ffmpeg/lib/pkgconfig:/opt/homebrew/opt/icu4c@78/lib/pkgconfig"
# BestSource R8 references the project's previous Bitbucket location.
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=url.https://github.com/sekrit-twc/.insteadOf
export GIT_CONFIG_VALUE_0=https://bitbucket.org/the-sekrit-twc/

if ! test -x .venv/bin/meson; then
    python3 -m venv .venv
    "$UV_BIN" pip install --python .venv/bin/python meson==1.7.2 ninja==1.13.0 cmake==3.31.6
fi

mkdir -p .deps/src artifacts/logs
if ! test -x .deps/wx/bin/wx-config; then
    WX_ARCHIVE=.deps/src/wxWidgets-3.2.9.tar.bz2
    if ! test -f "$WX_ARCHIVE"; then
        curl -fL https://github.com/wxWidgets/wxWidgets/releases/download/v3.2.9/wxWidgets-3.2.9.tar.bz2 -o "$WX_ARCHIVE"
    fi
    printf '%s  %s\n' fb90f9538bffd6a02edbf80037a0c14c2baf9f509feac8f76ab2a5e4321f112b "$WX_ARCHIVE" | shasum -a 256 -c -
    tar -xf "$WX_ARCHIVE" -C .deps/src
    mkdir -p .deps/src/wx-build
    (
        cd .deps/src/wx-build
        ../wxWidgets-3.2.9/configure --prefix="$ROOT/.deps/wx" \
            --with-osx_cocoa --disable-shared --enable-unicode --enable-stc \
            --with-opengl --disable-webview --without-libtiff --without-liblzma \
            --with-libpng=builtin --with-libjpeg=builtin --with-regex=builtin \
            --with-expat=builtin --with-zlib=builtin --disable-debug \
            --with-macosx-version-min=26.0 \
            CFLAGS='-arch arm64 -O2' CXXFLAGS='-arch arm64 -O2' LDFLAGS='-arch arm64'
        make -j"$JOBS"
        make install
    ) > artifacts/logs/wx-build-repro.log 2>&1
fi
test "$(wx-config --version)" = 3.2.9
if ! test -x .deps/ffmpeg/bin/ffmpeg; then
    ARCHIVE=.deps/src/ffmpeg-7.1.2.tar.xz
    if ! test -f "$ARCHIVE"; then
        curl -fL https://ffmpeg.org/releases/ffmpeg-7.1.2.tar.xz -o "$ARCHIVE"
    fi
    printf '%s  %s\n' 089bc60fb59d6aecc5d994ff530fd0dcb3ee39aa55867849a2bbc4e555f9c304 "$ARCHIVE" | shasum -a 256 -c -
    tar -xf "$ARCHIVE" -C .deps/src
    (
        cd .deps/src/ffmpeg-7.1.2
        ./configure --prefix="$ROOT/.deps/ffmpeg" --arch=aarch64 --target-os=darwin \
            --cc=clang --cxx=clang++ --enable-shared --disable-static \
            --disable-doc --disable-debug --disable-ffplay \
            --enable-videotoolbox --enable-audiotoolbox \
            --extra-cflags=-mmacosx-version-min=26.0 \
            --extra-ldflags=-mmacosx-version-min=26.0
        make -j"$JOBS"
        make install
    ) > artifacts/logs/ffmpeg-build-repro.log 2>&1
fi

test "$(pkg-config --modversion libavcodec)" = 61.19.101
test "$(lipo -archs .deps/ffmpeg/bin/ffmpeg)" = arm64
OPTIONS=(
    --buildtype=release -Ddefault_library=static -Dbuild_osx_bundle=true
    --force-fallback-for=ffms2,bestsource,luajit
    -Dlocal_boost=true -Dbestsource=enabled -Dffms2=enabled
    -Dportaudio=enabled -Ddefault_audio_output=PortAudio -Dfftw3=enabled
    -Dhunspell=enabled -Duchardet=enabled -Dvapoursynth=disabled
    -Davisynth=disabled -Dopenal=disabled -Dlibpulse=disabled -Dalsa=disabled
    '-Dc_args=-arch arm64 -mmacosx-version-min=26.0'
    '-Dcpp_args=-arch arm64 -mmacosx-version-min=26.0'
    '-Dobjc_args=-arch arm64 -mmacosx-version-min=26.0'
    '-Dobjcpp_args=-arch arm64 -mmacosx-version-min=26.0'
    '-Dc_link_args=-arch arm64 -mmacosx-version-min=26.0'
    '-Dcpp_link_args=-arch arm64 -mmacosx-version-min=26.0'
    '-Dobjc_link_args=-arch arm64 -mmacosx-version-min=26.0'
    '-Dobjcpp_link_args=-arch arm64 -mmacosx-version-min=26.0'
)
if test -f "$BUILD_DIR/build.ninja"; then
    meson setup --reconfigure --clearcache "$BUILD_DIR" "${OPTIONS[@]}"
else
    meson setup "$BUILD_DIR" "${OPTIONS[@]}"
fi
meson compile -C "$BUILD_DIR" -j"$JOBS"
meson test -C "$BUILD_DIR" --print-errorlogs
test "$(lipo -archs "$BUILD_DIR/aegisub")" = arm64
