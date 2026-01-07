# Usage: source "$SCRIPT_DIR"/module/bootstrap.sh file1.sh file2.sh ...
#
# Check the bash version requirment, set shell options, and source
# modules "$SCRIPT_DIR"/module/file[1,2,...].sh
#
# Also provide a few utility functions.

# bash >= 4.2 requirement
if [[ -z "${BASH_VERSINFO:-}" ]] ||
    ((BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 2))); then
    echo "This script requires bash >= 4.2" >&2
    exit 1
fi

if [[ -n "${BOOTSTRAP_BASH_SOURCE_GUARD:-}" ]]; then
    return 0
fi
readonly BOOTSTRAP_BASH_SOURCE_GUARD=1

: "${SCRIPT_DIR:?SCRIPT_DIR not set}"

set -eou pipefail

# Check if first positional argument is set, ensure it's not an
# option, and set environment variable BUILD_DIR.
set_build_dir() {
    if [[ $# -lt 1 ]] || [[ -z "${1-}" || "$1" == --* ]]; then
        usage
        exit 2
    fi
    readonly BUILD_DIR="$1"
    shift
}

# Return success if the given command-line option appears in the
# argument list.
# e.g.: has_opt --something "$@"
has_opt() {
    local opt="$1"
    shift
    for arg; do
        [[ "$arg" == "$opt" ]] && return 0
    done
    return 1
}

# Check if --help is an option and print usage.
check_help() {
    if has_opt "-h" "$@" || has_opt "--help" "$@"; then
        if declare -F usage >/dev/null; then
            usage
            exit 0
        else
            log_warning "help requested but usage message is not available"
        fi
    fi
}

for _m in "$@"; do
    # shellcheck source=/dev/null
    source "${SCRIPT_DIR}/module/${_m}"
done
unset _m
