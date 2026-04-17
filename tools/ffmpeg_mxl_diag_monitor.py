#!/usr/bin/env python3

# This script connects to an FFmpeg/MXL diagnostic socket, displays a
# visualization of the audio and video MXL ring buffers, and computes
# median and P99, P99.5, and P99.9 estimates of the time between good
# video frames and audio sample buffer events based on timestamps in
# the diagnostic event stream.
#
# It also tracks OK to TOO_LATE intervals, reporting the time from the
# last successful read to the subsequent TOO_LATE event, along with the
# buffer margin at the preceding OK. Buffer margin is the distance from
# the ring buffer tail index to the read index.
#
# The quantile estimator is t-digest, and the preferred t-digest
# Python implementation is `tdigest-cffi`.
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
#
# To build a standalone executable, the _cffi_backend` module must be
# explicitly included using PyInstaller hidden imports:
#
# $ pyinstaller --onefile --hidden-import _cffi_backend ffmpeg_mxl_diag_monitor.py

import argparse
import curses
from collections import deque
import os
import select
import signal
import socket
import struct
import sys
import tempfile
import time

from tdigest import TDigest


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
VIDEO_READ_FMT = "<QQQQQI4s"
AUDIO_READ_FMT = "<QQQQQII"
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

# stats table widths
OK_STATS_LABEL_WIDTH = 8
TL_STATS_LABEL_WIDTH = 8
EX_STATS_LABEL_WIDTH = 8
STATS_TIME_WIDTH = 9
STATS_COUNT_WIDTH = 9
STATS_TOO_LATE_WIDTH = 9

# number of history events to render on the ring buffer visualization
READ_HISTORY_LEN = 60

# number of recent OK->TOO_LATE intervals to display on the TL lines
TOO_LATE_HISTORY_DISPLAY_LEN = 5

# exit signal flag
_running = True


class TDigestEstimator:
    def __init__(self):
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

    def p99_5_estimate(self):
        if self.digest.weight <= 0:
            return None
        return self.digest.percentile(99.5)

    def p99_9_estimate(self):
        if self.digest.weight <= 0:
            return None
        return self.digest.percentile(99.9)


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

    timestamp, exec_dur, tail_index, head_index, read_index, mxl_status, _reserved = \
        struct.unpack_from(VIDEO_READ_FMT, data, HEADER_SIZE)

    return {
        "timestamp": timestamp,
        "exec_dur": exec_dur,
        "tail_index": tail_index,
        "head_index": head_index,
        "read_index": read_index,
        "mxl_status": mxl_status,
    }


def parse_audio_read(data: bytes):
    need = HEADER_SIZE + AUDIO_READ_SIZE
    if len(data) < need:
        raise ValueError(f"short audio_read datagram: got {len(data)} bytes, need {need}")

    timestamp, exec_dur, tail_index, head_index, read_index, read_size, mxl_status = \
        struct.unpack_from(AUDIO_READ_FMT, data, HEADER_SIZE)

    return {
        "timestamp": timestamp,
        "exec_dur": exec_dur,
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


def ns_to_us(value_ns):
    if value_ns is None:
        return None
    return value_ns / 1_000.0

def format_ms(value_ms):
    if value_ms is None:
        return "-"
    return f"{value_ms:.1f}"


def format_us(value_us):
    if value_us is None:
        return "-"
    return f"{value_us:.1f}"


def format_margin(value):
    if value is None:
        return "-"
    return str(value)


def format_interval_margin(interval_ms, margin_units):
    return f"{format_ms(interval_ms)}|{format_margin(margin_units)}"


def format_host_status() -> str:
    hostname = socket.gethostname()
    now_text = time.strftime("%Y-%m-%d %H:%M:%S")
    load1m = os.getloadavg()[0]
    cores = os.cpu_count()
    load_pct = 100.0 * load1m / cores

    return (
        f"host: {hostname}   "
        f"local time: {now_text}   "
        f"load 1m: {load1m:.1f} "
        f"({load_pct:.1f}% of {cores} cores)"
    )


def make_timing_state():
    return {
        "prev_ok_timestamp": None,
        "ok_event_count": 0,
        "interval_count": 0,
        "interval_sum_ms": 0.0,
        "last_interval_ms": None,
        "max_interval_ms": None,
        "estimator": TDigestEstimator(),
    }


def make_too_late_timing_state():
    return {
        "pending_ok_timestamp": None,
        "pending_ok_margin": None,
        "interval_count": 0,
        "interval_sum_ms": 0.0,
        "recent_pairs": deque(maxlen=TOO_LATE_HISTORY_DISPLAY_LEN),
    }


def make_exec_state():
    return {
        "ok_count": 0,
        "sum_us": 0.0,
        "max_us": None,
    }


def make_stream_state():
    return {
        "have_data": False,
        "tail_index": 0,
        "head_index": 0,
        "read_index": 0,
        "mxl_status": 0,
        "too_late_count": 0,
        "timestamp": 0,
        "read_history": deque(maxlen=READ_HISTORY_LEN),
        "timing": make_timing_state(),
        "too_late_timing": make_too_late_timing_state(),
        "exec": make_exec_state(),
    }


def reset_monitor_state():
    start_monotonic = time.monotonic()
    video = make_stream_state()
    audio = make_stream_state()
    return start_monotonic, video, audio


def update_timing_state(timing: dict, timestamp_ns: int):
    timing["ok_event_count"] += 1

    prev_ok_timestamp = timing["prev_ok_timestamp"]

    if prev_ok_timestamp is None:
        timing["prev_ok_timestamp"] = timestamp_ns
        return

    if timestamp_ns < prev_ok_timestamp:
        return

    delta_ms = ns_to_ms(timestamp_ns - prev_ok_timestamp)
    timing["interval_count"] += 1
    timing["interval_sum_ms"] += delta_ms
    timing["last_interval_ms"] = delta_ms
    timing["estimator"].add(delta_ms)

    max_interval_ms = timing["max_interval_ms"]
    if max_interval_ms is None or delta_ms > max_interval_ms:
        timing["max_interval_ms"] = delta_ms

    timing["prev_ok_timestamp"] = timestamp_ns


def update_too_late_timing_on_ok(too_late_timing: dict, timestamp_ns: int,
                                 tail_index: int, read_index: int):
    too_late_timing["pending_ok_timestamp"] = timestamp_ns
    too_late_timing["pending_ok_margin"] = read_index - tail_index


def update_too_late_timing_on_too_late(too_late_timing: dict, timestamp_ns: int):
    pending_ok_timestamp = too_late_timing["pending_ok_timestamp"]
    pending_ok_margin = too_late_timing["pending_ok_margin"]

    if pending_ok_timestamp is None:
        return

    if timestamp_ns < pending_ok_timestamp:
        return

    delta_ms = ns_to_ms(timestamp_ns - pending_ok_timestamp)
    too_late_timing["interval_count"] += 1
    too_late_timing["interval_sum_ms"] += delta_ms
    too_late_timing["recent_pairs"].append((delta_ms, pending_ok_margin))

    # Consume this OK so only the first subsequent TOO_LATE is counted.
    too_late_timing["pending_ok_timestamp"] = None
    too_late_timing["pending_ok_margin"] = None


def update_exec_state(exec_state: dict, exec_dur_ns: int):
    exec_dur_us = ns_to_us(exec_dur_ns)

    exec_state["ok_count"] += 1
    exec_state["sum_us"] += exec_dur_us

    max_us = exec_state["max_us"]
    if max_us is None or exec_dur_us > max_us:
        exec_state["max_us"] = exec_dur_us


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
        update_too_late_timing_on_too_late(
            state["too_late_timing"],
            msg["timestamp"],
        )

    if msg["mxl_status"] == MXL_STATUS_OK:
        update_timing_state(state["timing"], msg["timestamp"])
        update_too_late_timing_on_ok(
            state["too_late_timing"],
            msg["timestamp"],
            msg["tail_index"],
            msg["read_index"],
        )
        update_exec_state(
            state["exec"],
            msg["exec_dur"],
        )


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


def render_stats_header() -> str:
    return (
        f"{'':<{OK_STATS_LABEL_WIDTH}}  "
        f"{'last':>{STATS_TIME_WIDTH}}  "
        f"{'mean':>{STATS_TIME_WIDTH}}  "
        f"{'med':>{STATS_TIME_WIDTH}}  "
        f"{'p99':>{STATS_TIME_WIDTH}}  "
        f"{'p99.5':>{STATS_TIME_WIDTH}}  "
        f"{'p99.9':>{STATS_TIME_WIDTH}}  "
        f"{'max':>{STATS_TIME_WIDTH}}  "
        f"{'n':>{STATS_COUNT_WIDTH}}"
    )


def render_stats_row(label: str, state: dict) -> str:
    timing = state["timing"]
    estimator = timing["estimator"]

    median_ms = estimator.median_estimate()
    p99_ms = estimator.p99_estimate()
    p99_5_ms = estimator.p99_5_estimate()
    p99_9_ms = estimator.p99_9_estimate()

    mean_ms = None
    if timing["interval_count"] > 0:
        mean_ms = timing["interval_sum_ms"] / timing["interval_count"]

    return (
        f"{label:<{OK_STATS_LABEL_WIDTH}}  "
        f"{format_ms(timing['last_interval_ms']):>{STATS_TIME_WIDTH}}  "
        f"{format_ms(mean_ms):>{STATS_TIME_WIDTH}}  "
        f"{format_ms(median_ms):>{STATS_TIME_WIDTH}}  "
        f"{format_ms(p99_ms):>{STATS_TIME_WIDTH}}  "
        f"{format_ms(p99_5_ms):>{STATS_TIME_WIDTH}}  "
        f"{format_ms(p99_9_ms):>{STATS_TIME_WIDTH}}  "
        f"{format_ms(timing['max_interval_ms']):>{STATS_TIME_WIDTH}}  "
        f"{timing['interval_count']:>{STATS_COUNT_WIDTH}}"
    )


def render_too_late_header() -> str:
    return (
        f"{'':<{TL_STATS_LABEL_WIDTH}}  "
        f"{'too_late':>{STATS_TOO_LATE_WIDTH}}  "
        f"{'mean':>{STATS_TIME_WIDTH}}  "
        f"last {TOO_LATE_HISTORY_DISPLAY_LEN} OK->TOO_LATE|margin"
    )


def render_too_late_row(label: str, state: dict) -> str:
    too_late_timing = state["too_late_timing"]

    mean_ms = None
    if too_late_timing["interval_count"] > 0:
        mean_ms = (
            too_late_timing["interval_sum_ms"] /
            too_late_timing["interval_count"]
        )

    recent_values = "  ".join(
        format_interval_margin(interval_ms, margin_units)
        for interval_ms, margin_units in too_late_timing["recent_pairs"]
    )

    if not recent_values:
        recent_values = "-"

    return (
        f"{label:<{TL_STATS_LABEL_WIDTH}}  "
        f"{state['too_late_count']:>{STATS_TOO_LATE_WIDTH}}  "
        f"{format_ms(mean_ms):>{STATS_TIME_WIDTH}}  "
        f"{recent_values}"
    )


def render_exec_header() -> str:
    return (
        f"{'':<{EX_STATS_LABEL_WIDTH}}  "
        f"{'mean_us':>{STATS_TIME_WIDTH}}  "
        f"{'max_us':>{STATS_TIME_WIDTH}}  "
    )


def render_exec_row(label: str, state: dict) -> str:
    exec_state = state["exec"]

    mean_us = None
    if exec_state["ok_count"] > 0:
        mean_us = exec_state["sum_us"] / exec_state["ok_count"]

    return (
        f"{label:<{EX_STATS_LABEL_WIDTH}}  "
        f"{format_us(mean_us):>{STATS_TIME_WIDTH}}  "
        f"{format_us(exec_state['max_us']):>{STATS_TIME_WIDTH}}  "
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
            paused: bool):
    stdscr.erase()
    rows, cols = stdscr.getmaxyx()

    elapsed_seconds = time.monotonic() - start_monotonic
    elapsed = format_elapsed(elapsed_seconds)
    elapsed_fps = compute_elapsed_fps(video, elapsed_seconds)
    host_status = format_host_status()
    paused_text = "   PAUSED" if paused else ""

    safe_addnstr(
        stdscr,
        0,
        0,
        (
            f"FFmpeg MXL diagnostic monitor"
            f"   elapsed: {elapsed}"
            f"   elapsed FPS: {elapsed_fps}"
            f"{paused_text}"
        ),
        cols - 1,
    )

    safe_addnstr(stdscr, 2, 0, render_stream_line("VIDEO", video, cols - 1), cols - 1)
    safe_addnstr(stdscr, 3, 0, render_stream_line("AUDIO", audio, cols - 1), cols - 1)

    safe_addnstr(stdscr, 5, 0, render_stats_header(), cols - 1)
    safe_addnstr(stdscr, 6, 0, render_stats_row("VIDEO OK", video), cols - 1)
    safe_addnstr(stdscr, 7, 0, render_stats_row("AUDIO OK", audio), cols - 1)

    safe_addnstr(stdscr, 9, 0, render_too_late_header(), cols - 1)
    safe_addnstr(stdscr, 10, 0, render_too_late_row("VIDEO TL", video), cols - 1)
    safe_addnstr(stdscr, 11, 0, render_too_late_row("AUDIO TL", audio), cols - 1)

    safe_addnstr(stdscr, 13, 0, render_exec_header(), cols - 1)
    safe_addnstr(stdscr, 14, 0, render_exec_row("VIDEO EX", video), cols - 1)
    safe_addnstr(stdscr, 15, 0, render_exec_row("AUDIO EX", audio), cols - 1)

    safe_addnstr(stdscr, rows - 3, 0, "q quit   p pause/resume UI   c clear/restart", cols - 1)
    safe_addnstr(stdscr, rows - 1, 0, host_status, cols - 1)
    stdscr.refresh()


def handle_socket_ready(sock: socket.socket, video: dict, audio: dict):
    for _ in range(8):  # small bounded drain
        try:
            data, _addr = sock.recvfrom(4096)
        except BlockingIOError:
            break
        except InterruptedError:
            return
        except OSError:
            return

        try:
            version, msg_type, size, _reserved = parse_header(data)

            if version != MXL_DIAG_VERSION:
                pass
            elif size < HEADER_SIZE:
                pass
            elif len(data) < size:
                pass
            elif msg_type == MXL_DIAG_MSG_VIDEO_READ:
                update_stream_state(video, parse_video_read(data))
            elif msg_type == MXL_DIAG_MSG_AUDIO_READ:
                update_stream_state(audio, parse_audio_read(data))
            else:
                pass

        except ValueError:
            pass
        except OSError:
            pass


def handle_stdin_ready(stdscr):
    try:
        return stdscr.getch()
    except curses.error:
        return -1


def handle_keypress(key: int,
                    paused: bool,
                    start_monotonic: float,
                    video: dict,
                    audio: dict):
    global _running

    redraw_now = False

    if key == -1:
        return paused, start_monotonic, video, audio, redraw_now

    if key in (ord("p"), ord("P")):
        paused = not paused
        redraw_now = True
        return paused, start_monotonic, video, audio, redraw_now

    if key in (ord("q"), ord("Q")):
        _running = False
        return paused, start_monotonic, video, audio, redraw_now

    if key in (ord("c"), ord("C")):
        start_monotonic, video, audio = reset_monitor_state()
        redraw_now = True
        return paused, start_monotonic, video, audio, redraw_now

    if paused:
        return paused, start_monotonic, video, audio, redraw_now

    return paused, start_monotonic, video, audio, redraw_now


def run_ui(stdscr,
           sock: socket.socket):
    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    stdscr.nodelay(True)

    start_monotonic, video, audio = reset_monitor_state()
    paused = False

    draw_ui(
        stdscr,
        start_monotonic,
        video,
        audio,
        paused,
    )

    sock_fd = sock.fileno()
    stdin_fd = sys.stdin.fileno()

    while _running:

        try:
            readable, _writable, _exceptional = select.select(
                [sock_fd, stdin_fd],
                [],
                [],
                None,
            )
        except InterruptedError:
            continue
        except OSError:
            if not _running:
                break
            continue

        if sock_fd in readable:
            handle_socket_ready(sock, video, audio)

        redraw_now = False

        if stdin_fd in readable:
            key = handle_stdin_ready(stdscr)
            paused, start_monotonic, video, audio, redraw_now = handle_keypress(
                key,
                paused,
                start_monotonic,
                video,
                audio,
            )

        if not _running:
            break

        if redraw_now or not paused:
            draw_ui(
                stdscr,
                start_monotonic,
                video,
                audio,
                paused,
            )


def main():
    parser = argparse.ArgumentParser(
        prog="ffmpeg_mxl_diag_monitor.py",
        description=(
            "Monitor an FFmpeg-MXL diagnostic datagram socket and display live VIDEO/AUDIO "
            "ring state plus timing statistics in a curses UI."
        ),
        epilog=(
            "Examples:\n"
            "  ffmpeg_mxl_diag_monitor.py /tmp/ffmpeg.diag.server.sock\n"
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

    args = parser.parse_args()

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
