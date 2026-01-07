#!/usr/bin/env bash
#
# MXL build environment setup
#
# See: https://github.com/dmf-mxl/mxl/blob/main/docs/Building.md

set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}"/module/bootstrap.sh exit_trap.sh logging.sh safe_sudo.sh user_context.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") [--allow-root]

Options:
  --allow-root    Allow execution as root for host builds (normally refused)

When run on the host, the script is intended to be executed as an
unprivileged user and uses sudo to perform actions requiring elevated
privileges. Attempts to run the script as root are rejected unless
--allow-root is specified. When run inside a container, the script
expects to be executed as root.
EOF
}

setup_environment() {
    log "install MXL dependencies..."

    export DEBIAN_FRONTEND=noninteractive
    export TZ=Etc/UTC

    safe_sudo "update repositories" apt-get update

    local -a pkgs_cmake=(
        ca-certificates
        lsb-release
        wget
        gpg
    )

    safe_sudo "install cmake repo dependencies" apt-get install -y --no-install-recommends "${pkgs_cmake[@]}"

    safe_sudo "update cmake repo" "${SCRIPT_DIR}/cmake_repo_upgrade.sh"

    local -a pkgs=(
        curl
        zip
        unzip
        git
        pkg-config
        build-essential
        doxygen
        autoconf
        automake
        libtool
        bison
        flex
        rustup
        clang-19
        cmake
        ninja-build
        libgstreamer1.0-dev
        libgstreamer-plugins-base1.0-dev
    )

    safe_sudo "install MXL dependencies" apt-get install -y --no-install-recommends "${pkgs[@]}"

    rustup default 1.88.0
}

main() {
    check_help "$@"
    enforce_setup_context "$@"
    setup_environment
}

main "$@"
