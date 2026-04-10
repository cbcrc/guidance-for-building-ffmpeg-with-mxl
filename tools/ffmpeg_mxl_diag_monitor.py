#!/usr/bin/env python3

# This script connects to an FFmpeg/MXL diagnostic socket, displays a
# visualization of the audio and video MXL ring buffers, and computes
# a median and P99 quantile estimate of the time between good video
# frames and audio sample buffer events, based on timestamps in the
# diagnostic event stream.
#
# The preferred P99 quantile estimator is t-digest, and the preferred
# t-digest Python implementation is `tdigest-cffi`. If that is not
# available, the script falls back to a built-in P2 estimator.
#
# Install `tdigest-cffi` locally in a virtual environment:
#
#   python3 -m venv ~/venvs/ffmpeg-mxl-diag
#   . ~/venvs/ffmpeg-mxl-diag/bin/activate
#   python3 -m pip install --upgrade pip
#   python3 -m pip install tdigest-cffi
#
# Re-enter that environment later with:
#
#   . ~/venvs/ffmpeg-mxl-diag/bin/activate

import argparse
import curses
from collections import deque
import os
import signal
import socket
import struct
import tempfile
import time

# For P2Quantile
import bisect
import math
import random

try:
    from tdigest import TDigest
    HAVE_TDIGEST = True
except ImportError:
    TDigest = None
    HAVE_TDIGEST = False


# mxl_diag protocol
#
# See: https://github.com/cbcrc/FFmpeg/blob/dmf-mxl/master/libavformat/mxl_diag.h
#
# protocol version: 
MXL_DIAG_VERSION = 1
#
# protocol event types:
MXL_DIAG_MSG_CONNECT = 1
MXL_DIAG_MSG_RELEASE = 2
MXL_DIAG_MSG_VIDEO_READ = 3
MXL_DIAG_MSG_AUDIO_READ = 4
#
# encoded mxl status values:
MXL_STATUS_OK = 0
MXL_ERR_OUT_OF_RANGE_TOO_LATE = 3
#
# client side protocol encodings (see server side mxl_diag_msg):
HEADER_FMT = "<HHH10s"
VIDEO_READ_FMT = "<QQQQI4s"
AUDIO_READ_FMT = "<QQQQII"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
VIDEO_READ_SIZE = struct.calcsize(VIDEO_READ_FMT)
AUDIO_READ_SIZE = struct.calcsize(AUDIO_READ_FMT)


# mxlStatus enum names
#
# See: https://github.com/dmf-mxl/mxl/blob/release/v1.0/lib/include/mxl/mxl.h
#
MXL_STATUS_NAMES = {
    0: "OK",
    1: "UNKNOWN",
    2: "FLOW_NOT_FOUND",
    3: "TOO_LATE",
    4: "TOO_EARLY",
    5: "INVALID_READER",
    6: "INVALID_WRITER",
    7: "TIMEOUT",
    8: "INVALID_ARG",
    9: "CONFLICT",
    10: "PERMISSION_DENIED",
    11: "FLOW_INVALID",
}

# display widths
OK_WIDTH = 2
ERROR_WIDTH = max(
    len(name) for value, name in MXL_STATUS_NAMES.items()
    if value != MXL_STATUS_OK
)
DEPTH_WIDTH = 5

# number of history events to render on the ring buffer visualization
READ_HISTORY_LEN = 60

# exit signal flag
_running = True

# Fallback built-in quantile estimator when TDigest (preferred) is not available.
class P2Quantile:
    """
    Streaming P2 quantile estimator for a single quantile.
    """

    def __init__(self, p: float):
        if not 0.0 < p < 1.0:
            raise ValueError("p must be between 0 and 1")

        self.p = p
        self.count = 0
        self.initial = []
        self.q = None
        self.n = None
        self.np = None
        self.dn = None

    def add(self, x: float):
        x = float(x)
        self.count += 1

        if self.count <= 5:
            bisect.insort(self.initial, x)
            if self.count == 5:
                p = self.p
                self.q = self.initial[:]
                self.n = [1, 2, 3, 4, 5]
                self.np = [1.0, 1.0 + 2.0 * p, 1.0 + 4.0 * p, 3.0 + 2.0 * p, 5.0]
                self.dn = [0.0, p / 2.0, p, (1.0 + p) / 2.0, 1.0]
            return

        if x < self.q[0]:
            self.q[0] = x
            k = 0
        elif x < self.q[1]:
            k = 0
        elif x < self.q[2]:
            k = 1
        elif x < self.q[3]:
            k = 2
        elif x <= self.q[4]:
            k = 3
        else:
            self.q[4] = x
            k = 3

        for i in range(k + 1, 5):
            self.n[i] += 1

        for i in range(5):
            self.np[i] += self.dn[i]

        for i in range(1, 4):
            d = self.np[i] - self.n[i]
            if (d >= 1.0 and self.n[i + 1] - self.n[i] > 1) or \
               (d <= -1.0 and self.n[i - 1] - self.n[i] < -1):
                di = 1 if d > 0.0 else -1
                q_new = self._parabolic(i, di)
                if self.q[i - 1] < q_new < self.q[i + 1]:
                    self.q[i] = q_new
                else:
                    self.q[i] = self._linear(i, di)
                self.n[i] += di

    def estimate(self):
        if self.q is None:
            return None
        return self.q[2]

    def _parabolic(self, i: int, di: int) -> float:
        return self.q[i] + (
            di / (self.n[i + 1] - self.n[i - 1])
        ) * (
            (self.n[i] - self.n[i - 1] + di) *
            (self.q[i + 1] - self.q[i]) / (self.n[i + 1] - self.n[i]) +
            (self.n[i + 1] - self.n[i] - di) *
            (self.q[i] - self.q[i - 1]) / (self.n[i] - self.n[i - 1])
        )

    def _linear(self, i: int, di: int) -> float:
        return self.q[i] + di * (
            self.q[i + di] - self.q[i]
        ) / (self.n[i + di] - self.n[i])


class P2Estimator:
    name = "P2"

    def __init__(self):
        self.median = P2Quantile(0.5)
        self.p99 = P2Quantile(0.99)

    def add(self, value: float):
        self.median.add(value)
        self.p99.add(value)

    def median_estimate(self):
        return self.median.estimate()

    def p99_estimate(self):
        return self.p99.estimate()


# T-digest estimator using tdigest-cffi (preferred)
class TDigestEstimator:
    name = "TDIGEST"

    def __init__(self):
        if TDigest is None:
            raise RuntimeError("tdigest-cffi is not available")
        self.digest = TDigest()

    def add(self, value: float):
        self.digest.insert(float(value))

    def median_estimate(self):
        if self.digest.weight <= 0:
            return None
        return self.digest.percentile(50)

    def p99_estimate(self):
        if self.digest.weight <= 0:
            return None
        return self.digest.percentile(99)


def resolve_estimator_backend(mode: str):
    if mode == "p2":
        return P2Estimator

    if mode == "tdigest":
        if not HAVE_TDIGEST:
            raise RuntimeError(
                "tdigest-cffi is not available; install it or use --estimator p2"
            )
        return TDigestEstimator

    if mode == "auto":
        if HAVE_TDIGEST:
            return TDigestEstimator
        return P2Estimator

    raise RuntimeError(f"unknown estimator mode: {mode}")


def on_signal(signum, frame):
    del signum, frame
    global _running
    _running = False


def build_header_only_message(msg_type: int) -> bytes:
    return struct.pack(
        HEADER_FMT,
        MXL_DIAG_VERSION,
        msg_type,
        HEADER_SIZE,
        b"\x00" * 10,
    )


def parse_header(data: bytes):
    if len(data) < HEADER_SIZE:
        raise ValueError(f"short datagram: got {len(data)} bytes")
    return struct.unpack_from(HEADER_FMT, data, 0)


def parse_video_read(data: bytes):
    need = HEADER_SIZE + VIDEO_READ_SIZE
    if len(data) < need:
        raise ValueError(f"short video_read datagram: got {len(data)} bytes, need {need}")

    timestamp, tail_index, head_index, read_index, mxl_status, _reserved = \
        struct.unpack_from(VIDEO_READ_FMT, data, HEADER_SIZE)

    return {
        "timestamp": timestamp,
        "tail_index": tail_index,
        "head_index": head_index,
        "read_index": read_index,
        "mxl_status": mxl_status,
    }


def parse_audio_read(data: bytes):
    need = HEADER_SIZE + AUDIO_READ_SIZE
    if len(data) < need:
        raise ValueError(f"short audio_read datagram: got {len(data)} bytes, need {need}")

    timestamp, tail_index, head_index, read_index, read_size, mxl_status = \
        struct.unpack_from(AUDIO_READ_FMT, data, HEADER_SIZE)

    return {
        "timestamp": timestamp,
        "tail_index": tail_index,
        "head_index": head_index,
        "read_index": read_index,
        "read_size": read_size,
        "mxl_status": mxl_status,
    }


def status_to_string(status: int) -> str:
    return MXL_STATUS_NAMES.get(status, f"STATUS({status})")


def default_client_path() -> str:
    return os.path.join(tempfile.gettempdir(), f"ffmpeg.diag.client.{os.getpid()}.sock")


def send_release(sock: socket.socket, server_socket: str):
    try:
        sock.sendto(build_header_only_message(MXL_DIAG_MSG_RELEASE), server_socket)
    except OSError:
        pass


def ns_to_ms(value_ns):
    if value_ns is None:
        return None
    return value_ns / 1_000_000.0


def format_ms(value_ns):
    value_ms = ns_to_ms(value_ns)
    if value_ms is None:
        return "-"
    return f"{value_ms:.2f}"


def make_timing_state(estimator_cls):
    return {
        "prev_ok_timestamp": None,
        "ok_event_count": 0,
        "interval_count": 0,
        "last_interval_ns": None,
        "max_interval_ns": None,
        "estimator": estimator_cls(),
    }


def make_stream_state(estimator_cls):
    return {
        "have_data": False,
        "tail_index": 0,
        "head_index": 0,
        "read_index": 0,
        "mxl_status": 0,
        "too_late_count": 0,
        "timestamp": 0,
        "read_history": deque(maxlen=READ_HISTORY_LEN),
        "timing": make_timing_state(estimator_cls),
    }


def update_timing_state(timing: dict, timestamp_ns: int):
    timing["ok_event_count"] += 1

    prev_ok_timestamp = timing["prev_ok_timestamp"]

    if prev_ok_timestamp is None:
        timing["prev_ok_timestamp"] = timestamp_ns
        return

    if timestamp_ns < prev_ok_timestamp:
        return

    delta_ns = timestamp_ns - prev_ok_timestamp
    timing["interval_count"] += 1
    timing["last_interval_ns"] = delta_ns
    timing["estimator"].add(delta_ns)

    max_interval_ns = timing["max_interval_ns"]
    if max_interval_ns is None or delta_ns > max_interval_ns:
        timing["max_interval_ns"] = delta_ns

    timing["prev_ok_timestamp"] = timestamp_ns


def update_stream_state(state: dict, msg: dict):
    if state["have_data"]:
        state["read_history"].append((
            state["tail_index"],
            state["head_index"],
            state["read_index"],
        ))

    state["have_data"] = True
    state["tail_index"] = msg["tail_index"]
    state["head_index"] = msg["head_index"]
    state["read_index"] = msg["read_index"]
    state["mxl_status"] = msg["mxl_status"]
    state["timestamp"] = msg["timestamp"]

    if msg["mxl_status"] == MXL_ERR_OUT_OF_RANGE_TOO_LATE:
        state["too_late_count"] += 1

    if msg["mxl_status"] == MXL_STATUS_OK:
        update_timing_state(state["timing"], msg["timestamp"])


def map_read_position(inner: int, tail: int, head: int, read: int):
    if head < tail:
        return ("inside", 0)

    if read < tail:
        return ("left", None)

    if read > head:
        return ("right", None)

    count = head - tail + 1
    offset = read - tail

    mapped = (offset * inner) // count
    mapped = max(0, min(inner - 1, mapped))
    return ("inside", mapped)


def render_bar(width: int, tail: int, head: int, read: int, read_history,
               show_half_marker: bool = False) -> str:
    if width < 6:
        return " " * width

    inner = width - 4
    if inner < 1:
        inner = 1

    chars = ["-"] * inner
    left = " "
    right = " "

    if show_half_marker:
        chars[(inner - 1) // 2] = "|"

    for old_tail, old_head, old_read in read_history:
        where, mapped = map_read_position(inner, old_tail, old_head, old_read)

        if where == "inside":
            chars[mapped] = "r"
        elif where == "left":
            left = "r"
        elif where == "right":
            right = "r"

    where, mapped = map_read_position(inner, tail, head, read)

    if where == "inside":
        chars[mapped] = "R"
    elif where == "left":
        left = "R"
    elif where == "right":
        right = "R"

    return left + "|" + "".join(chars) + "|" + right


def render_stream_line(label: str, state: dict, total_width: int) -> str:
    if not state["have_data"]:
        return f"{label:<5} {'-':>{DEPTH_WIDTH}} (no data)"

    depth = state["head_index"] - state["tail_index"] + 1
    if depth < 0:
        depth = 0

    status = status_to_string(state["mxl_status"])
    if state["mxl_status"] == MXL_STATUS_OK:
        ok_field = "OK"
        error_field = ""
    else:
        ok_field = ""
        error_field = status

    prefix = f"{label:<5} {depth:>{DEPTH_WIDTH}} "
    suffix = f"  {ok_field:<{OK_WIDTH}}  {error_field:<{ERROR_WIDTH}}"

    bar_width = total_width - len(prefix) - len(suffix)
    if bar_width < 8:
        bar_width = 8

    bar = render_bar(
        bar_width,
        state["tail_index"],
        state["head_index"],
        state["read_index"],
        state["read_history"],
        show_half_marker=(label == "AUDIO"),
    )

    return prefix + bar + suffix


def render_stats_line(label: str, state: dict) -> str:
    timing = state["timing"]
    estimator = timing["estimator"]

    median_ns = estimator.median_estimate()
    p99_ns = estimator.p99_estimate()

    return (
        f"{label:<5} "
        f"last {format_ms(timing['last_interval_ns']):>9}  "
        f"med {format_ms(median_ns):>9}  "
        f"p99 {format_ms(p99_ns):>9}  "
        f"max {format_ms(timing['max_interval_ns']):>9}  "
        f"n {timing['interval_count']:>8}  "
        f"too_late {state['too_late_count']:>8}"
    )


def safe_addnstr(stdscr, y: int, x: int, text: str, maxcols: int):
    rows, cols = stdscr.getmaxyx()
    if y < 0 or y >= rows or x >= cols or maxcols <= 0:
        return
    stdscr.addnstr(y, x, text, min(maxcols, cols - x))


def format_elapsed(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"


def compute_elapsed_fps(video: dict, elapsed_seconds: float):
    ok_event_count = video["timing"]["ok_event_count"]
    if elapsed_seconds <= 0.0 or ok_event_count <= 0:
        return "-"
    return f"{ok_event_count / elapsed_seconds:.2f}"


def draw_ui(stdscr,
            start_monotonic: float,
            video: dict,
            audio: dict,
            estimator_name: str,
            last_error: str):
    stdscr.erase()
    rows, cols = stdscr.getmaxyx()

    elapsed_seconds = time.monotonic() - start_monotonic
    elapsed = format_elapsed(elapsed_seconds)
    elapsed_fps = compute_elapsed_fps(video, elapsed_seconds)

    safe_addnstr(
        stdscr,
        0,
        0,
        (
            f"FFmpeg MXL diagnostic monitor   estimator: {estimator_name}"
            f"   elapsed: {elapsed}"
            f"   elapsed FPS: {elapsed_fps}"
        ),
        cols - 1,
    )

    safe_addnstr(stdscr, 2, 0, render_stream_line("VIDEO", video, cols - 1), cols - 1)
    safe_addnstr(stdscr, 3, 0, render_stream_line("AUDIO", audio, cols - 1), cols - 1)

    safe_addnstr(stdscr, 5, 0, render_stats_line("VIDEO", video), cols - 1)
    safe_addnstr(stdscr, 6, 0, render_stats_line("AUDIO", audio), cols - 1)

    if last_error:
        safe_addnstr(stdscr, 8, 0, f"warning: {last_error}", cols - 1)

    safe_addnstr(stdscr, rows - 1, 0, "Ctrl-C to quit", cols - 1)
    stdscr.refresh()


def run_ui(stdscr,
           sock: socket.socket,
           estimator_cls,
           estimator_name: str):
    curses.curs_set(0)

    start_monotonic = time.monotonic()
    video = make_stream_state(estimator_cls)
    audio = make_stream_state(estimator_cls)
    last_error = ""

    draw_ui(
        stdscr,
        start_monotonic,
        video,
        audio,
        estimator_name,
        last_error,
    )

    while _running:
        try:
            data, _addr = sock.recvfrom(4096)
        except InterruptedError:
            continue
        except OSError as e:
            if not _running:
                break
            last_error = str(e)
            draw_ui(
                stdscr,
                start_monotonic,
                video,
                audio,
                estimator_name,
                last_error,
            )
            continue

        try:
            version, msg_type, size, _reserved = parse_header(data)

            if version != MXL_DIAG_VERSION:
                last_error = f"unexpected version {version}"
            elif size < HEADER_SIZE:
                last_error = f"bad size {size}"
            elif len(data) < size:
                last_error = f"short datagram payload: got {len(data)} bytes, need {size}"
            elif msg_type == MXL_DIAG_MSG_VIDEO_READ:
                update_stream_state(video, parse_video_read(data))
                last_error = ""
            elif msg_type == MXL_DIAG_MSG_AUDIO_READ:
                update_stream_state(audio, parse_audio_read(data))
                last_error = ""
            else:
                last_error = f"ignored msg type {msg_type}"

        except ValueError as e:
            last_error = str(e)
        except OSError as e:
            last_error = str(e)

        draw_ui(
            stdscr,
            start_monotonic,
            video,
            audio,
            estimator_name,
            last_error,
        )


def main():
    parser = argparse.ArgumentParser(
        prog="ffmpeg_mxl_diag_monitor.py",
        description=(
            "Monitor an FFmpeg-MXL diagnostic datagram socket and display live VIDEO/AUDIO "
            "ring state plus timing statistics in a curses UI."
        ),
        epilog=(
            "Estimator modes:\n"
            "  auto     Prefer tdigest-cffi when available, otherwise fall back to P2.\n"
            "  tdigest  Require tdigest-cffi. Exit with an error if it is not installed.\n"
            "  p2       Always use the built-in P2 quantile estimator.\n"
            "\n"
            "Examples:\n"
            "  ffmpeg_mxl_diag_monitor.py /tmp/ffmpeg.diag.server.sock\n"
            "  ffmpeg_mxl_diag_monitor.py --estimator auto /tmp/ffmpeg.diag.server.sock\n"
            "  ffmpeg_mxl_diag_monitor.py --estimator tdigest /tmp/ffmpeg.diag.server.sock\n"
            "  ffmpeg_mxl_diag_monitor.py --estimator p2 /tmp/ffmpeg.diag.server.sock\n"
            "  ffmpeg_mxl_diag_monitor.py --client-socket /tmp/ffmpeg.diag.client.sock "
            "/tmp/ffmpeg.diag.server.sock"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    
    parser.add_argument(
        "server_socket",
        metavar="SERVER_SOCKET",
        help=(
            "Path to the FFmpeg-MXL diagnostic server socket "
            "(for example /tmp/ffmpeg.diag.server.sock)"
        ),
    )

    parser.add_argument(
        "--client-socket",
        metavar="PATH",
        default=default_client_path(),
        help=(
            "Path to the client UNIX datagram socket created by this program. "
            "If the path already exists it will be removed before binding. "
            f"Default: {default_client_path()}"
        ),
    )
    
    parser.add_argument(
        "--estimator",
        metavar="MODE",
        choices=("auto", "tdigest", "p2"),
        default="auto",
        help=(
            "Quantile estimator backend to use. "
            "'auto' prefers tdigest-cffi and falls back to P2; "
            "'tdigest' requires tdigest-cffi; "
            "'p2' forces the built-in P2 estimator. "
            "Default: %(default)s"
        ),
    )
    
    args = parser.parse_args()

    try:
        estimator_cls = resolve_estimator_backend(args.estimator)
    except RuntimeError as e:
        parser.error(str(e))

    estimator_name = estimator_cls.name

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    signal.siginterrupt(signal.SIGINT, True)
    signal.siginterrupt(signal.SIGTERM, True)

    if os.path.exists(args.client_socket):
        os.unlink(args.client_socket)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        sock.bind(args.client_socket)
        sock.setblocking(True)
        sock.sendto(build_header_only_message(MXL_DIAG_MSG_CONNECT), args.server_socket)

        curses.wrapper(
            run_ui,
            sock,
            estimator_cls,
            estimator_name,
        )

    finally:
        send_release(sock, args.server_socket)
        sock.close()
        try:
            os.unlink(args.client_socket)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
