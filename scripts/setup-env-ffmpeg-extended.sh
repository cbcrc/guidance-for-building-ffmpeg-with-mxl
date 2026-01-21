#!/usr/bin/env bash
#
# FFmpeg extended build environment setup

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "${SCRIPT_DIR}"/module/bootstrap.sh exit_trap.sh logging.sh safe_sudo.sh user_context.sh read_list.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") [--allow-root]

Options:
  --allow-root    Allow execution as root for host builds (normally refused)

Setup environment dependencies for the extended ffmpeg build.

When run on the host, the script is intended to be executed as an
unprivileged user and uses sudo to perform actions requiring elevated
privileges. Attempts to run the script as root are rejected unless
--allow-root is specified. When run inside a container, the script
expects to be executed as root.
EOF
}

setup_environment() {
    log "installing FFmpeg extended build prerequisites"

    local pkgs=(
        texinfo
        yasm
        nasm
        meson
        libgnutls28-dev
        libass-dev
        libfreetype6-dev
        libfribidi-dev
        libvorbis-dev
        libmp3lame-dev
        libnuma-dev      # required by the x265 codec build
        libunistring-dev # required by ffmpeg itself
        rsync
        wget
        tar
    )
    
    safe_sudo "install ffmpeg-extended build dependencies" apt-get install -y --no-install-recommends "${pkgs[@]}"
}

main() {
    check_help "$@"
    enforce_setup_context "$@"
    setup_environment
}

main "$@"
