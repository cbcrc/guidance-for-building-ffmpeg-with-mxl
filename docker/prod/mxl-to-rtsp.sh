#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  mxl-to-rtsp.sh <ffmpeg-binary>

Description:
  Read one video flow and one audio flow from an MXL domain and publish
  them to an RTSP URL. If ffmpeg exits, it is restarted after 2 seconds.

  To use GPU encoding in a Docker container, the
  `nvidia-container-toolkit` must be installed on the host, and Docker
  must be configured to use it. To verify that a Docker container can
  see the GPU, run:

  $ docker run --rm --gpus all ubuntu:24.04 nvidia-smi

  See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

Arguments:
  <ffmpeg-binary>
        Path to the ffmpeg executable to run.
        In the container this is typically: /opt/bin/ffmpeg

Required environment:
  MXL_DOMAIN
        Path to the MXL domain directory.
        Example: /domain

  VIDEO_ID
        MXL video flow ID (UUID)

  AUDIO_ID
        MXL audio flow ID (UUID)

  RTSP_URL
        Output RTSP URL
        Example: rtsp://example.com:8554/live/stream

Optional environment:
  FFMPEG_DEMUX
        Select 'single' or 'multi' demux
        Default: 'multi'
  FFMPEG_MODE
        Select 'cpu' or 'gpu' H.264 encoding
        Default: 'gpu'
  RTSP_TRANSPORT
        Select 'tcp' or 'udp' RTSP transport
        Default: 'udp'
  FFMPEG_LOGLEVEL
        Select FFmpeg log level
        Default: 'error'
  ON_TOO_LATE, V_ON_TOO_LATE, A_ON_TOO_LATE
        Set the FFmpeg -on_too_late option. A_ and V_ apply to the multi-demux case
        Default: 1 (reset)
  GRAIN_INDEX_INIT, A_GRAIN_INDEX_INIT, V_GRAIN_INDEX_INIT
        Set the FFmpeg -grain_index_init option. A_ and V_ apply to the multi-demuxer case
        Default: 0 (current)
  V_BLOCKING
        Set the FFmpeg -blocking option. Only applies to the multi-demuxer video case.
        Default: 1 (blocking)
  FFMPEG_RT_PRIORITY
        Set real time priority. If set then the process is started with `chrt`
        Default: unset
  DIAG_SOCKET, V_DIAG_SOCKET, A_DIAG_SOCKET
        Diagnostic socket path.

From: ./ffmpeg -h demuxer=mxl
mxl demuxer AVOptions:
  -blocking          <int>        .D......... Use blocking video read: auto (default), 0=non-blocking, 1=blocking (from -1 to 1) (default -1)
  -grain_index_init  <int>        .D......... initial MXL grain index (from 0 to 2) (default current)
     current         0            .D......... current time
     head            1            .D......... ring buffer head
     tail            2            .D......... ring buffer tail
  -on_too_late       <int>        .D......... action when MXL reports grain index too late (from 0 to 1) (default increment)
     increment       0            .D......... increment the grain index
     reset           1            .D......... reset to position defined by grain_index_init
  -diag_socket       <string>     .D......... Unix domain socket path for diagnostic monitoring

Examples:
  Host:
    MXL_DOMAIN=/dev/shm/mxl \
    VIDEO_ID=11111111-1111-1111-1111-111111111111 \
    AUDIO_ID=22222222-2222-2222-2222-222222222222 \
    RTSP_URL=rtsp://127.0.0.1:8554/live/stream \
    ./mxl-to-rtsp.sh /path/to/ffmpeg

  Container:
    docker run --rm --gpus all \
      -e MXL_DOMAIN=/domain \
      -e VIDEO_ID=11111111-1111-1111-1111-111111111111 \
      -e AUDIO_ID=22222222-2222-2222-2222-222222222222 \
      -e RTSP_URL=rtsp://192.168.1.100:8554/live/stream \
      -v /dev/shm/mxl:/domain \
      ffmpeg-mxl
EOF
}

if [[ "${1:-}" = "--help" ]] || [[ "${1:-}" = "-h" ]]; then
    usage
    exit 0
fi

: "${1:?ffmpeg binary required as first argument (use --help for usage)}"
FFMPEG="$1"
shift

if [[ ! -x "$FFMPEG" ]]; then
    echo "Error: ffmpeg not found or not executable: $FFMPEG" >&2
    exit 1
fi

# --- required parameters ---
: "${MXL_DOMAIN:?required}"
: "${VIDEO_ID:?required}"
: "${AUDIO_ID:?required}"
: "${RTSP_URL:?required}"

# --- optional ---
: "${FFMPEG_RT_PRIORITY:=}"
: "${FFMPEG_DEMUX:=multi}"
: "${FFMPEG_MODE:=gpu}"
: "${RTSP_TRANSPORT:=udp}"
: "${FFMPEG_LOGLEVEL:=error}"
: "${ON_TOO_LATE:=1}"
: "${A_ON_TOO_LATE:=1}"
: "${V_ON_TOO_LATE:=1}"
: "${GRAIN_INDEX_INIT:=0}"
: "${A_GRAIN_INDEX_INIT:=0}"
: "${V_GRAIN_INDEX_INIT:=0}"
: "${V_BLOCKING:=1}"
: "${DIAG_SOCKET:=}"
: "${A_DIAG_SOCKET:=}"
: "${V_DIAG_SOCKET:=}"

case "$FFMPEG_MODE" in
    gpu|cpu)
        ;;
    *)
        echo "Error: FFMPEG_MODE must be 'gpu' or 'cpu'" >&2
        exit 1
        ;;
esac

case "$FFMPEG_DEMUX" in
    multi|single)
    ;;
    *)
        echo "Error: FFMPEG_DEMUX must be 'multi' or 'single'" >&2
        exit 1
        ;;
esac

case "$RTSP_TRANSPORT" in
    tcp|udp)
        ;;
    *)
        echo "Error: RTSP_TRANSPORT must be 'tcp' or 'udp'" >&2
        exit 1
        ;;
esac

AV_INPUT="mxl://${MXL_DOMAIN}?id=${VIDEO_ID}&id=${AUDIO_ID}"
A_INPUT="mxl://${MXL_DOMAIN}?id=${AUDIO_ID}"
V_INPUT="mxl://${MXL_DOMAIN}?id=${VIDEO_ID}"

echo "Starting FFmpeg MXL to RTSP transcoder"
echo "FFmpeg:      $FFMPEG"
echo "Loglevel:    $FFMPEG_LOGLEVEL"
echo "MXL Domain:  $MXL_DOMAIN"
echo "Audio ID:    $AUDIO_ID"
echo "Video ID:    $VIDEO_ID"
echo "Demux:       $FFMPEG_DEMUX"
echo "Mode:        $FFMPEG_MODE"
echo "Output:      $RTSP_URL using $RTSP_TRANSPORT"
echo "RT Priority: $FFMPEG_RT_PRIORITY"

TERMINATE=false
FFMPEG_PID=""

trap 'TERMINATE=true; if [[ -n "$FFMPEG_PID" ]]; then kill -TERM "$FFMPEG_PID" 2>/dev/null || true; fi' SIGINT SIGTERM

check_rt_permission() {
    if [[ -n "${FFMPEG_RT_PRIORITY:-}" ]]; then
        if ! chrt --fifo "${FFMPEG_RT_PRIORITY}" true >/dev/null 2>&1; then
            echo "FFMPEG_RT_PRIORITY=${FFMPEG_RT_PRIORITY} requested, but could not set" >&2
            exit 1
        fi
    fi
}

run_with_optional_rt() {
    set -x
    if [[ -n "${FFMPEG_RT_PRIORITY:-}" ]]; then
        chrt --fifo "${FFMPEG_RT_PRIORITY}" "$@" &
    else
        "$@" &
    fi
    set +x
    FFMPEG_PID=$!
}

run_ffmpeg_cpu_single_demux() {
    local ffmpeg_args=(
        "$FFMPEG"
        -hide_banner -nostats -loglevel "${FFMPEG_LOGLEVEL}"
        -threads 1
        -f mxl
        -on_too_late "${ON_TOO_LATE}"
        -grain_index_init "${GRAIN_INDEX_INIT}"
    )

    if [[ -n ${DIAG_SOCKET:-} ]]; then
        ffmpeg_args+=(-diag_socket "$DIAG_SOCKET")
    fi

    ffmpeg_args+=(
        -i "${AV_INPUT}"
        -vf format=yuv420p
        -c:v libx264
        -preset superfast
        -tune zerolatency
        -bf 0
        -rc-lookahead 0
        -g 30
        -sc_threshold 0
        -crf 20
        -x264-params "sliced-threads=1:sync-lookahead=0"
        -maxrate 12M -bufsize 1M
        -threads 4
        -c:a libopus -b:a 128k -application lowdelay -frame_duration 10
        -f rtsp -rtsp_transport "${RTSP_TRANSPORT}" "${RTSP_URL}"
    )

    run_with_optional_rt "${ffmpeg_args[@]}"
}

run_ffmpeg_cpu_multi_demux() {
    local ffmpeg_args=(
        "$FFMPEG"
        -hide_banner -nostats -loglevel "${FFMPEG_LOGLEVEL}"
        -threads 1
        -f mxl
        -blocking "${V_BLOCKING}"
        -on_too_late "${V_ON_TOO_LATE}"
        -grain_index_init "${V_GRAIN_INDEX_INIT}"
    )

    if [[ -n ${V_DIAG_SOCKET:-} ]]; then
        ffmpeg_args+=(-diag_socket "$V_DIAG_SOCKET")
    fi

    ffmpeg_args+=(
        -i "${V_INPUT}"
        -f mxl
        -on_too_late "${A_ON_TOO_LATE}"
        -grain_index_init "${A_GRAIN_INDEX_INIT}"
    )

    if [[ -n ${A_DIAG_SOCKET:-} ]]; then
        ffmpeg_args+=(-diag_socket "$A_DIAG_SOCKET")
    fi

    ffmpeg_args+=(
        -i "${A_INPUT}"
        -map 0:v:0 -map 1:a:0
        -vf format=yuv420p
        -c:v libx264
        -preset superfast
        -tune zerolatency
        -bf 0
        -rc-lookahead 0
        -g 30
        -sc_threshold 0
        -crf 20
        -x264-params "sliced-threads=1:sync-lookahead=0"
        -maxrate 12M -bufsize 1M
        -threads 4
        -c:a libopus -b:a 128k -application lowdelay -frame_duration 10
        -f rtsp -rtsp_transport "${RTSP_TRANSPORT}" "${RTSP_URL}"
    )

    run_with_optional_rt "${ffmpeg_args[@]}"
}

run_ffmpeg_gpu_single_demux() {
    local ffmpeg_args=(
        "$FFMPEG"
        -hide_banner -nostats -loglevel "${FFMPEG_LOGLEVEL}"
        -threads 1
        -f mxl
        -on_too_late "${ON_TOO_LATE}"
        -grain_index_init "${GRAIN_INDEX_INIT}"
    )

    if [[ -n ${DIAG_SOCKET:-} ]]; then
        ffmpeg_args+=(-diag_socket "$DIAG_SOCKET")
    fi

    ffmpeg_args+=(
        -i "${AV_INPUT}"
        -vf "hwupload_cuda,scale_cuda=format=nv12:interp_algo=nearest"
        -c:v h264_nvenc
        -pix_fmt cuda
        -profile:v high
        -preset p3
        -tune ull
        -zerolatency 1
        -delay 0
        -bf 0
        -g 30
        -rc cbr
        -ldkfs 1
        -b:v 20M
        -maxrate 12M
        -bufsize 1M
        -rc-lookahead 0
        -surfaces 2
        -spatial-aq 1
        -temporal-aq 0
        -c:a libopus -b:a 128k -application lowdelay -frame_duration 10
        -f rtsp -rtsp_transport "${RTSP_TRANSPORT}" "${RTSP_URL}"
    )

    run_with_optional_rt "${ffmpeg_args[@]}"
}


run_ffmpeg_gpu_multi_demux() {
    local ffmpeg_args=(
        "$FFMPEG"
        -hide_banner -nostats -loglevel "${FFMPEG_LOGLEVEL}"
        -threads 1
        -f mxl
        -blocking "${V_BLOCKING}"
        -on_too_late "${V_ON_TOO_LATE}"
        -grain_index_init "${V_GRAIN_INDEX_INIT}"
    )

    if [[ -n ${V_DIAG_SOCKET:-} ]]; then
        ffmpeg_args+=(-diag_socket "$V_DIAG_SOCKET")
    fi

    ffmpeg_args+=(
        -i "${V_INPUT}"
        -f mxl
        -on_too_late "${A_ON_TOO_LATE}"
        -grain_index_init "${A_GRAIN_INDEX_INIT}"
    )

    if [[ -n ${A_DIAG_SOCKET:-} ]]; then
        ffmpeg_args+=(-diag_socket "$A_DIAG_SOCKET")
    fi

    ffmpeg_args+=(
        -i "${A_INPUT}"
        -map 0:v:0 -map 1:a:0
        -vf "hwupload_cuda,scale_cuda=format=nv12:interp_algo=nearest"
        -c:v h264_nvenc
        -pix_fmt cuda
        -profile:v high
        -preset p3
        -tune ull
        -zerolatency 1
        -delay 0
        -bf 0
        -g 30
        -rc cbr
        -ldkfs 1
        -b:v 20M
        -maxrate 12M
        -bufsize 1M
        -rc-lookahead 0
        -surfaces 2
        -spatial-aq 1
        -temporal-aq 0
        -c:a libopus -b:a 128k -application lowdelay -frame_duration 10
        -f rtsp -rtsp_transport "${RTSP_TRANSPORT}" "${RTSP_URL}"
    )

    run_with_optional_rt "${ffmpeg_args[@]}"
}

run_ffmpeg() {

    case "$FFMPEG_MODE:$FFMPEG_DEMUX" in
        gpu:multi)
            run_ffmpeg_gpu_multi_demux
            ;;
        gpu:single)
            run_ffmpeg_gpu_single_demux
            ;;
        cpu:multi)
            run_ffmpeg_cpu_multi_demux
            ;;
        cpu:single)
            run_ffmpeg_cpu_single_demux
            ;;
    esac
}

check_rt_permission

while true; do

    echo "MXL Domain:"
    if [[ -d "$MXL_DOMAIN" ]]; then
        find "$MXL_DOMAIN"
    else
        echo "Warning: MXL domain not found: $MXL_DOMAIN" >&2
    fi

    run_ffmpeg
    
    wait "$FFMPEG_PID" || true

    if [[ "$TERMINATE" = "true" ]]; then
        echo "Received termination signal, exiting..." >&2
        exit 0
    fi

    echo "ffmpeg exited, restarting in 2 seconds..." >&2
    sleep 2
done
