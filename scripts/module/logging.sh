# shellcheck shell=bash
# Usage: source "$SCRIPT_DIR"/module/logging.sh
#
# Provide simple logging functions.

if [[ -n "${LOGGING_BASH_SOURCE_GUARD:-}" ]]; then
    return 0
fi
readonly LOGGING_BASH_SOURCE_GUARD=1

log() {
    printf '\033[1;32m==> %s\033[0m\n' "$*"
}

log_warning() {
    printf '\033[1;93m==> warning: %s\033[0m\n' "$*" >&2
}

log_error() {
    printf '\033[1;91m==> error: %s\033[0m\n' "$*" >&2
}

log_cmd() {
    local a
    printf '==> '
    for a in "$@"; do
        printf ' %q' "$a"
    done
    printf '\n'
}
