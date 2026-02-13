#!/usr/bin/env bash
#
# FFmpeg configure and build with MXL support.

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "$SCRIPT_DIR"/module/bootstrap.sh exit_trap.sh logging.sh user_context.sh read_list.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <src-dir> <build-dir> [--prod] [--dev]

Arguments:
  <src-dir>     Directory to find src artifacts
  <build-dir>   Directory to write build artifacts

Options:
  --prod        Production build (GCC, static, release)
  --dev         Development build (GCC, static, debug)
  --no-ffplay   Do not build ffplay or link its dependent libraries.
  --streaming   Build with RTSP, Opus, and H.264 support.

Use --prod or --dev to select build variant, or else all variants are
built.
EOF
}

ffmpeg_configure() {
    local install_dir="$1"
    local include_fate_samples="$2"
    local linkage="$3"
    shift 3

    log "FFmpeg configure (in $PWD)"

    log_cmd "PKG_CONFIG_PATH=$PKG_CONFIG_PATH"

    local -a config_options
    read_list config_options "$@"
    
    local -a cmd=(
        "$FFMPEG_SRC"/configure
        --prefix="$install_dir"
        "${config_options[@]}"
    )

    if (( include_fate_samples )); then
        cmd+=("--samples=$FFMPEG_FATE_SUITE")
    fi

    # Statically link GCC-13 libstdc++ so the resulting binaries do
    # not depend on the target system's libstdc++ version (workaround
    # for compatibility with stock Ubuntu 20.04 systems and MXL GCC-13
    # dependency).
    if [[ "$linkage" == static ]]; then
        local libstdcpp
        libstdcpp="$(g++-13 -print-file-name=libstdc++.a)"
        cmd+=("--extra-libs=$libstdcpp")
    fi
    
    log_cmd "${cmd[@]}"
    "${cmd[@]}"
}

build_variant() {
    local preset="$1"
    local mxl_preset="$2"
    local linkage="$3"
    
    log "build FFmpeg with preset $1, mxl preset $mxl_preset, and $linkage linkage"

    : "${SRC_DIR:?SRC_DIR is not set}"
    : "${BUILD_DIR:?BUILD_DIR is not set}"

    local streaming=0
    if has_opt "--streaming" "$@"; then
        streaming=1
    fi
    
    FFMPEG_SRC="$SRC_DIR"/FFmpeg
    FFMPEG_BUILD="$BUILD_DIR"/ffmpeg/build
    FFMPEG_INSTALL="$BUILD_DIR"/ffmpeg/install
    FFMPEG_FATE_SUITE="$BUILD_DIR"/ffmpeg-fate-suite

    local mxl_install="$BUILD_DIR"/mxl/install
    local full_mxl_install_dir="$mxl_install/$mxl_preset/$linkage"
    export PKG_CONFIG_PATH="$full_mxl_install_dir"/lib/pkgconfig:"$full_mxl_install_dir"/x64-linux/lib/pkgconfig

    if (( streaming )); then
        local codecs_install="$BUILD_DIR/codecs/install/Linux-GCC-Release/static/lib/pkgconfig"
        export PKG_CONFIG_PATH="$PKG_CONFIG_PATH":"$codecs_install"
    fi
    
    local -a config_opts_files=("deps/ffmpeg-configure-base-options.txt")

    if [[ "$preset" == *-Debug ]]; then
        config_opts_files+=("deps/ffmpeg-configure-debug-options.txt")
    fi

    if [[ "$linkage" == static ]]; then
        unset LD_LIBRARY_PATH
        config_opts_files+=("deps/ffmpeg-configure-static-options.txt")
    else
        export LD_LIBRARY_PATH="$full_mxl_install_dir"/lib:libswscale:libswresample:libavutil:libavformat:libavfilter:libavdevice:libavcodec
        log_cmd "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
        config_opts_files+=("deps/ffmpeg-configure-shared-options.txt")
    fi

    if (( streaming )); then
        config_opts_files+=("deps/ffmpeg-configure-streaming-options.txt")
    fi

    if has_opt "--no-ffplay" "$@"; then
        config_opts_files+=("deps/ffmpeg-configure-noplay-options.txt")
    fi
    
    # Note: match MXL build path convention
    local build_dir="$FFMPEG_BUILD/$preset/$linkage"
    local install_dir="$FFMPEG_INSTALL/$preset/$linkage"

    mkdir -p "$build_dir"
    pushd "$build_dir"

    ffmpeg_configure "$install_dir" "$streaming" "$linkage" "${config_opts_files[@]}"
    make clean
    make -j"$(nproc)"
    if (( streaming )); then
        make fate-rsync
        make fate
    else
        make fate-mxl-json fate-mxl-video-encdec fate-mxl-audio-encdec
    fi
    make install

    popd
}

main() {
    check_help "$@"

    local SRC_DIR BUILD_DIR
    get_var SRC_DIR "$@" && shift
    get_var BUILD_DIR "$@" && shift

    enforce_build_context

    local mxl_gcc_preset="GCC"
    if has_opt "--mxl-gcc-preset" "$@"; then
      get_opt mxl_gcc_preset "--mxl-gcc-preset" "$@"
    fi

    if has_opt "--prod" "$@"; then
        build_variant "Linux-GCC-Release" "Linux-$mxl_gcc_preset-Release" static "$@"
    elif has_opt "--dev" "$@"; then
        build_variant "Linux-GCC-Debug" "Linux-$mxl_gcc_preset-Debug" static "$@"
    else
        build_variant "Linux-GCC-Release" "Linux-$mxl_gcc_preset-Release" shared "$@"
        build_variant "Linux-GCC-Release" "Linux-$mxl_gcc_preset-Release" static "$@"
        build_variant "Linux-GCC-Debug" "Linux-$mxl_gcc_preset-Debug" shared "$@"
        build_variant "Linux-GCC-Debug" "Linux-$mxl_gcc_preset-Debug" static "$@"
    fi
}

main "$@"
