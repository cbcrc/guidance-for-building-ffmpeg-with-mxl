#!/usr/bin/env bash
#
# FFmpeg configure and build with MXL support.

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "${SCRIPT_DIR}"/module/bootstrap.sh exit_trap.sh logging.sh user_context.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <build-dir>

Arguments:
  <build-dir>   Directory to place build artifacts
EOF
}

setup_paths() {
    : "${BUILD_DIR:?BUILD_DIR is not set}"

    MXL_SANDBOX="${BUILD_DIR}/mxl"
    MXL_BUILD="${MXL_SANDBOX}/build"
    MXL_INSTALL="${MXL_SANDBOX}/install"

    FFMPEG_SANDBOX="${BUILD_DIR}/ffmpeg"

    # derived FFmpeg dirs
    FFMPEG_SRC="${FFMPEG_SANDBOX}/src"
    FFMPEG_BUILD="${FFMPEG_SANDBOX}/build"
    FFMPEG_INSTALL="${FFMPEG_SANDBOX}/install"

    log "FFMPEG_SANDBOX=${FFMPEG_SANDBOX}"
}

clone_ffmpeg() {
    log "clone FFmpeg repository"
    git clone --single-branch --branch dmf-mxl/master --depth 1 https://github.com/cbcrc/FFmpeg.git
}

ffmpeg_configure() {
    log "FFmpeg configure (in $PWD)"

    log_cmd "PKG_CONFIG_PATH=$PKG_CONFIG_PATH"

    local -a cmd=(
        "${FFMPEG_SRC}"/FFmpeg/configure
        --disable-everything
        --enable-demuxer=mxl --enable-muxer=mxl --enable-libmxl
        --enable-muxer=framemd5
        --enable-encoder=pcm_f32le --enable-decoder=pcm_f32le
        --enable-encoder=pcm_s16le --enable-decoder=pcm_s16le
        --enable-encoder=rawvideo --enable-decoder=rawvideo
        --enable-encoder=v210 --enable-decoder=v210
        --enable-decoder=wrapped_avframe
        --enable-indev=lavfi
        --enable-filter=scale
        --enable-filter=testsrc2
        --enable-filter=anoisesrc
        --enable-filter=aresample
        --enable-protocol=pipe
    )

    cmd+=("$@")

    log_cmd "${cmd[@]}"

    "${cmd[@]}"
}

ffmpeg_build_test_install() {
    local variant_name="$1"
    log "FFmpeg build and test ($variant_name in $PWD)"

    make clean
    make -j
    make fate-mxl-json fate-mxl-video-encdec fate-mxl-audio-encdec
    make install
}

build_variant() {
    local mxl_preset="$1"
    local linkage="$2"

    local variant_name="${mxl_preset}_${linkage}"

    local vcpkg_build_dir=""
    local is_debug=0
    if [[ "$mxl_preset" == *-Debug ]]; then
        is_debug=1
        vcpkg_build_dir="debug/"
    fi

    log "configure variant: $variant_name"
    local full_mxl_install_dir="${MXL_INSTALL}/${mxl_preset}/${linkage}"
    local full_mxl_build_dir="${MXL_BUILD}/${mxl_preset}/${linkage}"
    export PKG_CONFIG_PATH="${full_mxl_install_dir}/lib/pkgconfig:${full_mxl_build_dir}/vcpkg_installed/x64-linux/${vcpkg_build_dir}lib/pkgconfig"

    local extra_config_opts=()

    if ((is_debug)); then
        extra_config_opts+=(--enable-debug=2 --assert-level=2 --disable-optimizations --disable-stripping)
    fi

    if [[ "$linkage" == static ]]; then
        unset LD_LIBRARY_PATH
        extra_config_opts+=(--pkg-config-flags=--static --enable-static --disable-shared)
    else
        export LD_LIBRARY_PATH="${full_mxl_install_dir}/lib:libswscale:libswresample:libavutil:libavformat:libavfilter:libavdevice:libavcodec"
        log_cmd "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
        extra_config_opts+=(--disable-static --enable-shared)
    fi

    # Note: intentional use of "mxl_peset" to match mxl build convention
    local build_dir="${FFMPEG_BUILD}/${mxl_preset}/${linkage}"
    local install_dir="${FFMPEG_INSTALL}/${mxl_preset}/${linkage}"

    mkdir -p -- "${build_dir}"
    pushd "${build_dir}"

    ffmpeg_configure --prefix="${install_dir}" "${extra_config_opts[@]}"
    ffmpeg_build_test_install "${variant_name}"

    popd
}

main() {
    check_help "$@"
    set_build_dir "$@"

    setup_paths

    enforce_build_context

    mkdir -p -- "$FFMPEG_SRC"
    cd "$FFMPEG_SRC"
    clone_ffmpeg

    cd FFmpeg
    build_variant Linux-GCC-Release shared
    build_variant Linux-GCC-Release static
    build_variant Linux-GCC-Debug shared
    build_variant Linux-GCC-Debug static
}

main "$@"
