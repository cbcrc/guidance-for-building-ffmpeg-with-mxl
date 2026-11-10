#!/usr/bin/env python3

import os
import re
import shlex
import signal
import subprocess
import sys
import time


ffmpeg_process = None
terminate_requested = False

USAGE = """\
Usage:
  mxl-to-st2110.py

Description:
  Bridge a video flow between an MXL domain and an ST 2110-20 stream,
  using the Intel Media Transport Library (MTL) FFmpeg plugins
  (mtl_st20p). If ffmpeg exits, it is restarted after 2 seconds.

  Two directions are supported, selected with DIRECTION:

  rx (ST 2110 -> MXL)
        Receive an ST 2110-20 video stream from the network and write
        it to an MXL flow.

  tx (MXL -> ST 2110)
        Read a video flow from an MXL domain and send it as an
        ST 2110-20 stream on the network.

  This script requires MTL to be set up on the host (hugepages, bound
  NIC, and running mtl-manager) and the container must be granted
  access to /dev/vfio and the SYS_NICE capability. See
  ../../docs/st_2110.md for details.

Required environment (both directions):
  FFMPEG_BIN
        Path to ffmpeg binary
        Default: /opt/bin/ffmpeg

  DIRECTION
        Select 'rx' (ST 2110 -> MXL) or 'tx' (MXL -> ST 2110).

  MXL_DOMAIN
        Path to the MXL domain directory.
        Example: /domain

  VIDEO_FLOW_IDs
        Space- or comma-separated list of MXL video flow IDs (UUIDs),
        one per session.
        In 'rx' mode, these are the flows written to the MXL domain.
        In 'tx' mode, these are the flows read from the MXL domain.
        Must have as many entries as RX_VIDEO_MCAST_IP / TX_VIDEO_MCAST_IP.

  LOCAL_IFACE_IP
        IP address assigned to the local ST 2110 interface (-p_sip).

  PCI_ADDR
        PCI address of the (virtual) NIC function bound to the
        ST 2110 interface (-p_port).

  RX_VIDEO_MCAST_IPs  (DIRECTION=rx only)
        Space- or comma-separated list of source multicast IP addresses
        of the incoming ST 2110-20 video streams (-p_rx_ip), one per
        Rx session.

  TX_VIDEO_MCAST_IPs  (DIRECTION=tx only)
        Space- or comma-separated list of destination multicast IP
        addresses for the outgoing ST 2110-20 video streams (-p_tx_ip),
        one per Tx session.

Optional environment (both directions):
  UDP_PORT
        ST 2110 UDP port.
        Default: '20000'

  PAYLOAD_TYPE
        RTP payload type.
        Default: '96'

  FPS
        Video frame rate.
        Default: '29.97'

  VIDEO_SIZE
        Video frame size.
        Default: '1920x1080'

  PIX_FMT
        Pixel format used on the ST 2110 side (-pix_fmt).
        Default: 'yuv422p10le'

  INTERLACED
        Set the FFmpeg -interlaced option.
        Default: '1'

  PACING_WAY
        Set the FFmpeg -pacing_way option.
        Default: 'tsc'

  FFMPEG_LOGLEVEL
        Select FFmpeg log level.
        Default: 'error'

Optional environment, DIRECTION=rx only:
  DEINTERLACE
        Apply a 'yadif' deinterlace filter between the ST 2110 input
        and the MXL output.
        Allowed values: 1, true, yes
        Default: unset (disabled)

  MXL_VIDEO_CODEC
        Codec used to write the video flow to MXL (-c:v).
        Default: 'v210'

Optional environment, DIRECTION=tx only:
  BLOCKING
        Set the FFmpeg MXL demuxer -blocking option.
        Default: '-1' (auto)

  ON_TOO_LATE
        Set the FFmpeg MXL demuxer -on_too_late option.
        Default: '1' (reset)

  MXL_READ_INDEX_INIT
        Set the FFmpeg -mxl_read_index_init option.
        Allowed values: current, head, tail
        Default: head

  DIAG_SOCKET
        Diagnostic socket path for the MXL demuxer.
        Default: unset

Examples:
  ST 2110 -> MXL:
    DIRECTION=rx
    MXL_DOMAIN=/domain
    VIDEO_FLOW_IDs="fe781cad-8a82-4b8e-a3c2-f833c70ac730 fe781cad-8a82-4b8e-a3c2-f833c70ac731"
    LOCAL_IFACE_IP=192.168.1.10
    PCI_ADDR=0000:2a:11.0
    RX_VIDEO_MCAST_IPs="239.1.1.1 239.1.1.3"
    ./st2110.py /path/to/ffmpeg

  MXL -> ST 2110:
    DIRECTION=tx
    MXL_DOMAIN=/domain
    VIDEO_FLOW_IDs="fe781cad-8a82-4b8e-a3c2-f833c70ac730 fe781cad-8a82-4b8e-a3c2-f833c70ac731"
    LOCAL_IFACE_IP=192.168.1.10
    PCI_ADDR=0000:2a:11.1
    TX_VIDEO_MCAST_IPs="239.1.1.2 239.1.1.4"
    ./st2110.py /path/to/ffmpeg
"""


def env_or_default(name, default):
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def env_list(name):
    return [item for item in re.split(r"[\s,]+", os.environ.get(name, "")) if item]


def env_flag_enabled(name):
    value = os.environ.get(name, "")
    return value.lower() in ("1", "true", "yes")


def handle_signal(_signum, _frame):
    global terminate_requested, ffmpeg_process

    terminate_requested = True

    if ffmpeg_process is not None and ffmpeg_process.poll() is None:
        ffmpeg_process.terminate()


def build_rx_cmd(
    ffmpeg_bin,
    loglevel,
    mxl_domain,
    video_flow_ids,
    local_iface_ip,
    pci_addr,
    video_mcast_ips,
    udp_port,
    payload_type,
    fps,
    video_size,
    pix_fmt,
    interlaced,
    pacing_way,
    deinterlace,
    mxl_video_codec,
):
    cmd = [ffmpeg_bin, "-hide_banner", "-nostats", "-loglevel", loglevel]

    # One ST 2110 input per Rx session
    for index, mcast_ip in enumerate(video_mcast_ips):
        cmd.extend(
            [
                "-pacing_way",
                pacing_way,
                "-interlaced",
                interlaced,
                "-p_port",
                pci_addr,
                "-p_sip",
                local_iface_ip,
                "-p_rx_ip",
                mcast_ip,
                "-udp_port",
                udp_port,
                "-payload_type",
                payload_type,
                "-fps",
                fps,
                "-pix_fmt",
                pix_fmt,
                "-video_size",
                video_size,
                "-f",
                "mtl_st20p",
                "-i",
                f"rx{index}",
            ]
        )

    # One MXL output per Rx session
    for index, flow_id in enumerate(video_flow_ids):
        cmd.extend(["-map", f"{index}:v:0"])

        if deinterlace:
            cmd.extend(["-vf", "yadif"])

        cmd.extend(
            [
                "-c:v",
                mxl_video_codec,
                "-f",
                "mxl",
                "-video_flow_id",
                flow_id,
                mxl_domain,
            ]
        )

    return cmd


def build_tx_cmd(
    ffmpeg_bin,
    loglevel,
    mxl_domain,
    video_flow_ids,
    local_iface_ip,
    pci_addr,
    video_mcast_ips,
    udp_port,
    payload_type,
    fps,
    video_size,
    pix_fmt,
    interlaced,
    pacing_way,
    blocking,
    on_too_late,
    mxl_read_index_init,
    diag_socket,
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

    # One MXL input per Tx session
    for flow_id in video_flow_ids:
        cmd.extend(
            [
                "-f",
                "mxl",
                "-blocking",
                blocking,
                "-on_too_late",
                on_too_late,
                "-mxl_read_index_init",
                mxl_read_index_init,
            ]
        )

        if diag_socket:
            cmd.extend(["-diag_socket", diag_socket])

        cmd.extend(["-i", f"mxl://{mxl_domain}?id={flow_id}"])

    # One ST 2110 output per Tx session
    for index, mcast_ip in enumerate(video_mcast_ips):
        cmd.extend(
            [
                "-map",
                f"{index}:v:0",
                "-pix_fmt",
                pix_fmt,
                "-vcodec",
                "rawvideo",
                "-pacing_way",
                pacing_way,
                "-video_size",
                video_size,
                "-fps",
                fps,
                "-interlaced",
                interlaced,
                "-p_port",
                pci_addr,
                "-p_sip",
                local_iface_ip,
                "-p_tx_ip",
                mcast_ip,
                "-udp_port",
                udp_port,
                "-payload_type",
                payload_type,
                "-f",
                "mtl_st20p",
                "-",
            ]
        )

    return cmd


def print_configuration(label, value):
    print(f"{label:<15}{value}", flush=True)


def print_startup_configuration(direction, ffmpeg_bin, loglevel, mxl_domain, video_flow_ids, extra):
    print(
        f"Starting FFmpeg MXL <-> ST 2110 bridge ({direction})",
        flush=True,
    )
    print_configuration("FFmpeg:", ffmpeg_bin)
    print_configuration("Loglevel:", loglevel)
    print_configuration("MXL Domain:", mxl_domain)
    print_configuration("Video Flows:", video_flow_ids)

    for label, value in extra:
        if value:
            print_configuration(label, value)


def main():
    global ffmpeg_process

    if (len(sys.argv) == 1) and (sys.argv[2] in ("-h", "--help")):
        print(USAGE, end="")
        return 0

    ffmpeg_bin = env_or_default("FFMPEG_BIN", "/opt/bin/ffmpeg")

    if not os.path.isfile(ffmpeg_bin) or not os.access(ffmpeg_bin, os.X_OK):
        print(
            f"Error: ffmpeg not found or not executable: {ffmpeg_bin}",
            file=sys.stderr,
        )
        return 1

    direction = env_or_default("DIRECTION", "")

    if direction not in ("rx", "tx"):
        print(
            "Error: DIRECTION must be 'rx' (ST 2110 -> MXL) or "
            "'tx' (MXL -> ST 2110)",
            file=sys.stderr,
        )
        return 1

    mxl_domain = os.environ.get("MXL_DOMAIN")
    video_flow_ids = env_list("VIDEO_FLOW_IDs")
    local_iface_ip = os.environ.get("LOCAL_IFACE_IP")
    pci_addr = os.environ.get("PCI_ADDR")
    mcast_var = "RX_VIDEO_MCAST_IPs" if direction == "rx" else "TX_VIDEO_MCAST_IPs"
    video_mcast_ips = env_list(mcast_var)

    required = [
        ("MXL_DOMAIN", mxl_domain),
        ("VIDEO_FLOW_IDs", video_flow_ids),
        ("LOCAL_IFACE_IP", local_iface_ip),
        ("PCI_ADDR", pci_addr),
        (mcast_var, video_mcast_ips),
    ]

    missing = [name for name, value in required if not value]

    if missing:
        print(
            f"Error: Missing required environment variables: "
            f"{', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    if len(video_mcast_ips) != len(video_flow_ids):
        print(
            f"Error: {mcast_var} ({len(video_mcast_ips)} entries) and VIDEO_FLOW_IDs "
            f"({len(video_flow_ids)} entries) must have the same number of "
            f"entries",
            file=sys.stderr,
        )
        return 1

    udp_port = env_or_default("UDP_PORT", "20000")
    payload_type = env_or_default("PAYLOAD_TYPE", "96")
    fps = env_or_default("FPS", "29.97")
    video_size = env_or_default("VIDEO_SIZE", "1920x1080")
    pix_fmt = env_or_default("PIX_FMT", "yuv422p10le")
    interlaced = env_or_default("INTERLACED", "1")
    pacing_way = env_or_default("PACING_WAY", "tsc")
    ffmpeg_loglevel = env_or_default("FFMPEG_LOGLEVEL", "error")

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, handle_signal)

    if direction == "rx":
        deinterlace = env_flag_enabled("DEINTERLACE")
        mxl_video_codec = env_or_default("MXL_VIDEO_CODEC", "v210")

        cmd = build_rx_cmd(
            ffmpeg_bin,
            ffmpeg_loglevel,
            mxl_domain,
            video_flow_ids,
            local_iface_ip,
            pci_addr,
            video_mcast_ips,
            udp_port,
            payload_type,
            fps,
            video_size,
            pix_fmt,
            interlaced,
            pacing_way,
            deinterlace,
            mxl_video_codec,
        )

        extra = [
            ("PCI Addr:", pci_addr),
            ("Mcast IPs:", video_mcast_ips),
            ("Local IP:", local_iface_ip),
            ("Video Size:", video_size),
            ("FPS:", fps),
            ("Pix Fmt:", pix_fmt),
            ("MXL Codec:", mxl_video_codec),
            ("Deinterlace:", "enabled" if deinterlace else ""),
        ]
    else:
        blocking = env_or_default("BLOCKING", "-1")
        on_too_late = env_or_default("ON_TOO_LATE", "1")
        mxl_read_index_init = env_or_default("MXL_READ_INDEX_INIT", "head")
        diag_socket = env_or_default("DIAG_SOCKET", "")

        cmd = build_tx_cmd(
            ffmpeg_bin,
            ffmpeg_loglevel,
            mxl_domain,
            video_flow_ids,
            local_iface_ip,
            pci_addr,
            video_mcast_ips,
            udp_port,
            payload_type,
            fps,
            video_size,
            pix_fmt,
            interlaced,
            pacing_way,
            blocking,
            on_too_late,
            mxl_read_index_init,
            diag_socket,
        )

        extra = [
            ("PCI Addr:", pci_addr),
            ("Mcast IP:", video_mcast_ips),
            ("Local IP:", local_iface_ip),
            ("Video Size:", video_size),
            ("FPS:", fps),
            ("Pix Fmt:", pix_fmt),
            ("Diag Socket:", diag_socket),
        ]

    print_startup_configuration(
        direction,
        ffmpeg_bin,
        ffmpeg_loglevel,
        mxl_domain,
        video_flow_ids,
        extra,
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
