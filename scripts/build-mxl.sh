#!/usr/bin/env bash
#
# MXL cmake build
#
# See: https://github.com/dmf-mxl/mxl/blob/main/docs/Building.md

set -e

readonly SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}"/module/bootstrap.sh exit_trap.sh logging.sh user_context.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <build-dir>

Arguments:
  <build-dir>   Directory to place build artifacts

Build MXL release/debug and static/shared variants.
EOF
}

setup_paths() {
    : "${BUILD_DIR:?BUILD_DIR is not set}"

    MXL_SANDBOX="${BUILD_DIR}/mxl"

    # derived MXL dirs
    MXL_SRC="${MXL_SANDBOX}/src"
    MXL_BUILD="${MXL_SANDBOX}/build"
    MXL_INSTALL="${MXL_SANDBOX}/install"

    log "MXL_SANDBOX=${MXL_SANDBOX}"
}

fetch_vcpkg_repo() {
    log "fetch vcpkg git repository..."

    mkdir -p -- "${MXL_SRC}"
    cd "${MXL_SRC}"
    git clone https://github.com/microsoft/vcpkg
    "${MXL_SRC}/vcpkg/bootstrap-vcpkg.sh" --disableMetrics
}

fetch_mxl_repo() {
    log "fetch MXL git repository..."

    mkdir -p -- "${MXL_SRC}"
    cd "${MXL_SRC}"
    git clone https://github.com/dmf-mxl/mxl.git

    cd "${MXL_SRC}/mxl"
    git checkout --detach 52aea5a
}

safer_ctest() {
    local log_file="$1"
    shift

    log "ctest output log: ${log_file}"
    log "ctest version: $(ctest --version | head -n 1)"
    log "ctest arguments: $*"

    ctest "$@" 2>&1 | tee "${log_file}"

    if grep --quiet "No tests were found" "${log_file}"; then
        log "ctest found no tests"
        return 1
    fi
}

build_variant() {
    local preset="$1"
    local shared="$2"

    local lib_type
    case "${shared}" in
        ON) lib_type="shared" ;;
        OFF) lib_type="static" ;;
        *)
            log "invalid shared value: \"${shared}\" (expected ON|OFF)"
            return 2
            ;;
    esac

    log "build MXL preset ${preset} with shared ${shared}..."

    local build_dir="${MXL_BUILD}/${preset}/${lib_type}"
    local install_dir="${MXL_INSTALL}/${preset}/${lib_type}"

    mkdir -p -- "${MXL_BUILD}"

    export VCPKG_ROOT="${MXL_SRC}/vcpkg"
    cmake -S "${MXL_SRC}/mxl" -B "${build_dir}" --preset "${preset}" \
        -DCMAKE_TOOLCHAIN_FILE="${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake" \
        -DBUILD_SHARED_LIBS="${shared}" \
        -DCMAKE_INSTALL_PREFIX="${install_dir}"

    cmake --build "${build_dir}" -j --target all

    log "testing MXL preset ${preset} with shared ${shared}..."
    cd "${build_dir}"
    safer_ctest "${build_dir}/ctest_output.log" --test-dir "${build_dir}" --stop-on-failure --output-on-failure

    cmake --build "${build_dir}" -j --target doc
    cmake --install "${build_dir}"
}

main() {
    check_help "$@"
    set_build_dir "$@"

    setup_paths

    enforce_build_context

    fetch_vcpkg_repo
    fetch_mxl_repo

    build_variant Linux-GCC-Release ON
    build_variant Linux-GCC-Release OFF
    build_variant Linux-GCC-Debug ON
    build_variant Linux-GCC-Debug OFF

    log "MXL build dir: ${MXL_BUILD}"
}

main "$@"
