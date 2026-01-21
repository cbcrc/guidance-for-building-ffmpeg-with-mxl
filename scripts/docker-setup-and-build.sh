#!/usr/bin/env bash
#
# MXL plus FFmpeg full build in Docker container

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "${SCRIPT_DIR}"/module/bootstrap.sh exit_trap.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <build-dir> [--skip-setup] [--extended]

Arguments:
  <build-dir>   Host directory to place build artifacts

Options:
  --skip-setup  Skip environment setup.
  --extended    Include FFmpeg extended build.

Setup container environment and build both MXL and FFmpeg.
EOF
}

main() {
    check_help "$@"
    set_build_dir "$@"

    if ! has_opt "--skip-setup" "$@"; then
        log "environment setup"

        docker rm -f mxl-env-setup 2>/dev/null || true
        docker rmi mxl-env:24.04 2>/dev/null || true

        docker run -it \
            --name mxl-env-setup \
            --volume "$PWD":/src \
            --workdir /src \
            ubuntu:24.04 \
            bash -lc './setup-env-all.sh "$@"' bash "$@"

        docker commit mxl-env-setup mxl-env-ubuntu:24.04
        docker rm mxl-env-setup
    else
        log "skip environment setup"
    fi

    mkdir -p -- "$BUILD_DIR"

    docker run -it --rm \
        --user "$(id -u)":"$(id -g)" \
        --volume "$PWD":/src \
        --volume "$BUILD_DIR":/build \
        --workdir /src \
        mxl-env-ubuntu:24.04 \
        bash -lc './build-mxl.sh /build "$@"' bash "$@"

    docker run -it --rm \
        --user "$(id -u)":"$(id -g)" \
        --volume "$PWD":/src \
        --volume "$BUILD_DIR":/build \
        --workdir /src \
        mxl-env-ubuntu:24.04 \
        bash -lc './build-ffmpeg.sh /build "$@"' bash "$@"

    if has_opt "--extended" "$@"; then
        docker run -e WITH_X265=0 -it --rm \
               --user "$(id -u)":"$(id -g)" \
               --volume "$PWD":/src \
               --volume "$BUILD_DIR":/build \
               --workdir /src \
               mxl-env-ubuntu:24.04 \
               bash -lc './build-ffmpeg-extended.sh /build "$@"' bash --build-all "$@"
    fi

    log "docker interactive shell command:"
    log_cmd docker run -it \
            --rm --user "$(id -u)":"$(id -g)" \
            --volume "$PWD":/src \
            --volume "$BUILD_DIR":/build \
            --workdir /src \
            mxl-env-ubuntu:24.04 \
            bash -li
}

main "$@"
