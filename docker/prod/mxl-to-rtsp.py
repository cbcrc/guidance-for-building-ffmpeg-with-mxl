#!/usr/bin/env python3

import os
import shlex
import shutil
import signal
import subprocess
import sys
import time


ffmpeg_process = None
terminate_requested = False

USAGE = """\
Usage:
  mxl-to-rtsp.py <ffmpeg-binary>

Description:
  Read a video flow, an audio flow, or both from an MXL domain and publish
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

  RTSP_URL
        Output RTSP URL.
        Example: rtsp://example.com:8554/live/stream

  At least one of:
    VIDEO_ID
        MXL video flow ID (UUID)

    AUDIO_ID
        MXL audio flow ID (UUID)

Optional environment:
  FFMPEG_DEMUX
        Select demuxer instantiation mode.

        single
              Instantiate a single MXL demuxer. The MXL URI contains
              every configured ID: VIDEO_ID, AUDIO_ID, or both. The
              plain demuxer options are used.

        multi
              Instantiate multiple MXL demuxers. One demuxer is
              created for each configured ID. The video-specific (V_*)
              and audio-specific (A_*) demuxer options are used.

        Default: 'single'

  FFMPEG_MODE
        Select 'cpu' or 'gpu' H.264 encoding.
        Has no effect when VIDEO_ID is not specified.
        Default: 'gpu'

  VIDEO_BITRATE
        Set the video bitrate.
        For GPU encoding, sets both -b:v and -maxrate.
        For CPU encoding, sets -maxrate.
        Has no effect when VIDEO_ID is not specified.
        Default: '12M'

  RTSP_TRANSPORT
        Select 'tcp' or 'udp' RTSP transport.
        Default: 'udp'

  FFMPEG_LOGLEVEL
        Select FFmpeg log level.
        Default: 'error'

  FFMPEG_RT_PRIORITY
        Set realtime priority. If set, ffmpeg is started with `chrt`.
        Default: unset

  In single-demux mode, the plain option names are used.

  In multi-demux mode, the A_* and V_* forms apply to the audio and
  video demuxers respectively.

  ON_TOO_LATE
  A_ON_TOO_LATE
  V_ON_TOO_LATE
        Set the FFmpeg -on_too_late option.
        Default: 1 (reset)

  GRAIN_INDEX_INIT
  A_GRAIN_INDEX_INIT
  V_GRAIN_INDEX_INIT
        Set the FFmpeg -grain_index_init option.
        Default: 0 (current)

  BLOCKING
  V_BLOCKING
        Set the FFmpeg -blocking option.
        Default: -1 (auto)

  DIAG_SOCKET
  A_DIAG_SOCKET
  V_DIAG_SOCKET
        Diagnostic socket path.
        Default: unset

Realtime priority in Docker:

  To use FFMPEG_RT_PRIORITY in a Docker container, the container must
  be granted the SYS_NICE capability and an rtprio limit at least as
  high as the requested priority.

  Example:

        docker run --rm \\
          --cap-add=SYS_NICE --ulimit rtprio=20 \\
          --user "$(id -u):$(id -g)" \\
          -e FFMPEG_RT_PRIORITY=20 \\
          ...

  If FFMPEG_RT_PRIORITY is specified and the requested priority
  cannot be set, mxl-to-rtsp.py exits with an error.

FFmpeg MXL demuxer options reference:

$ ./ffmpeg -h demuxer=mxl
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
  Audio and video, single demux:
    MXL_DOMAIN=/dev/shm/mxl
    VIDEO_ID=11111111-1111-1111-1111-111111111111
    AUDIO_ID=22222222-2222-2222-2222-222222222222
    RTSP_URL=rtsp://127.0.0.1:8554/live/stream
    ./mxl-to-rtsp.py /path/to/ffmpeg

  Audio and video, multiple demuxers:
    MXL_DOMAIN=/dev/shm/mxl
    VIDEO_ID=11111111-1111-1111-1111-111111111111
    AUDIO_ID=22222222-2222-2222-2222-222222222222
    FFMPEG_DEMUX=multi
    RTSP_URL=rtsp://127.0.0.1:8554/live/stream
    ./mxl-to-rtsp.py /path/to/ffmpeg

  Video only, single demux:
    MXL_DOMAIN=/dev/shm/mxl
    VIDEO_ID=11111111-1111-1111-1111-111111111111
    RTSP_URL=rtsp://127.0.0.1:8554/live/video
    ./mxl-to-rtsp.py /path/to/ffmpeg

  Audio only, multiple-demux configuration:
    MXL_DOMAIN=/dev/shm/mxl
    AUDIO_ID=22222222-2222-2222-2222-222222222222
    FFMPEG_DEMUX=multi
    RTSP_URL=rtsp://127.0.0.1:8554/live/audio
    ./mxl-to-rtsp.py /path/to/ffmpeg
"""

def env_or_default(name, default):
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def handle_signal(_signum, _frame):
    global terminate_requested, ffmpeg_process

    terminate_requested = True

    if ffmpeg_process is not None and ffmpeg_process.poll() is None:
        ffmpeg_process.terminate()


def check_rt_permission(priority):
    if not priority:
        return None

    chrt_bin = shutil.which("chrt")

    if chrt_bin is None:
        print(
            "Error: FFMPEG_RT_PRIORITY requested, but chrt was not found",
            file=sys.stderr,
        )
        sys.exit(1)

    result = subprocess.run(
        [chrt_bin, "--fifo", priority, "true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    if result.returncode != 0:
        print(
            f"Error: FFMPEG_RT_PRIORITY={priority} requested, but could not set",
            file=sys.stderr,
        )
        sys.exit(1)

    return chrt_bin


def build_mxl_input_options(
    input_url,
    *,
    on_too_late,
    grain_init,
    diag_socket,
    blocking=None,
):
    input_opts = [
        "-f",
        "mxl",
    ]

    if blocking is not None:
        input_opts.extend(["-blocking", blocking])

    input_opts.extend(
        [
            "-on_too_late",
            on_too_late,
            "-grain_index_init",
            grain_init,
        ]
    )

    if diag_socket:
        input_opts.extend(["-diag_socket", diag_socket])

    input_opts.extend(["-i", input_url])

    return input_opts


def build_single_demux_input(
    mxl_domain,
    video_id,
    audio_id,
    blocking,
    on_too_late,
    grain_init,
    diag_socket,
):
    query_parts = []

    if video_id:
        query_parts.append(f"id={video_id}")

    if audio_id:
        query_parts.append(f"id={audio_id}")

    return build_mxl_input_options(
        f"mxl://{mxl_domain}?{'&'.join(query_parts)}",
        blocking=blocking,
        on_too_late=on_too_late,
        grain_init=grain_init,
        diag_socket=diag_socket,
    )


def build_multi_demux_inputs(
    mxl_domain,
    video_id,
    audio_id,
    v_blocking,
    v_on_too_late,
    a_on_too_late,
    v_grain_init,
    a_grain_init,
    v_diag_socket,
    a_diag_socket,
):
    input_opts = []
    input_index = 0

    video_input_index = None
    audio_input_index = None

    if video_id:
        video_input_index = input_index

        input_opts.extend(
            build_mxl_input_options(
                f"mxl://{mxl_domain}?id={video_id}",
                blocking=v_blocking,
                on_too_late=v_on_too_late,
                grain_init=v_grain_init,
                diag_socket=v_diag_socket,
            )
        )

        input_index += 1

    if audio_id:
        audio_input_index = input_index

        input_opts.extend(
            build_mxl_input_options(
                f"mxl://{mxl_domain}?id={audio_id}",
                on_too_late=a_on_too_late,
                grain_init=a_grain_init,
                diag_socket=a_diag_socket,
            )
        )

    if video_id and audio_id:
        input_opts.extend(
            [
                "-map",
                f"{video_input_index}:v:0",
                "-map",
                f"{audio_input_index}:a:0",
            ]
        )

    return input_opts


def build_video_options(mode, video_bitrate):
    if mode == "gpu":
        return [
            "-vf",
            "hwupload_cuda,scale_cuda=format=nv12:interp_algo=nearest",
            "-c:v",
            "h264_nvenc",
            "-pix_fmt",
            "cuda",
            "-profile:v",
            "high",
            "-preset",
            "p3",
            "-tune",
            "ull",
            "-zerolatency",
            "1",
            "-delay",
            "0",
            "-bf",
            "0",
            "-g",
            "30",
            "-rc",
            "cbr",
            "-ldkfs",
            "1",
            "-b:v",
            video_bitrate,
            "-maxrate",
            video_bitrate,
            "-bufsize",
            "1M",
            "-rc-lookahead",
            "0",
            "-surfaces",
            "2",
            "-spatial-aq",
            "1",
            "-temporal-aq",
            "0",
        ]

    return [
        "-vf",
        "format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "superfast",
        "-tune",
        "zerolatency",
        "-bf",
        "0",
        "-rc-lookahead",
        "0",
        "-g",
        "30",
        "-sc_threshold",
        "0",
        "-crf",
        "20",
        "-x264-params",
        "sliced-threads=1:sync-lookahead=0",
        "-maxrate",
        video_bitrate,
        "-bufsize",
        "1M",
        "-threads",
        "4",
    ]


def build_audio_options():
    return [
        "-c:a",
        "libopus",
        "-b:a",
        "128k",
        "-application",
        "lowdelay",
        "-frame_duration",
        "10",
    ]


def build_ffmpeg_cmd(
    ffmpeg_bin,
    mode,
    demux,
    mxl_domain,
    video_id,
    audio_id,
    rtsp_url,
    rtsp_transport,
    loglevel,
    blocking,
    on_too_late,
    a_on_too_late,
    v_on_too_late,
    diag_socket,
    a_diag_socket,
    v_diag_socket,
    grain_init,
    a_grain_init,
    v_grain_init,
    v_blocking,
    video_bitrate,
):
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-nostats",
        "-loglevel",
        loglevel,
        "-threads",
        "1",
    ]

    if demux == "single":
        cmd.extend(
            build_single_demux_input(
                mxl_domain,
                video_id,
                audio_id,
                blocking,
                on_too_late,
                grain_init,
                diag_socket,
            )
        )
    else:
        cmd.extend(
            build_multi_demux_inputs(
                mxl_domain,
                video_id,
                audio_id,
                v_blocking,
                v_on_too_late,
                a_on_too_late,
                v_grain_init,
                a_grain_init,
                v_diag_socket,
                a_diag_socket,
            )
        )

    if video_id:
        cmd.extend(build_video_options(mode, video_bitrate))

    if audio_id:
        cmd.extend(build_audio_options())

    cmd.extend(
        [
            "-f",
            "rtsp",
            "-rtsp_transport",
            rtsp_transport,
            rtsp_url,
        ]
    )

    return cmd


def print_configuration(label, value):
    print(f"{label:<13}{value}", flush=True)


def print_startup_configuration(
    ffmpeg_bin,
    loglevel,
    mxl_domain,
    video_id,
    audio_id,
    demux,
    mode,
    video_bitrate,
    rtsp_url,
    rtsp_transport,
    rt_priority,
    diag_socket,
    a_diag_socket,
    v_diag_socket,
):
    print(
        "Starting FFmpeg MXL to RTSP transcoder",
        flush=True,
    )
    print_configuration("FFmpeg:", ffmpeg_bin)
    print_configuration("Loglevel:", loglevel)
    print_configuration("MXL Domain:", mxl_domain)

    if audio_id:
        print_configuration("Audio ID:", audio_id)

    if video_id:
        print_configuration("Video ID:", video_id)

    print_configuration("Demux:", demux)

    if video_id:
        print_configuration("Mode:", mode)
        print_configuration("Video Rate:", video_bitrate)

    print_configuration("Output:", f"{rtsp_url} using {rtsp_transport}")

    if rt_priority:
        print_configuration("RT Priority:", rt_priority)

    if demux == "single":
        if diag_socket:
            print_configuration("Diag Socket:", diag_socket)
    else:
        if video_id and v_diag_socket:
            print_configuration("Video Diag:", v_diag_socket)

        if audio_id and a_diag_socket:
            print_configuration("Audio Diag:", a_diag_socket)


def main():
    global ffmpeg_process

    if len(sys.argv) < 2:
        print(USAGE, end="")
        return 1

    if sys.argv[1] in ("-h", "--help"):
        print(USAGE, end="")
        return 0

    ffmpeg_bin = sys.argv[1]

    if not os.path.isfile(ffmpeg_bin) or not os.access(ffmpeg_bin, os.X_OK):
        print(
            f"Error: ffmpeg not found or not executable: {ffmpeg_bin}",
            file=sys.stderr,
        )
        return 1

    mxl_domain = os.environ.get("MXL_DOMAIN")
    rtsp_url = os.environ.get("RTSP_URL")

    video_id = env_or_default("VIDEO_ID", "")
    audio_id = env_or_default("AUDIO_ID", "")

    missing = [
        name
        for name, value in (
            ("MXL_DOMAIN", mxl_domain),
            ("RTSP_URL", rtsp_url),
        )
        if not value
    ]

    if missing:
        print(
            f"Error: Missing required environment variables: "
            f"{', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    if not video_id and not audio_id:
        print(
            "Error: at least one of VIDEO_ID or AUDIO_ID is required",
            file=sys.stderr,
        )
        return 1

    ffmpeg_demux = env_or_default("FFMPEG_DEMUX", "single")

    if ffmpeg_demux not in ("single", "multi"):
        print(
            "Error: FFMPEG_DEMUX must be 'single' or 'multi'",
            file=sys.stderr,
        )
        return 1

    ffmpeg_mode = env_or_default("FFMPEG_MODE", "gpu")

    if video_id and ffmpeg_mode not in ("gpu", "cpu"):
        print(
            "Error: FFMPEG_MODE must be 'gpu' or 'cpu'",
            file=sys.stderr,
        )
        return 1

    video_bitrate = env_or_default("VIDEO_BITRATE", "12M")

    rtsp_transport = env_or_default("RTSP_TRANSPORT", "udp")

    if rtsp_transport not in ("tcp", "udp"):
        print(
            "Error: RTSP_TRANSPORT must be 'tcp' or 'udp'",
            file=sys.stderr,
        )
        return 1

    ffmpeg_loglevel = env_or_default("FFMPEG_LOGLEVEL", "error")
    ffmpeg_rt_priority = env_or_default("FFMPEG_RT_PRIORITY", "")

    blocking = env_or_default("BLOCKING", "-1")

    on_too_late = env_or_default("ON_TOO_LATE", "1")
    a_on_too_late = env_or_default("A_ON_TOO_LATE", "1")
    v_on_too_late = env_or_default("V_ON_TOO_LATE", "1")

    grain_init = env_or_default("GRAIN_INDEX_INIT", "0")
    a_grain_init = env_or_default("A_GRAIN_INDEX_INIT", "0")
    v_grain_init = env_or_default("V_GRAIN_INDEX_INIT", "0")

    v_blocking = env_or_default("V_BLOCKING", "-1")

    diag_socket = env_or_default("DIAG_SOCKET", "")
    a_diag_socket = env_or_default("A_DIAG_SOCKET", "")
    v_diag_socket = env_or_default("V_DIAG_SOCKET", "")

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, handle_signal)

    chrt_bin = check_rt_permission(ffmpeg_rt_priority)

    cmd = build_ffmpeg_cmd(
        ffmpeg_bin,
        ffmpeg_mode,
        ffmpeg_demux,
        mxl_domain,
        video_id,
        audio_id,
        rtsp_url,
        rtsp_transport,
        ffmpeg_loglevel,
        blocking,
        on_too_late,
        a_on_too_late,
        v_on_too_late,
        diag_socket,
        a_diag_socket,
        v_diag_socket,
        grain_init,
        a_grain_init,
        v_grain_init,
        v_blocking,
        video_bitrate,
    )

    if ffmpeg_rt_priority:
        cmd = [
            chrt_bin,
            "--fifo",
            ffmpeg_rt_priority,
            *cmd,
        ]

    print_startup_configuration(
        ffmpeg_bin,
        ffmpeg_loglevel,
        mxl_domain,
        video_id,
        audio_id,
        ffmpeg_demux,
        ffmpeg_mode,
        video_bitrate,
        rtsp_url,
        rtsp_transport,
        ffmpeg_rt_priority,
        diag_socket,
        a_diag_socket,
        v_diag_socket,
    )

    while not terminate_requested:
        print(
            f"+ {shlex.join(cmd)}",
            file=sys.stderr,
            flush=True,
        )

        try:
            ffmpeg_process = subprocess.Popen(cmd)
        except OSError as error:
            print(
                f"Error starting ffmpeg: {error}",
                file=sys.stderr,
                flush=True,
            )
            ffmpeg_process = None
        else:
            ffmpeg_process.wait()

        if terminate_requested:
            print(
                "Received termination signal, exiting...",
                file=sys.stderr,
                flush=True,
            )
            break

        print(
            "ffmpeg exited, restarting in 2 seconds...",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(2)

    return 0


if __name__ == "__main__":
    sys.exit(main())

