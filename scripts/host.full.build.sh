#!/usr/bin/env bash
#
# MXL plus FFmpeg full build on host

set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}"/module/bootstrap.sh exit_trap.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <build-dir> [--skip-setup]

Arguments:
  <build-dir>   Directory to place build artifacts

Options:
  --skip-setup  Skip environment setup.

Setup host environment and build both MXL and FFmpeg.
EOF
}

main() {
    check_help "$@"
    set_build_dir "$@"

    if ! has_opt "--skip-setup" "$@"; then
        log "environment setup"
        # Note: intentionally not passing args to prevent "--allow-root"
        ./setup-env-mxl.sh
        ./setup-env-ffmpeg.sh
    else
        log "skip environment setup"
    fi

    mkdir -p -- "$BUILD_DIR"

    ./build-mxl.sh $BUILD_DIR "$@"
    ./build-ffmpeg.sh $BUILD_DIR "$@"
}

main "$@"
