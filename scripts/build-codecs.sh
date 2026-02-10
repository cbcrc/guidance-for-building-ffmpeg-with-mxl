#!/usr/bin/env bash
#
# Build streaming libraries used by FFmpeg streaming build.

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "$SCRIPT_DIR"/module/bootstrap.sh exit_trap.sh logging.sh user_context.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <src-dir> <build-dir>

Arguments:
  <src-dir>     Directory to find src artifacts
  <build-dir>   Directory to write build artifacts

Build Opus and x264 codecs. Testing is performed via the FFmpeg FATE
test suite rather than the codecs’ own test suites.
EOF
}

build_opus() {
    log "Build Opus"
    
    local opus_build_dir="$BUILD_DIR"/opus/build/Linux-GCC-Release/static
    local opus_install_dir="$BUILD_DIR"/codecs/install/Linux-GCC-Release/static

    mkdir -p "$opus_build_dir"
 
    cd "$SRC_DIR"/opus
    ./autogen.sh

    cd "$opus_build_dir"

    CFLAGS="-O3 -DNDEBUG -march=core-avx2 -mtune=icelake-server" \
    "$SRC_DIR"/opus/configure \
        --prefix="$opus_install_dir" \
        --enable-static \
        --disable-shared \
        --disable-doc \
        --disable-extra-programs
    
    make -j"$(nproc)"
    make install
}

build_h264() {
    log "Build x264"

    local x264_build_dir="$BUILD_DIR"/x264/build/Linux-GCC-Release/static
    local x264_install_dir="$BUILD_DIR"/codecs/install/Linux-GCC-Release/static

    mkdir -p "$x264_build_dir" 
    cd "$x264_build_dir"

    CFLAGS="-O3 -DNDEBUG -march=core-avx2 -mtune=icelake-server" \
    "$SRC_DIR/x264/configure" \
        --prefix="$x264_install_dir" \
        --enable-static \
        --disable-shared \
        --disable-cli \
        --disable-opencl
    
    make -j"$(nproc)"
    make install
}

main() {
    check_help "$@"

    local SRC_DIR BUILD_DIR
    get_var SRC_DIR "$@" && shift
    get_var BUILD_DIR "$@" && shift

    enforce_build_context

    build_opus
    build_h264
}

main "$@"
