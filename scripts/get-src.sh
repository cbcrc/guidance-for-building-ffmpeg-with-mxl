#!/usr/bin/env bash
#
# Clone MXL, FFmpeg, and dependent repositories at known-good
# revisions.

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "$SCRIPT_DIR"/module/bootstrap.sh exit_trap.sh logging.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <src-dir>

Arguments:
  <src-dir>   Directory to place source artifacts

Options:
  --ffmpeg-version <version>
              FFmpeg version to fetch: 8.x-orig, 8.1, 9.0, or master
              Default: 8.1
  --streaming Get x264, opus, nvcodec
  --fate      Get the FFmpeg FATE suite

Environment:
  FATE_SUITE_MIRROR
    Optional rsync source for the FFmpeg FATE suite.
    Default: "rsync://fate.ffmpeg.org/fate-suite/"
    Example: "/mnt/archive/fate-suite/"
    To set up a fate archive use:
      rsync -av rsync://fate.ffmpeg.org/fate-suite /mnt/archive
EOF
}

clone_vcpkg_repo() {
    log "fetch vcpkg git repository..."

    local src_dir="$1"
    cd "$src_dir"

    git clone https://github.com/microsoft/vcpkg
}

clone_mxl_repo() {
    log "fetch MXL git repository..."

    local src_dir="$1"    
    cd "$src_dir"

    git clone https://github.com/dmf-mxl/mxl.git

    cd mxl
    git switch --detach v1.1.0-beta-1
}

clone_ffmpeg_branch() {
    log "fetch FFmpeg git repository..."

    local src_dir="$1"
    local branch="$2"
    local revision="$3"

    cd "$src_dir"

    git clone --single-branch --branch "$branch" https://github.com/cbcrc/FFmpeg.git

    cd FFmpeg
    git switch --detach "$revision"
}

clone_ffmpeg_repo() {
    local src_dir="$1"
    shift

    local ffmpeg_version="8.1"
    if has_opt "--ffmpeg-version" "$@"; then
        get_opt ffmpeg_version "--ffmpeg-version" "$@"
    fi

    case "$ffmpeg_version" in
        8.x-orig)
            clone_ffmpeg_branch "$src_dir" dmf-mxl/8.x-orig 5c5d59370e
            ;;
        8.1)
            clone_ffmpeg_branch "$src_dir" dmf-mxl/8.1 9eddb90ac0
            ;;
        9.0)
            clone_ffmpeg_branch "$src_dir" dmf-mxl/9.0 16abbf0413
            ;;
        master)
            clone_ffmpeg_branch "$src_dir" dmf-mxl/master 361268ffa2
            ;;
        *)
            echo "Unsupported FFmpeg version: $ffmpeg_version" >&2
            echo "Supported versions: 8.x-orig, 8.1, 9.0, master" >&2
            return 1
            ;;
    esac
}

clone_opus_repo() {
    log "fetch Opus git repository..."
    local src_dir="$1"
    cd "$src_dir"
    git clone https://github.com/xiph/opus.git
    cd opus
    git switch --detach v1.6.1
}

clone_nvcodec_repo() {
    log "fetch Nvidia codec headers repository..."
    local src_dir="$1"
    cd "$src_dir"
    git clone  https://git.ffmpeg.org/nv-codec-headers.git
    cd nv-codec-headers
    git switch --detach n12.1.14.0
}

rsync_fate_suite() {
    log "fetch FFmpeg fate test suite ..."
    local src_dir="$1"
    local fate_source="${2:-rsync://fate.ffmpeg.org/fate-suite/}"

    log "FFmpeg fate test suite source: $fate_source"
    rsync -av "$fate_source" "$src_dir/fate-suite/"
}

main() {
    check_help "$@"

    local SRC_DIR
    get_var SRC_DIR "$@" && shift

    mkdir -p "$SRC_DIR"

    clone_vcpkg_repo "$SRC_DIR" "$@"
    clone_mxl_repo "$SRC_DIR" "$@"
    clone_ffmpeg_repo "$SRC_DIR" "$@"

    if has_opt "--streaming" "$@"; then
        clone_x264_repo "$SRC_DIR" "$@"
        clone_opus_repo "$SRC_DIR" "$@"
        clone_nvcodec_repo "$SRC_DIR" "$@"
    fi
    if has_opt "--fate" "$@"; then
        rsync_fate_suite "$SRC_DIR" "${FATE_SUITE_MIRROR:-}"
    fi
}

main "$@"
