#!/usr/bin/env bash
#
# FFmpeg feature extended build with MXL support.
#
# Based originally on: https://trac.ffmpeg.org/wiki/CompilationGuide/Ubuntu

set -e

SCRIPT_ARGS=("$@")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export SCRIPT_ARGS SCRIPT_DIR
readonly SCRIPT_ARGS SCRIPT_DIR
# shellcheck source=./module/bootstrap.sh
source "$SCRIPT_DIR"/module/bootstrap.sh exit_trap.sh logging.sh safe_sudo.sh user_context.sh read_list.sh

usage() {
    cat <<EOF
Usage: $(basename "$0") <build-dir> {--build-all} {--build-codecs} {--build-ffmpeg} {--test-ffmpeg} {--help|-h}

  Build FFmpeg with MXL plus a fuller set of codecs.

  - Based on https://trac.ffmpeg.org/wiki/CompilationGuide/Ubuntu
  - Additions: MXL, FATE test support

Environment variables:

   WITH_X264, WITH_X265, WITH_VPX, WITH_AOM,
   WITH_DAV1D, WITH_OPUS, WITH_FDKAAC, WITH_VMAF

   Toggle building each external library.
   1 = build (default), 0 = skip.

Options:
  --build-all            Build codecs, ffmpeg, and run tests.
  --build-codecs         Build codecs
  --build-ffmpeg         Build FFmpeg only (assumes codecs are built)
  --test-ffmpeg          Download FATE test suite and run FATE tests
  --help|-h              Help message

Notes:
  - Enabling WITH_FDKAAC=1 adds --enable-nonfree to FFmpeg;
    redistribution may be restricted.
EOF
}

# build job count
JOBS=$(nproc)

setup_paths() {
    : "${SRC_DIR:?SRC_DIR is not set}"
    : "${BUILD_DIR:?BUILD_DIR is not set}"

    set -x
    local gcc_preset="GCC"
    if has_opt "--mxl-gcc-preset" "$@"; then
      get_opt gcc_preset "--mxl-gcc-preset" "$@"
    fi

    MXL_PRESET="Linux-$gcc_preset-Release"
    MXL_INSTALL="$BUILD_DIR"/mxl/install
    MXL_VARIANT="$MXL_INSTALL/$MXL_PRESET"/static
    
    FFMPEG_SRC="$SRC_DIR/FFmpeg"
    FFMPEG_BUILD="$BUILD_DIR"/ffmpeg.extended/build
    FFMPEG_INSTALL="$BUILD_DIR"/ffmpeg.extended/install
    FFMPEG_BIN="$FFMPEG_INSTALL"/bin
    FFMPEG_FATE_SUITE="$BUILD_DIR"/ffmpeg.extended/fate-suite

    # Paths used by shell
    export PATH="$FFMPEG_BIN:$PATH"

    # pkg-config for extended libs, mxl, and vcpkg (mxl dependency)
    PKG_CONFIG_PATH="$FFMPEG_INSTALL/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
    PKG_CONFIG_PATH="$PKG_CONFIG_PATH:$MXL_VARIANT/lib/pkgconfig:$MXL_VARIANT/x64-linux/lib/pkgconfig"
    export PKG_CONFIG_PATH

    # simplify long names (to make codec builds easier)
    PREFIX="$FFMPEG_INSTALL"
    SRC="$SRC_DIR"
    BIN="$FFMPEG_BIN"

    log "          SRC_DIR = $SRC_DIR"
    log "        BUILD_DIR = $BUILD_DIR"
    log "      MXL_INSTALL = $MXL_INSTALL"
    log "       FFMPEG_SRC = $FFMPEG_SRC"
    log "   FFMPEG_INSTALL = $FFMPEG_INSTALL"
    log "FFMPEG_FATE_SUITE = $FFMPEG_FATE_SUITE"
}

# Build toggles (1=build, 0=skip), default is 1 if the toggle variable
# is not set, or set but empty.
: "${WITH_X264:=1}" 
: "${WITH_X265:=1}" 
: "${WITH_VPX:=1}" 
: "${WITH_AOM:=1}" 
: "${WITH_DAV1D:=1}" 
: "${WITH_OPUS:=1}" 
: "${WITH_FDKAAC:=1}" 
: "${WITH_VMAF:=1}" 

# x264 (source, static)
build_x264() {
    (( WITH_X264 )) || return 0
    log "building x264"
    mkdir -p "$SRC"
    cd "$SRC"
    if [[ ! -d x264 ]]; then
        git clone --depth 1 https://code.videolan.org/videolan/x264.git
    fi
    cd x264
    ./configure --prefix="$PREFIX" --bindir="$BIN" --enable-static --enable-pic
    make -j"$JOBS"
    make install
}

# x265 (source, static)
build_x265() {
    (( WITH_X265 )) || return 0
    log "building x265"
    mkdir -p "$SRC"
    cd "$SRC"

    # subshell to isolate nullglob state
    (
        set -eou pipefail
        shopt -s nullglob
        dirs=(multicoreware*/)      

        if (( ${#dirs[@]} == 0 )); then
            wget -O x265.tar.bz2 https://bitbucket.org/multicoreware/x265_git/get/master.tar.bz2
            tar xjvf x265.tar.bz2
            dirs=(multicoreware*/)
        fi

        cd "${dirs[0]}"/build/linux

        cmake -G "Unix Makefiles" -DCMAKE_INSTALL_PREFIX="$PREFIX" -DENABLE_SHARED=OFF ../../source
        make -j"$JOBS"
        make install
    )

}

# libvpx (source, static)
build_libvpx() {
    (( WITH_VPX )) || return 0
    log "building libvpx"
    mkdir -p "$SRC"
    cd "$SRC"
    if [[ ! -d libvpx ]]; then
        git clone --depth 1 https://chromium.googlesource.com/webm/libvpx
    fi
    cd libvpx
    ./configure --prefix="$PREFIX" --disable-examples --disable-unit-tests --enable-vp9-highbitdepth --as=yasm
    make -j"$JOBS"
    make install
}

# libaom (source, static)
build_libaom() {
    (( WITH_AOM )) || return 0
    log "building libaom"
    mkdir -p "$SRC"
    cd "$SRC"
    if [[ ! -d aom ]]; then
        git clone --depth 1 https://aomedia.googlesource.com/aom
    fi
    cd aom
    mkdir -p build && cd build
    cmake -DCMAKE_INSTALL_PREFIX="$PREFIX" -DBUILD_SHARED_LIBS=0 -DENABLE_TESTS=0 -DENABLE_NASM=1 ..
    make -j"$JOBS"
    make install
}

# libdav1d (source, static)
build_dav1d() {
    (( WITH_DAV1D )) || return 0
    log "building dav1d"
    mkdir -p "$SRC"
    cd "$SRC"
    if [[ ! -d dav1d ]]; then
        git clone --depth 1 https://code.videolan.org/videolan/dav1d.git
    fi
    cd dav1d
    meson setup build --prefix "$PREFIX" --libdir lib -Ddefault_library=static -Denable_tests=false -Denable_tools=false
    ninja -C build -j"$JOBS"
    ninja -C build -j"$JOBS" install
}

# libopus (source, static)
build_opus() {
    (( WITH_OPUS )) || return 0
    log "building opus"
    mkdir -p "$SRC"
    cd "$SRC"
    if [[ ! -d opus ]]; then
        git clone --depth 1 https://github.com/xiph/opus.git
    fi
    cd opus
    ./autogen.sh
    ./configure --prefix="$PREFIX" --disable-shared --enable-static
    make -j"$JOBS"
    make install
}

# libfdk-aac (source, static; nonfree)
build_fdk_aac() {
    (( WITH_FDKAAC )) || return 0
    log "building libfdk-aac"
    mkdir -p "$SRC"
    cd "$SRC"
    if [[ ! -d fdk-aac ]]; then
        git clone --depth 1 https://github.com/mstorsjo/fdk-aac.git
    fi
    cd fdk-aac
    autoreconf -fiv
    ./configure --prefix="$PREFIX" --disable-shared --enable-static
    make -j"$JOBS"
    make install
}

# libvmaf (source, static)
build_vmaf() {
    (( WITH_VMAF )) || return 0
    log "building libvmaf"
    mkdir -p "$SRC"
    cd "$SRC"
    if [[ ! -d vmaf-master ]]; then
        git clone https://github.com/Netflix/vmaf vmaf-master
    fi
    mkdir -p "vmaf-master/libvmaf/build"
    cd "vmaf-master/libvmaf/build"
    meson setup -Denable_tests=false -Denable_docs=false \
          --buildtype=release \
          --default-library=static \
          ../ \
          --prefix "$PREFIX" \
          --bindir "$BIN" \
          --libdir "$PREFIX/lib"
    ninja -j"$JOBS"
    ninja -j"$JOBS" install
}

build_ffmpeg() {
    log "build FFmpeg"

    conf=(
        --prefix="$PREFIX"
        --pkg-config-flags="--static"
        --extra-cflags="-I$PREFIX/include"
        --extra-ldflags="-L$PREFIX/lib"
        --extra-libs="-lpthread -lm"
        --ld="g++"
        --bindir="$BIN"
        # base MXL build options:
        --enable-demuxer=mxl
        --enable-muxer=mxl
        --enable-libmxl
        --enable-muxer=framemd5
        --enable-encoder=pcm_f32le
        --enable-decoder=pcm_f32le
        --enable-encoder=pcm_s16le
        --enable-decoder=pcm_s16le
        --enable-encoder=rawvideo
        --enable-decoder=rawvideo
        --enable-encoder=v210
        --enable-decoder=v210
        --enable-decoder=wrapped_avframe
        --enable-indev=lavfi
        --enable-filter=scale
        --enable-filter=testsrc2
        --enable-filter=anoisesrc
        --enable-filter=sine
        --enable-filter=aresample
        --enable-protocol=pipe
        # extended:
        --enable-gpl
        --enable-gnutls
        --enable-libass
        --enable-libfreetype
        --enable-libfribidi
        --enable-libmp3lame
        --enable-libvorbis
        --samples="$FFMPEG_FATE_SUITE"
        --ignore-tests=source
    )

    (( WITH_X264 ))   && conf+=( --enable-libx264 )
    (( WITH_X265 ))   && conf+=( --enable-libx265 )
    (( WITH_VPX ))    && conf+=( --enable-libvpx )
    (( WITH_AOM ))    && conf+=( --enable-libaom )
    (( WITH_DAV1D ))  && conf+=( --enable-libdav1d )
    (( WITH_OPUS ))   && conf+=( --enable-libopus )
    (( WITH_VMAF ))   && conf+=( --enable-libvmaf )
    (( WITH_FDKAAC )) && conf+=( --enable-libfdk-aac --enable-nonfree )

    # pre-check libmxl resolution
    log_cmd "PKG_CONFIG_PATH=$PKG_CONFIG_PATH"
    if pkg-config --exists libmxl; then
        log "libmxl found by pkg-config"
    else
        log_error "libmxl not found by pkg-config"
    fi

    mkdir -p "$FFMPEG_BUILD"
    pushd "$FFMPEG_BUILD"
    "$FFMPEG_SRC"/configure "${conf[@]}"
    make -j"$JOBS"
    make install

    # sanity check
    "$FFMPEG_BIN"/ffmpeg -version > /dev/null
    "$FFMPEG_BIN"/ffprobe -version > /dev/null
    "$FFMPEG_BIN"/ffplay -version > /dev/null
}

test_ffmpeg() {
    cd "$FFMPEG_BUILD"
    log "running $(make fate-list | wc -l) FATE tests."

    make fate-rsync
    make -j"$JOBS" fate
}

build_codecs() {
    build_x264
    build_x265
    build_libvpx
    build_libaom
    build_dav1d
    build_opus
    build_fdk_aac
    build_vmaf
}

build_all() {
    build_codecs
    build_ffmpeg
    test_ffmpeg
}

main() {
    check_help "$@"

    local SRC_DIR BUILD_DIR
    get_var SRC_DIR "$@" && shift
    get_var BUILD_DIR "$@" && shift
    
    setup_paths "$@"

    enforce_build_context

    if has_opt "--build-ffmpeg" "$@"; then
        build_ffmpeg
    elif has_opt "--test-ffmpeg" "$@"; then
        test_ffmpeg
    elif has_opt "--build-codecs" "$@"; then
        build_codecs
    elif has_opt "--build-all" "$@"; then
        build_all
    else
        usage
        exit 1
    fi
}

main "$@"
