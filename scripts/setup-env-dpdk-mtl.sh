#!/usr/bin/env bash
#
# dpdk+mtl build environment setup

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "$SCRIPT_DIR"/module/bootstrap.sh exit_trap.sh logging.sh safe_sudo.sh user_context.sh read_list.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") [--allow-root]

Options:
  --allow-root    Allow execution as root for host builds (normally refused)

Setup environment dependencies for mtl build. The mtl
configuration includes just enough to run the mtl/MXL FATE
regression tests.

When run on the host, the script is intended to be executed as an
unprivileged user and uses sudo to perform actions requiring elevated
privileges. Attempts to run the script as root are rejected unless
--allow-root is specified. When run inside a container, the script
expects to be executed as root.
EOF
}

setup_environment() {
    log "install DPDK +  Intel MTL dependencies..."

    export DEBIAN_FRONTEND=noninteractive
    export TZ=Etc/UTC

    local -a mtl_apt_pkg_files=("deps/mtl-apt-pkgs.txt")

    local -a mtl_apt_pkgs
    read_list mtl_apt_pkgs "${mtl_apt_pkg_files[@]}"

    safe_sudo "install mtl dependencies" apt-get install -y --no-install-recommends "${mtl_apt_pkgs[@]}"
}

main() {
    check_help "$@"
    enforce_setup_context "$@"
    setup_environment "$@"
}

main "$@"
