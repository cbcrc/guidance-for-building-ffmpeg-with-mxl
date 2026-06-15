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

    # grab mxl version and stick it to image tag
    cd "$SRC_DIR/mxl/"
    MXL_TAG=$(git describe --tags)
    cd -
    IMAGE_TAG="ffmpeg-mxl-${MXL_TAG}-dev"
       
    # Prevent Docker-created root-owned bind mounts
    mkdir -p "$SRC_DIR" "$BUILD_DIR"

    local dockerfile="Dockerfile.dev"
    if has_opt "--dockerfile" "$@"; then
        get_opt dockerfile "--dockerfile" "$@"
    fi

    cd "$SCRIPT_DIR"

    docker build -f "$dockerfile" \
           --build-context scripts="$SCRIPT_DIR" \
           --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" \
           --build-arg SETUP_OPTIONS="$*" \
           --build-arg EXTENDED="$EXTENDED" \
           --tag "$IMAGE_TAG" .
    
    docker run --rm \
           --user "$(id -u)":"$(id -g)" \
           --volume "$SCRIPT_DIR":/scripts \
           --volume "$SRC_DIR":/src \
           --volume "$BUILD_DIR":/build \
           "$IMAGE_TAG" \
           /scripts/build-mxl.sh /src /build "$@"
    
    if has_opt "--streaming" "$@"; then
        docker run --rm \
               --user "$(id -u)":"$(id -g)" \
               --volume "$SCRIPT_DIR":/scripts \
               --volume "$SRC_DIR":/src \
               --volume "$BUILD_DIR":/build \
               "$IMAGE_TAG" \
               /scripts/build-codecs.sh /src /build "$@"
    fi
    
    docker run --rm \
           --user "$(id -u)":"$(id -g)" \
           --volume "$SCRIPT_DIR":/scripts \
           --volume "$SRC_DIR":/src \
           --volume "$BUILD_DIR":/build \
           "$IMAGE_TAG" \
           /scripts/build-ffmpeg.sh /src /build "$@"
       
    log "docker interactive shell command:"
    log_cmd docker run -it \
            --rm \
            --volume "$SCRIPT_DIR":/scripts \
            --volume "$SRC_DIR":/src \
            --volume "$BUILD_DIR":/build \
           "$IMAGE_TAG"
}

main "$@"
