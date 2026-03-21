# syntax=docker/dockerfile:1.6

# Runtime image for the FFmpeg/MXL to RTSP pipeline.
#
# This is a multi-stage build:
#   1. The builder stage compiles MXL, codec dependencies, and FFmpeg.
#   2. The runtime stage contains only the runtime packages, the built
#      FFmpeg install tree under /opt, and the mxl-to-rtsp.sh launcher.
#
# The container starts by running:
#   /usr/local/bin/mxl-to-rtsp.sh /opt/bin/ffmpeg
#
# The launcher script is configured at runtime using environment
# variables such as:
#   MXL_DOMAIN
#   VIDEO_ID
#   AUDIO_ID
#   RTSP_TRANSPORT
#   RTSP_URL
#   FFMPEG_MOD
#   FFMPEG_LOGLEVEL
#
# See `mxl-to-rtsp.sh --help` for runtime configuration details.
#
# This image is intended to act as a parameterized appliance:
# it provides a fixed FFmpeg+MXL runtime, while the source and
# destination are supplied when the container is launched.

FROM ubuntu:24.04 AS builder

ARG UID=1000
ARG GID=1000

COPY scripts /scripts

RUN echo "container" > /run/ffmpeg-build-context && /scripts/setup-env-all.sh --streaming

RUN set -e; \
    if ! getent group "${GID}" >/dev/null; then \
        groupadd -g "${GID}" builder; \
    fi; \
    if ! id -u "${UID}" >/dev/null 2>&1; then \
        useradd -m -u "${UID}" -g "${GID}" builder; \
    fi

RUN install -d -o ${UID} -g ${GID} /build
RUN install -d -o ${UID} -g ${GID} /src

USER ${UID}:${GID}

RUN rsync ${FATE_SUITE_MIRROR} /src

ARG FATE_SUITE_MIRROR
RUN if [ -n "${FATE_SUITE_MIRROR:-}" ]; then \
        export FATE_SUITE_MIRROR; \
    fi; \
    /scripts/get-src.sh /src --streaming
    
RUN /scripts/build-mxl.sh /src /build --prod
RUN /scripts/build-codecs.sh /src /build
RUN /scripts/build-ffmpeg.sh /src /build --prod --streaming --no-ffplay

FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    ca-certificates \
    zlib1g \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/ffmpeg/install/Linux-GCC-Release/static /opt

COPY docker/prod/mxl-to-rtsp.sh /usr/local/bin/mxl-to-rtsp.sh
RUN chmod +x /usr/local/bin/mxl-to-rtsp.sh

ENTRYPOINT ["/usr/local/bin/mxl-to-rtsp.sh", "/opt/bin/ffmpeg"]
