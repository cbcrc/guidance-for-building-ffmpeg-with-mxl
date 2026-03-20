#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  mxl-to-rtsp.sh <ffmpeg-binary>

Description:
  Read one video flow and one audio flow from an MXL domain and publish
  them to an RTSP URL. If ffmpeg exits, it is restarted after 2 seconds.

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
  FFMPEG_LOGLEVEL
        ffmpeg log level
        Default: error

Examples:
  Host:
    MXL_DOMAIN=/dev/shm/mxl \
    VIDEO_ID=11111111-1111-1111-1111-111111111111 \
    AUDIO_ID=22222222-2222-2222-2222-222222222222 \
    RTSP_URL=rtsp://127.0.0.1:8554/live/stream \
    ./mxl-to-rtsp.sh /path/to/ffmpeg

  Container:
    docker run --rm \
      -e MXL_DOMAIN=/domain \
      -e VIDEO_ID=11111111-1111-1111-1111-111111111111 \
      -e AUDIO_ID=22222222-2222-2222-2222-222222222222 \
      -e RTSP_URL=rtsp://127.0.0.1:8554/live/stream \
      -v /host/mxl:/domain \
      ffmpeg-mxl
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    usage
    exit 0
fi

: "${1:?ffmpeg binary required as first argument (use --help for usage)}"
FFMPEG="$1"
shift

if [ ! -x "$FFMPEG" ]; then
    echo "Error: ffmpeg not found or not executable: $FFMPEG" >&2
    exit 1
fi

# --- required parameters ---
: "${MXL_DOMAIN:?required}"
: "${VIDEO_ID:?required}"
: "${AUDIO_ID:?required}"
: "${RTSP_URL:?required}"

# --- optional ---
: "${FFMPEG_LOGLEVEL:=error}"

INPUT="mxl://${MXL_DOMAIN}?id=${VIDEO_ID}&id=${AUDIO_ID}"

echo "Starting mxl-to-rtsp pipeline"
echo "Input:     $INPUT"
echo "Output:    $RTSP_URL"
echo "Loglevel:  $FFMPEG_LOGLEVEL"
echo "FFmpeg:    $FFMPEG"

TERMINATE=false
FFMPEG_PID=""

trap 'TERMINATE=true; [ -n "$FFMPEG_PID" ] && kill -TERM "$FFMPEG_PID" 2>/dev/null || true' SIGINT SIGTERM

while true; do
    "$FFMPEG" \
        -hide_banner \
        -loglevel "$FFMPEG_LOGLEVEL" \
        -i "$INPUT" \
        -f rtsp "$RTSP_URL" &

    FFMPEG_PID=$!
    wait "$FFMPEG_PID" || true

    if "$TERMINATE"; then
        echo "Received termination signal, exiting..." >&2
        exit 0
    fi

    echo "ffmpeg exited, restarting in 2 seconds..." >&2
    sleep 2
done
