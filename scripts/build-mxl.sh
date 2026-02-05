#!/usr/bin/env bash
#
# MXL cmake build
#
# See: https://github.com/dmf-mxl/mxl/blob/main/docs/Building.md

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "$SCRIPT_DIR"/module/bootstrap.sh exit_trap.sh logging.sh user_context.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <src-dir> <build-dir> [-dev] [-prod] [-clang]

Arguments:
  <src-dir>     Directory to find src artifacts
  <build-dir>   Directory to write build artifacts

Options:
  --prod        Production build (GCC, static, release)
  --dev         Development build (GCC, static, debug)
  --clang       Add Clang build to all.

Build MXL release/debug and static/shared variants.  GCC is always
built, Clang is optional. Use --prod or --dev to select build variant,
or else all variants are built.
EOF
}

# Adds check for error conditions that are not reflected by the ctest
# exit status.
safer_ctest() {
    local log_file="$1"
    shift

    log "ctest output log: $log_file"
    log "ctest version: $(ctest --version | head -n 1)"
    log "ctest arguments: $*"

    ctest "$@" 2>&1 | tee "$log_file"

    if grep --quiet "No tests were found" "$log_file"; then
        log_error "ctest found no tests"
        exit 1
    fi
}

build_variant() {
    local preset="$1"
    local linkage="$2"

    local shared
    case "$linkage" in
        shared) shared="ON" ;;
        static) shared="OFF" ;;
        *)
            log_error "invalid linkage value: \"$linkage\" (expected shared|static)"
            exit 2
            ;;
    esac

    log "build MXL preset $preset with $linkage linkage"

    : "${SRC_DIR:?SRC_DIR is not set}"
    : "${BUILD_DIR:?BUILD_DIR is not set}"

    MXL_SRC="$SRC_DIR"/mxl
    MXL_BUILD="$BUILD_DIR"/mxl/build
    MXL_INSTALL="$BUILD_DIR"/mxl/install

    export VCPKG_ROOT="$SRC_DIR"/vcpkg

    local variant_build_dir="$MXL_BUILD/$preset/$linkage"
    local variant_install_dir="$MXL_INSTALL/$preset/$linkage"

    mkdir -p "$MXL_BUILD"

    # optional config args
    local cmake_config_args=""
    if has_opt "--mxl-cmake-config-args" "$@"; then
      get_opt cmake_config_args "--mxl-cmake-config-args" "$@"
    fi

    cmake -S "$MXL_SRC" -B "$variant_build_dir" --preset "$preset" \
        -DCMAKE_TOOLCHAIN_FILE="$VCPKG_ROOT"/scripts/buildsystems/vcpkg.cmake \
        -DVCPKG_INSTALLED_DIR="$variant_install_dir" \
        -DBUILD_SHARED_LIBS="$shared" \
        -DCMAKE_INSTALL_PREFIX="$variant_install_dir" \
        -DMXL_ENABLE_IPO=OFF \
        -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF \
        -DCMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE=OFF \
        "$cmake_config_args"

    cmake --build "$variant_build_dir" -j --target all

    log "testing MXL preset $preset with shared $shared..."
    cd "$variant_build_dir"
    safer_ctest "$variant_build_dir"/ctest_output.log \
                --test-dir "$variant_build_dir" --stop-on-failure --output-on-failure

    cmake --build "$variant_build_dir" -j --target doc
    cmake --install "$variant_build_dir"
}

vcpkg_bootstrap() {
    local src_dir="$1"
    "$src_dir"/vcpkg/bootstrap-vcpkg.sh --disableMetrics
}

main() {
    check_help "$@"

    local SRC_DIR BUILD_DIR
    get_var SRC_DIR "$@" && shift
    get_var BUILD_DIR "$@" && shift

    enforce_build_context

    vcpkg_bootstrap "$SRC_DIR"

    local gcc_preset="GCC"
    if has_opt "--mxl-gcc-preset" "$@"; then
      get_opt gcc_preset "--mxl-gcc-preset" "$@"
    fi
    
    if has_opt "--prod" "$@"; then
        build_variant "Linux-${gcc_preset}-Release" static "$@"
    elif has_opt "--dev" "$@"; then
        build_variant "Linux-${gcc_preset}-Debug" static "$@"
    else
        build_variant "Linux-${gcc_preset}-Release" shared "$@"
        build_variant "Linux-${gcc_preset}-Release" static "$@"
        build_variant "Linux-${gcc_preset}-Debug" shared "$@"
        build_variant "Linux-${gcc_preset}-Debug" static "$@"
        
        if has_opt "--clang" "$@"; then
            build_variant Linux-Clang-Release shared "$@"
            build_variant Linux-Clang-Release static "$@"
            build_variant Linux-Clang-Debug shared "$@"
            build_variant Linux-Clang-Debug static "$@"
        fi
    fi
}

main "$@"
