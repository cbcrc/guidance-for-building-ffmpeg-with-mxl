#!/usr/bin/env bash
#
# Build Intel Media-Transport-Library (MTL / ST 2110).
# DPDK must be installed first; run build-dpdk.sh before this script.

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "$SCRIPT_DIR"/module/bootstrap.sh exit_trap.sh logging.sh user_context.sh

MTL_SUBMODULE_DIR="$SCRIPT_DIR/../Media-Transport-Library"

usage() {
    cat <<EOF
Usage: $(basename "$0") <src-dir> <build-dir> [--dev]

Arguments:
  <src-dir>     Directory to find src artifacts (reserved, currently unused)
  <build-dir>   Directory to write build artifacts

Options:
  --dev         Debug build (with ASAN)

Build Intel Media-Transport-Library and install.
Install prefix: <build-dir>/mtl/install
EOF
}

main() {
    check_help "$@"

    local SRC_DIR BUILD_DIR
    get_var SRC_DIR "$@" && shift
    get_var BUILD_DIR "$@" && shift

    enforce_build_context

    export MTL_INSTALL_PREFIX="$BUILD_DIR/mtl/install"

    # Expose DPDK to meson when it was installed to a custom prefix by build-dpdk.sh.
    local dpdk_pkgdir
    dpdk_pkgdir=$(find "$MTL_INSTALL_PREFIX" -name "libdpdk.pc" -exec dirname {} \; 2>/dev/null | head -1)
    if [[ -n "$dpdk_pkgdir" ]]; then
        export PKG_CONFIG_PATH="$dpdk_pkgdir:${PKG_CONFIG_PATH:-}"
        log "DPDK pkg-config: $dpdk_pkgdir"
    fi

    local buildtype=release
    if has_opt "--dev" "$@"; then
        buildtype=debug
    fi

    log "Build MTL ($buildtype, install prefix: $MTL_INSTALL_PREFIX)"
    pushd "$MTL_SUBMODULE_DIR"
    bash build.sh "$buildtype"
    ninja -C build install
    #DESTDIR=/build ninja -C build install
    popd
}

main "$@"
