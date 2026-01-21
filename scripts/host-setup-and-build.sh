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
Usage: $(basename "$0") <build-dir> [--skip-setup]

Arguments:
  <build-dir>   Directory to place build artifacts

Options:
  --skip-setup  Skip environment setup.
  --extended    Include FFmpeg extended build.

Setup host environment and build both MXL and FFmpeg.
EOF
}

main() {
    check_help "$@"
    set_build_dir "$@"
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

    mkdir -p -- "$BUILD_DIR"

    ./build-mxl.sh "$BUILD_DIR" "$@"

    ./build-ffmpeg.sh "$BUILD_DIR" "$@"

    if has_opt "--extended" "$@"; then
        echo yap
        WITH_X265=0 ./build-ffmpeg-extended.sh "$BUILD_DIR" --build-all "$@"
    fi
}

main "$@"
