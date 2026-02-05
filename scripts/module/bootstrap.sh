# shellcheck shell=bash
# Usage: source "$SCRIPT_DIR"/module/bootstrap.sh file1.sh file2.sh ...
#
# Check the bash version requirement, set shell options, and source
# modules "$SCRIPT_DIR"/module/file[1,2,...].sh
#
# Also provide a few utility functions.

# bash >= 4.3 requirement
if [[ -z "${BASH_VERSINFO:-}" ]] ||
    ((BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3))); then
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
# option, and set environment variable named by $1. The named
# variable is exported and set to readonly.
# e.g. get_dir SRC_DIR "$@" && shift
# e.g. get_dir BUILD_DIR "$@" && shift
get_var() {
    local -n out_var="$1"
    shift
    
    if [[ $# -lt 1 ]] || [[ -z "${1-}" || "$1" == --* ]]; then
        usage
        exit 2
    fi
    out_var="$1"
    export out_var
    readonly out_var
}


# Return success if the given command-line option appears in the
# argument list.
# e.g.: if has_opt --something "$@"; then do_something; fi 
has_opt() {
    local opt="$1"
    shift
    for arg; do
        [[ "$arg" == "$opt" ]] && return 0
    done
    return 1
}

# Get the value following a command-line option.
# Usage: get_opt <varname> <option> "$@"
# Example: get_opt patchfile --mxl_patch "$@"
get_opt() {
    local -n out="$1"
    local opt="$2"
    shift 2

    while (($#)); do
        if [[ "$1" == "$opt" ]]; then
            shift
            [[ $# -gt 0 ]] || {
                log_error "missing argument for \"$opt\"" >&2
                exit 2
            }
            # shellcheck disable=SC2034
            out="$1"
            return 0
        fi
        shift
    done

    log_error "option not found \"$opt\""
    exit 2
}

# Check if "-h" or "--help" is an option and print usage.
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
