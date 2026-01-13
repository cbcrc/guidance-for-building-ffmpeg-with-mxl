# shellcheck shell=bash
# Usage: source "$SCRIPT_DIR"/module/safe_sudo.sh
#
# Lock down sudo to avoid accidental permission elevation of
# unexpected commands. Command paths are resolved using the shell
# "command" built in.
#
# The sudo prompt includes a reason and echos the command so that the
# user is not blindly elevating permission.
#
# Commands executed in containers are exempted from using sudo if the
# effective user is root but those commands are not exempted from the
# safe list check.

if [[ -n "${SAFE_SUDO_BASH_SOURCE_GUARD:-}" ]]; then
    return 0
fi
readonly SAFE_SUDO_BASH_SOURCE_GUARD=1

: "${SCRIPT_DIR:?SCRIPT_DIR not set}"
source "${SCRIPT_DIR}/module/logging.sh"
source "${SCRIPT_DIR}/module/user_context.sh"

# Allow-list (absolute paths only)
readonly SAFE_SUDO_ALLOWED_LIST=(
    "/usr/bin/apt-get"
    "${SCRIPT_DIR}/cmake-repo-upgrade.sh"
)

_safe_sudo_is_allowed() {
    local cmd="$1"
    local allowed
    for allowed in "${SAFE_SUDO_ALLOWED_LIST[@]}"; do
        [[ "$cmd" == "$allowed" ]] && return 0
    done
    return 1
}

# usage: safe_sudo reason command [args...]
# e.g. safe_sudo "install dependencies" apt-get install a_thing another_thing
safe_sudo() {
    local reason="$1"
    shift

    local prog="$1"
    shift

    # Resolve to absolute command path
    local cmd
    cmd="$(command -v -- "$prog" 2>/dev/null || true)"
    if [[ -z "$cmd" ]]; then
        log_error "command not found: $prog"
        exit 127
    fi

    # Enforce allow list
    if ! _safe_sudo_is_allowed "$cmd"; then
        log_error "\"$cmd\" is not on the allow list."
        exit 126
    fi

    # Show the user exactly what's about to happen
    printf '+ %q' "$cmd"
    local arg
    for arg in "$@"; do
        printf ' %q' "$arg"
    done
    printf '\n'

    if is_container && ((EUID == 0)); then
        # already root, sudo may not be available in container
        log "$reason: $cmd $*"
        "$cmd" "$@"
    else
        # force a fresh password prompt every time, with a clear message
        command sudo -k -p "[sudo] password for %u (reason: ${reason}): " -- "$cmd" "$@"
    fi
}
