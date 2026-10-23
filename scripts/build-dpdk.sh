#!/usr/bin/env bash
#
# Build DPDK with Intel MTL patches (dependency for Media-Transport-Library).

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "$SCRIPT_DIR"/module/bootstrap.sh exit_trap.sh logging.sh

MTL_SUBMODULE_DIR="$SCRIPT_DIR/../Media-Transport-Library"

usage() {
    cat <<EOF
Usage: $(basename "$0") <src-dir> <build-dir> [--force]

Arguments:
  <src-dir>     Directory to find src artifacts (reserved, currently unused)
  <build-dir>   Directory to write build artifacts (reserved, currently unused)

Options:
  --force       Force DPDK rebuild even if the correct MTL-patched version
                is already installed.

Build DPDK from source with Intel MTL patches and install system-wide.
May be run as root. Skips the build if the correct MTL-patched DPDK
version is already installed.
DPDK source is downloaded into the Media-Transport-Library submodule
script/ directory as expected by the upstream build_dpdk.sh.
EOF
}

main() {
    check_help "$@"

    local SRC_DIR BUILD_DIR
    get_var SRC_DIR "$@" && shift
    get_var BUILD_DIR "$@" && shift

    local -a force_flag=()
    if has_opt "--force" "$@"; then
        force_flag=(-f)
    fi

    pushd "$MTL_SUBMODULE_DIR/script"
    #log "Build eBPF"
    # bash build_ebpf_xdp.sh
    log "Build DPDK with MTL patches"
    export MTL_INSTALL_PREFIX="$BUILD_DIR/mtl/install"
    bash build_dpdk.sh "${force_flag[@]}"
    popd
}

main "$@"
