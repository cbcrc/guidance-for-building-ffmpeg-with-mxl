#!/usr/bin/env bash
#
# FFmpeg configure and build with MXL support.

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "${SCRIPT_DIR}"/module/bootstrap.sh exit_trap.sh logging.sh user_context.sh read_list.sh

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
    mkdir -p -- "$FFMPEG_SRC"
    cd "$FFMPEG_SRC"

    git clone --single-branch --branch dmf-mxl/master --depth 1 https://github.com/cbcrc/FFmpeg.git

    cd FFmpeg
    git checkout --detach a8441ff
}

ffmpeg_configure() {
    local install_dir="$1"
    shift

    log "FFmpeg configure (in $PWD)"

    log_cmd "PKG_CONFIG_PATH=$PKG_CONFIG_PATH"

    local -a config_options
    read_list config_options "$@"
    
    local -a cmd=(
        "${FFMPEG_SRC}/FFmpeg/configure"
        --prefix="${install_dir}"
        "${config_options[@]}"
    )
    
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
    log "configure variant: $variant_name"
    
    local full_mxl_install_dir="${MXL_INSTALL}/${mxl_preset}/${linkage}"
    export PKG_CONFIG_PATH="${full_mxl_install_dir}/lib/pkgconfig:${full_mxl_install_dir}/x64-linux/lib/pkgconfig"

    local -a config_opts_files=("deps/ffmpeg-configure-base-options.txt")

    if [[ "$mxl_preset" == *-Debug ]]; then
        config_opts_files+=("deps/ffmpeg-configure-debug-options.txt")
    fi

    if [[ "$linkage" == static ]]; then
        unset LD_LIBRARY_PATH
        config_opts_files+=("deps/ffmpeg-configure-static-options.txt")
    else
        export LD_LIBRARY_PATH="${full_mxl_install_dir}/lib:libswscale:libswresample:libavutil:libavformat:libavfilter:libavdevice:libavcodec"
        log_cmd "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
        config_opts_files+=("deps/ffmpeg-configure-shared-options.txt")
    fi

    # Note: intentional use of "mxl_peset" to match mxl build convention
    local build_dir="${FFMPEG_BUILD}/${mxl_preset}/${linkage}"
    local install_dir="${FFMPEG_INSTALL}/${mxl_preset}/${linkage}"

    mkdir -p -- "${build_dir}"
    pushd "${build_dir}"

    ffmpeg_configure "$install_dir" "${config_opts_files[@]}"
    ffmpeg_build_test_install "${variant_name}"

    popd
}

main() {
    check_help "$@"
    set_build_dir "$@"

    setup_paths

    enforce_build_context

    clone_ffmpeg

    build_variant Linux-GCC-Release shared
    build_variant Linux-GCC-Release static
    build_variant Linux-GCC-Debug shared
    build_variant Linux-GCC-Debug static
}

main "$@"
