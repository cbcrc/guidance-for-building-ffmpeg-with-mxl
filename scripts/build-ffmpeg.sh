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
  --fate        Build the FFmpeg FATE suite
  --mtl         Enable Intel Media-Transport-Library (ST 2110) support.
                Applies the MTL FFmpeg plugin patch and enables the mtl
                in/out devices. Requires MTL and DPDK to be installed.

Use --prod or --dev to select build variant, or else all variants are
built.
EOF
}

# Apply the MTL FFmpeg plugin patch and copy its source files into the
# FFmpeg source tree. A sentinel file prevents double-patching on
# subsequent builds.
apply_mtl_patch() {
    : "${SRC_DIR:?SRC_DIR is not set}"

    local ffmpeg_src="$SRC_DIR/FFmpeg"
    local mtl_submodule="$SCRIPT_DIR/../Media-Transport-Library"
    local mtl_plugin="$mtl_submodule/ecosystem/ffmpeg_plugin"
    local sentinel="$ffmpeg_src/.mtl-patch-applied"

    if [[ -f "$sentinel" ]]; then
        log "MTL FFmpeg patch already applied, skipping"
        return
    fi

    local ffmpeg_version
    # shellcheck source=/dev/null
    ffmpeg_version=$(. "$mtl_submodule/versions.env" && echo "$FFMPEG_VERSION")

    local patch_dir="$mtl_plugin/$ffmpeg_version"
    [[ -d "$patch_dir" ]] || {
        log_error "No MTL patch found for FFmpeg $ffmpeg_version (looked in $patch_dir)"
        exit 1
    }

    log "Copy MTL FFmpeg plugin source files to $ffmpeg_src/libavdevice/"
    cp -f "$mtl_plugin"/mtl_* "$ffmpeg_src/libavdevice/"

    log "Apply MTL FFmpeg plugin patches (FFmpeg $ffmpeg_version)"
    for patch_file in "$patch_dir"/*.patch; do
        [[ -f "$patch_file" ]] || continue
        log "  Applying: $(basename "$patch_file")"
        git -C "$ffmpeg_src" am "$patch_file"
    done

    touch "$sentinel"
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
    FFMPEG_FATE_SUITE="$SRC_DIR"/fate-suite

    local mxl_install="$BUILD_DIR"/mxl/install
    local full_mxl_install_dir="$mxl_install/$mxl_preset/$linkage"
    export PKG_CONFIG_PATH="$full_mxl_install_dir"/lib/pkgconfig:"$full_mxl_install_dir"/x64-linux/lib/pkgconfig

    if has_opt "--mtl" "$@"; then
        PKG_CONFIG_PATH="$BUILD_DIR/mtl/install/lib/pkgconfig:$PKG_CONFIG_PATH"
    fi

    # Note: match MXL build path convention
    local build_dir="$FFMPEG_BUILD/$preset/$linkage"
    local install_dir="$FFMPEG_INSTALL/$preset/$linkage"
    
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
        local -a ld_library_path=(
            "$full_mxl_install_dir/lib"
            "$build_dir/libswscale"
            "$build_dir/libswresample"
            "$build_dir/libavutil"
            "$build_dir/libavformat"
            "$build_dir/libavfilter"
            "$build_dir/libavdevice"
            "$build_dir/libavcodec"
        )
        export LD_LIBRARY_PATH
        LD_LIBRARY_PATH=$(IFS=:; echo "${ld_library_path[*]}")        
        log_cmd "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
        config_opts_files+=("deps/ffmpeg-configure-shared-options.txt")
    fi

    if (( streaming )); then
        config_opts_files+=("deps/ffmpeg-configure-streaming-options.txt")
    fi

    if has_opt "--no-ffplay" "$@"; then
        config_opts_files+=("deps/ffmpeg-configure-noplay-options.txt")
    fi

    if has_opt "--mtl" "$@"; then
        config_opts_files+=("deps/ffmpeg-configure-mtl-options.txt")
    fi

    mkdir -p "$build_dir"
    pushd "$build_dir"

    ffmpeg_configure "$install_dir" "$streaming" "$linkage" "${config_opts_files[@]}"
    make clean
    make -j"$(nproc)"
    if has_opt "--fate" "$@"; then
        if [[ ! -d "$FFMPEG_FATE_SUITE" ]]; then
            make fate-rsync
        fi
        log Run full FATE test suite
        log_cmd make fate
        make fate
    else
        log Run only MXL FATE tests
        # shellcheck disable=SC2046
        log_cmd make $(make fate-list | grep mxl)
        # shellcheck disable=SC2046
        make $(make fate-list | grep mxl)
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

    if has_opt "--mtl" "$@"; then
        apply_mtl_patch
    fi

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
