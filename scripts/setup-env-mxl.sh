#!/usr/bin/env bash
#
# MXL build environment setup
#
# See: https://github.com/dmf-mxl/mxl/blob/main/docs/Building.md

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "$SCRIPT_DIR"/module/bootstrap.sh exit_trap.sh logging.sh safe_sudo.sh user_context.sh read_list.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") [--allow-root] [--clang]

Options:
  --allow-root    Allow execution as root for host builds (normally refused)
  --clang         Install and configure Clang

When run on the host, the script is intended to be executed as an
unprivileged user and uses sudo to perform actions requiring elevated
privileges. Attempts to run the script as root are rejected unless
--allow-root is specified. When run inside a container, the script
expects to be executed as root.

The --clang option installs and configures the Clang compiler and
linker.
EOF
}

setup_environment() {
    log "install MXL dependencies..."

    export DEBIAN_FRONTEND=noninteractive
    export TZ=Etc/UTC

    safe_sudo "update repositories" apt-get update

    # cmake repository environment dependencies
    local -a cmake_repo_apt_pkgs
    read_list cmake_repo_apt_pkgs "deps/cmake-repo-apt-pkgs.txt"
    safe_sudo "install cmake repo dependencies" apt-get install -y --no-install-recommends "${cmake_repo_apt_pkgs[@]}"
    safe_sudo "update cmake repo" "$SCRIPT_DIR/deps/cmake-repo-upgrade.sh"

    # setup ppa repo (if necessary)
    safe_sudo "setup ppa repository" "$SCRIPT_DIR/deps/ppa-repo-add.sh"
    
    # rustup installer
    safe_sudo "install rustup" "$SCRIPT_DIR/deps/install-rustup.sh"
    
    # MXL build environment dependencies
    local -a config_opts_files=("deps/mxl-apt-pkgs.txt")
    if has_opt "--clang" "${SCRIPT_ARGS[@]}"; then
        config_opts_files+=("deps/mxl-clang-pkgs.txt")
    fi
    
    local -a mxl_apt_pkgs
    echo read_list mxl_apt_pkgs "${config_opts_files[@]}"
    read_list mxl_apt_pkgs "${config_opts_files[@]}"
    safe_sudo "install MXL dependencies" apt-get install -y --no-install-recommends "${mxl_apt_pkgs[@]}"
    safe_sudo "update MXL alternatives" "$SCRIPT_DIR/deps/mxl-update-alternatives.sh"

    export PATH="$HOME/.cargo/bin:$PATH"
    rustup default 1.88.0
}

main() {
    check_help "$@"
    enforce_setup_context "$@"
    setup_environment
}

main "$@"
