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
  FFMPEG_MODE
        Select 'cpu' or 'gpu' H.264 encoding
        Default: 'gpu'
  RTSP_TRANSPORT
        Select 'tcp' or 'udp' RTSP transport
        Default: 'udp'
  FFMPEG_LOGLEVEL
        Select FFmpeg log level
        Default: 'error'

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
: "${FFMPEG_MODE:=gpu}"
: "${RTSP_TRANSPORT:=udp}"
: "${FFMPEG_LOGLEVEL:=error}"
: "${ON_TOO_LATE:=1}"
: "${GRAIN_INDEX_INIT:=0}"

case "$FFMPEG_MODE" in
    gpu|cpu)
        ;;
    *)
        echo "Error: FFMPEG_MODE must be 'gpu' or 'cpu'" >&2
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

INPUT="mxl://${MXL_DOMAIN}?id=${VIDEO_ID}&id=${AUDIO_ID}"

echo "Starting FFmpeg MXL to RTSP transcoder"
echo "FFmpeg:    $FFMPEG"
echo "Loglevel:  $FFMPEG_LOGLEVEL"
echo "Input:     $INPUT"
echo "Mode:      $FFMPEG_MODE"
echo "Output:    $RTSP_URL using $RTSP_TRANSPORT"

TERMINATE=false
FFMPEG_PID=""

trap 'TERMINATE=true; [[ -n "$FFMPEG_PID" ]] && kill -TERM "$FFMPEG_PID" 2>/dev/null || true' SIGINT SIGTERM

run_ffmpeg_cpu() {
    set -x
    "$FFMPEG" \
      -hide_banner -nostats -loglevel "${FFMPEG_LOGLEVEL}" \
      -threads 1 -f mxl -on_too_late "${ON_TOO_LATE}" -grain_index_init "${GRAIN_INDEX_INIT}" \
      -i "${INPUT}" \
      -vf format=yuv420p \
      -c:v libx264 \
      -preset superfast \
      -tune zerolatency \
      -bf 0 \
      -rc-lookahead 0 \
      -g 30 \
      -sc_threshold 0 \
      -crf 20 \
      -x264-params "sliced-threads=1:sync-lookahead=0" \
      -maxrate 12M -bufsize 1M \
      -threads 4 \
      -c:a libopus -b:a 128k -application lowdelay -frame_duration 10 \
      -f rtsp -rtsp_transport "${RTSP_TRANSPORT}" "${RTSP_URL}" &
    set +x

    FFMPEG_PID=$!
}

run_ffmpeg_gpu() {
    set -x
    "$FFMPEG" \
        -hide_banner -nostats -loglevel "${FFMPEG_LOGLEVEL}" \
        -threads 1 -f mxl -on_too_late "${ON_TOO_LATE}" -grain_index_init "${GRAIN_INDEX_INIT}" \
        -i "${INPUT}" \
        -vf "hwupload_cuda,scale_cuda=format=nv12:interp_algo=nearest" \
        -c:v h264_nvenc \
        -pix_fmt cuda \
        -profile:v high \
        -preset p3 \
        -tune ull \
        -zerolatency 1 \
        -delay 0 \
        -bf 0 \
        -g 30 \
        -rc cbr \
        -ldkfs 1 \
        -b:v 20M \
        -maxrate 20M \
        -bufsize 1M \
        -rc-lookahead 0 \
        -surfaces 2 \
        -spatial-aq 1 \
        -temporal-aq 0 \
        -c:a libopus -b:a 128k -application lowdelay -frame_duration 10 \
        -f rtsp -rtsp_transport "${RTSP_TRANSPORT}" "${RTSP_URL}" &
    set +x

    FFMPEG_PID=$!
}

while true; do

    echo "MXL Domain:"
    find "${MXL_DOMAIN}"
    
    case "$FFMPEG_MODE" in
        gpu)
            run_ffmpeg_gpu
            ;;
        cpu)
            run_ffmpeg_cpu
            ;;
        *)
            echo "Error: FFMPEG_MODE must be 'gpu' or 'cpu', got: $FFMPEG_MODE" >&2
            exit 1
            ;;
    esac

    wait "$FFMPEG_PID" || true

    if [[ "$TERMINATE" = "true" ]]; then
        echo "Received termination signal, exiting..." >&2
        exit 0
    fi

    echo "ffmpeg exited, restarting in 2 seconds..." >&2
    sleep 2
done
