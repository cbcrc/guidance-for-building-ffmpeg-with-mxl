# Usage: source "$SCRIPT_DIR"/module/exit_trap.sh
#
# Setup exit trap that outputs a final PASS or FAIL message and then
# exits with final exit status.

if [[ -n "${EXIT_TRAP_BASH_SOURCE_GUARD:-}" ]]; then
    return 0
fi
readonly EXIT_TRAP_BASH_SOURCE_GUARD=1

: "${SCRIPT_DIR:?SCRIPT_DIR not set}"
source "${SCRIPT_DIR}/module/logging.sh"

_on_err_trap() {
    local status=$?
    log_error "status=$status at ${BASH_SOURCE[1]}:${BASH_LINENO[0]}: ${BASH_COMMAND}"
    return "$status"
}

_on_exit_trap() {
    local status=$?

    if ((status != 0)); then
        echo
        log_error "FAIL ($0 ${SCRIPT_ARGS[@]})"
    else
        echo
        log "PASS ($0 ${SCRIPT_ARGS[@]})"
    fi

    exit "${status}"
}

trap _on_err_trap ERR
trap _on_exit_trap INT TERM EXIT
