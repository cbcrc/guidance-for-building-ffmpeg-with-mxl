#!/usr/bin/env bash
#
# MXL plus FFmpeg full build in Docker container

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "$SCRIPT_DIR"/module/bootstrap.sh exit_trap.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <src-dir> <build-dir>

Arguments:
  <src-dir>     Directory to find src artifacts
  <build-dir>   Directory to write build artifacts

Prepare Dockerfile.dev container and build source located at
<src-dir>. Populate <src-dir> with get-src.sh before invoking this
script. The command-line arguments are passed through to build-mxl.sh
and build-ffmpeg.sh (e.g. --dev or --prod).
EOF
}

main() {
    check_help "$@"
    get_var SRC_DIR "$@" && shift
    get_var BUILD_DIR "$@" && shift

    local EXTENDED=0
    if has_opt --extended "$@"; then
        EXTENDED=1
    fi
       
    # Prevent Docker-created root-owned bind mounts
    mkdir -p "$SRC_DIR" "$BUILD_DIR"

    local dockerfile="Dockerfile.dev"
    if has_opt "--dockerfile" "$@"; then
      get_opt gcc_preset "--dockerfile" "$@"
    fi

    cd "$SCRIPT_DIR"

    docker build -f "$dockerfile" \
           --build-context scripts=${SCRIPT_DIR} \
           --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" \
           --build-arg EXTENDED="$EXTENDED" \
           --tag mxl-dev .
    
    docker run --rm \
           --user "$(id -u)":"$(id -g)" \
           --volume "$SCRIPT_DIR":/scripts \
           --volume "$SRC_DIR":/src \
           --volume "$BUILD_DIR":/build \
           mxl-dev \
           /scripts/build-mxl.sh /src /build "$@"

    docker run --rm \
           --user "$(id -u)":"$(id -g)" \
           --volume "$SCRIPT_DIR":/scripts \
           --volume "$SRC_DIR":/src \
           --volume "$BUILD_DIR":/build \
           mxl-dev \
           /scripts/build-ffmpeg.sh /src /build "$@"
       
    if has_opt "--extended" "$@"; then
        docker run --rm \
               --user "$(id -u)":"$(id -g)" \
               --volume "$SCRIPT_DIR":/scripts \
               --volume "$SRC_DIR":/src \
               --volume "$BUILD_DIR":/build \
               -e WITH_X265=0 \
               -e WITH_VMAF=0
               mxl-dev \
               /scripts/build-ffmpeg-extended.sh /src /build --build-all "$@"
    fi

    log "docker interactive shell command:"
    log_cmd docker run -it \
            --rm \
            --volume "$SRC_DIR":/src \
            --volume "$BUILD_DIR":/build \
            mxl-dev
}

main "$@"
