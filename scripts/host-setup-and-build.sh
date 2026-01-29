#!/usr/bin/env bash
#
# MXL plus FFmpeg full build on host

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "${SCRIPT_DIR}"/module/bootstrap.sh exit_trap.sh safe_sudo.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <src-dir> <build-dir> [--skip-setup] [--allow-root]

Arguments:
  <src-dir>     Directory to find src artifacts
  <build-dir>   Directory to place build artifacts

Options:
  --skip-setup  Skip environment setup.
  --allow-root  Run all environment setup under a single sudo invocation
                to avoid repeated password prompts.

Setup host environment and build both MXL and FFmpeg. Populate
<src-dir> with get-src.sh. All command-line arguments are passed
through to build-mxl.sh and build-ffmpeg.sh (e.g. --dev, --prod).
EOF
}

main() {
    check_help "$@"
    get_var SRC_DIR "$@" && shift
    get_var BUILD_DIR "$@" && shift

    enforce_build_context

    if ! has_opt "--skip-setup" "$@"; then
        log "environment setup"
        if has_opt --allow-root "$@"; then
            safe_sudo "setup all environment dependencies" "${SCRIPT_DIR}/setup-env-all.sh" "$@"
        else
            ./setup-env-all.sh "$@"
        fi
    else
        log "skip environment setup"
    fi

    mkdir -p "$BUILD_DIR"

    ./build-mxl.sh "$SRC_DIR" "$BUILD_DIR" "$@"

    ./build-ffmpeg.sh "$SRC_DIR" "$BUILD_DIR" "$@"
    
    if has_opt "--extended" "$@"; then
        WITH_X265=0 ./build-ffmpeg-extended.sh "$SRC_DIR" "$BUILD_DIR" --build-all "$@"
    fi
}

main "$@"
