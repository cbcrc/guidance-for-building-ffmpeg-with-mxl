# shellcheck shell=bash
# Usage: source "$SCRIPT_DIR"/module/user_context.sh
#
# Utility functions to manage user context, i.e. root vs ordinary
# user, host vs container, setup vs build.

if [[ -n "${USER_CONTEXT_BASH_SOURCE_GUARD:-}" ]]; then
    return 0
fi
readonly USER_CONTEXT_BASH_SOURCE_GUARD=1

: "${SCRIPT_DIR:?SCRIPT_DIR not set}"
source "${SCRIPT_DIR}/module/logging.sh"

is_container() {
    [[ -f /run/ffmpeg-build-context ]] && [[ "$(</run/ffmpeg-build-context)" == "container" ]]
}

is_host() {
    ! is_container
}

# Enforce that effective user is root in a container. Refuse to run as
# root on host unless the --allow-root is option is found.
#
# The refusal to run as root on host is a safety measure. Commands
# that require root permissions should use the safe_sudo function to
# gain root permission. Users can use "--allow-root" for convenience
# after confidence and trust is established.
enforce_setup_context() {
    if is_container && ((EUID != 0)); then
        log_error "Running in container and user not root."
        exit 1
    elif is_host && ((EUID == 0)); then
        if has_opt "--allow-root" "$@"; then
            log_warning "Running as root on host."
            # Give the user a few seconds to see that message if this is a terminal.
            if [[ -t 2 ]]; then
                sleep 2
            fi
        else
            log_error "Refusing to run as root on host."
            exit 1
        fi
    fi
}

_log_container_build_context_hint() {
    log_error "Hint: run docker as a regular user has that has permision to write $BUILD_DIR."
}

# Enforce that the effective user is not root. In a container also
# enforce that the user has permission to create the $BUILD_DIR. Note:
# this is necessary for both safety, and because the MXL test will
# fail if executed with root permissions.
enforce_build_context() {
    : "${BUILD_DIR:?BUILD_DIR is not set}"

    if ((EUID == 0)); then
        log_error "Build/test cannot run as root."
        if is_container; then
            _log_container_build_context_hint
        fi
        exit 1
    fi

    if is_container; then
        if ! mkdir -p -- "${BUILD_DIR}"; then
            log_error "${BUILD_DIR} is not writable by uid=$EUID, gid=$(id -g)."
            _log_container_build_context_hint
            exit 1
        fi
    fi
}
