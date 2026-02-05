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
EOF
}

clone_vcpkg_repo() {
    log "fetch vcpkg git repository..."

    local src_dir="$1"
    mkdir -p "$src_dir"
    cd "$src_dir"

    git clone https://github.com/microsoft/vcpkg
}

# Use a release/1.0 commit hash that includes
# https://github.com/dmf-mxl/mxl/commit/0e3825685c3ca0bfd71145326ec398b341a9fdd2
# pending final 1.0 release tag.
clone_mxl_repo() {
    log "fetch MXL git repository..."

    local src_dir="$1"    
    mkdir -p "$src_dir"
    cd "$src_dir"

    git clone https://github.com/dmf-mxl/mxl.git

    cd mxl
    git switch --detach 0e38256 

    # optional patch
    if has_opt "--mxl-patch" "$@"; then
      local patchfile;
      get_opt patchfile "--mxl-patch" "$@"
      log "MXL patch file: $patchfile"
      git apply "$SCRIPT_DIR"/patches/"$patchfile"
    fi
}

clone_ffmpeg_repo() {
    log "fetch FFmpeg git repository..."

    local src_dir="$1"
    mkdir -p "$src_dir"
    cd "$src_dir"

    git clone --single-branch --branch dmf-mxl/master --depth 1 https://github.com/cbcrc/FFmpeg.git

    cd FFmpeg
    git switch --detach ea2cb90
}

main() {
    check_help "$@"

    local SRC_DIR
    get_var SRC_DIR "$@" && shift

    clone_vcpkg_repo "$SRC_DIR" "$@"
    clone_mxl_repo "$SRC_DIR" "$@"
    clone_ffmpeg_repo "$SRC_DIR" "$@"
}

main "$@"
