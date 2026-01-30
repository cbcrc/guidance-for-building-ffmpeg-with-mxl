#!/usr/bin/env bash
#
# Setup both MXL and FFmpeg environment.
#

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "${SCRIPT_DIR}"/module/bootstrap.sh exit_trap.sh user_context.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") [--allow-root] [--clang]

Options:
  --allow-root    Allow execution as root for host builds (normally refused)
  --clang         Install and configure Clang
EOF
}


main() {
    check_help "$@"
    enforce_setup_context "$@"
    "${SCRIPT_DIR}/setup-env-mxl.sh" "$@"
    "${SCRIPT_DIR}/setup-env-ffmpeg.sh" "$@"

    if has_opt "--extended" "$@"; then
        "${SCRIPT_DIR}/setup-env-ffmpeg-extended.sh" "$@"
    fi
}

main "$@"
