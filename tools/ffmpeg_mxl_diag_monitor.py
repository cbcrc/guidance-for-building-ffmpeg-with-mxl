#!/usr/bin/env python3

# This script connects to an FFmpeg/MXL diagnostic socket, displays a
# visualization of the audio and video MXL ring buffers, and computes
# median and P99, P99.5, and P99.9 estimates of the time between good
# video frames and audio sample buffer events based on timestamps in
# the diagnostic event stream.
#
# It also tracks read safety margins, reporting low-tail statistics that
# characterize how close reads get to the TOO_LATE threshold under load.
# Safety status is based on the P0.01 low-tail margin, with FAIL still
# based on any observed negative minimum margin.
# Video safety margin is the distance from tail to read_index. Audio safety
# margin is the distance from tail to the start of the audio read region,
# minus half of the current ring depth.
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
# $ pyinstaller --onedir --hidden-import _cffi_backend ffmpeg_mxl_diag_monitor.py

import argparse
import curses
from collections import deque
import os
import select
import signal
import socket
import struct
import subprocess
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
MXL_ERR_OUT_OF_RANGE_TOO_EARLY = 4
#
# client side protocol encodings (see server side mxl_diag_msg):
HEADER_FMT = "<HHH10s"
VIDEO_READ_FMT = "<QQQQQI4s"
AUDIO_READ_FMT = "<QQQQQII"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
VIDEO_READ_SIZE = struct.calcsize(VIDEO_READ_FMT)
AUDIO_READ_SIZE = struct.calcsize(AUDIO_READ_FMT)

# host / ffmpeg status sampling interval
STATUS_SAMPLE_INTERVAL_SECONDS = 1.0


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
SAFETY_STATS_LABEL_WIDTH = 10
SAFETY_STATUS_WIDTH = 8
EX_STATS_LABEL_WIDTH = 8
STATS_TIME_WIDTH = 9
STATS_COUNT_WIDTH = 9
STATS_TOO_LATE_WIDTH = 9

# number of history events to render on the ring buffer visualization
READ_HISTORY_LEN = 30

# number of recent OK->TOO_LATE intervals to display on the TL lines
TOO_LATE_HISTORY_DISPLAY_LEN = 5

# timeline marker characters
TIMELINE_CHAR = "-"
CURRENT_REGION_CHAR = "="
HISTORY_MARK_CHAR = ":"
AUDIO_MIN_SAFETY_MARK_CHAR = "^"

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

    def p1_estimate(self):
        if self.digest.weight <= 0:
            return None
        return self.digest.percentile(1)

    def p0_5_estimate(self):
        if self.digest.weight <= 0:
            return None
        return self.digest.percentile(0.5)

    def p0_1_estimate(self):
        if self.digest.weight <= 0:
            return None
        return self.digest.percentile(0.1)

    def p0_05_estimate(self):
        if self.digest.weight <= 0:
            return None
        return self.digest.percentile(0.05)

    def p0_01_estimate(self):
        if self.digest.weight <= 0:
            return None
        return self.digest.percentile(0.01)


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


def format_safety_margin(value):
    if value is None:
        return "-"
    return f"{value:.1f}"


def format_interval_margins(interval_ms, ok_margin_units, tl_margin_units):
    return (
        f"{format_ms(interval_ms)}"
        f"|{format_margin(ok_margin_units)}"
        f"|{format_margin(tl_margin_units)}"
    )


def normalize_sched_class(cls: str) -> str:
    if cls == "TS":
        return "NORMAL"
    return cls


def resolve_pid_from_server_socket(server_socket: str) -> int:
    try:
        result = subprocess.run(
            ["ss", "-xlpn"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RuntimeError(f"failed to run ss: {exc}") from exc

    pid_matches = []

    for line in result.stdout.splitlines():
        if server_socket not in line:
            continue

        pid_marker = "pid="
        start = line.find(pid_marker)
        if start < 0:
            continue

        start += len(pid_marker)
        end = start
        while end < len(line) and line[end].isdigit():
            end += 1

        pid_text = line[start:end]
        if not pid_text:
            continue

        try:
            pid_matches.append(int(pid_text))
        except ValueError:
            continue

    if not pid_matches:
        raise RuntimeError(
            f"could not resolve PID from server socket path using ss: {server_socket}"
        )

    return pid_matches[0]

def resolve_pid_from_cmdline_socket_path(server_socket: str):
    needle = server_socket.encode()
    self_pid = os.getpid()

    for proc_name in os.listdir("/proc"):
        if not proc_name.isdigit():
            continue

        try:
            pid = int(proc_name)
        except ValueError:
            continue

        if pid == self_pid:
            continue

        cmdline_path = os.path.join("/proc", proc_name, "cmdline")

        try:
            with open(cmdline_path, "rb") as f:
                cmdline = f.read()
        except OSError:
            continue

        if needle not in cmdline:
            continue

        argv = [arg for arg in cmdline.split(b"\x00") if arg]

        has_ffmpeg = any(
            os.path.basename(arg.decode(errors="ignore")) == "ffmpeg"
            for arg in argv
        )

        if not has_ffmpeg:
            continue

        return pid

    return None

def read_ffmpeg_sched_info(pid: int) -> dict:
    try:
        result = subprocess.run(
            ["ps", "-o", "cls=,rtprio=,ni=", "-p", str(pid)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.SubprocessError, OSError):
        return {
            "pid": pid,
            "sched_text": "unknown",
        }

    output = result.stdout.strip()
    if not output:
        return {
            "pid": pid,
            "sched_text": "unknown",
        }

    parts = output.split()
    if len(parts) != 3:
        return {
            "pid": pid,
            "sched_text": "unknown",
        }

    cls, rtprio, nice = parts
    cls = normalize_sched_class(cls)

    if cls == "NORMAL":
        priority = nice
    else:
        priority = rtprio

    return {
        "pid": pid,
        "sched_text": f"{cls}/{priority}",
    }


def read_proc_stat_cpu_ticks(pid: int):
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="ascii") as f:
            stat = f.read()
    except OSError:
        return None

    try:
        close_paren = stat.rfind(")")
        fields = stat[close_paren + 2:].split()

        # After removing "pid (comm) ", fields[0] is proc stat field 3.
        # utime is field 14, stime is field 15.
        utime = int(fields[11])
        stime = int(fields[12])
    except (IndexError, ValueError):
        return None

    return utime + stime


def sample_ffmpeg_cpu(pid: int, cpu_sample_state: dict):
    now_monotonic = time.monotonic()
    cpu_ticks = read_proc_stat_cpu_ticks(pid)

    if cpu_ticks is None:
        cpu_sample_state.clear()
        return None

    previous_ticks = cpu_sample_state.get("cpu_ticks")
    previous_monotonic = cpu_sample_state.get("monotonic")

    cpu_sample_state["cpu_ticks"] = cpu_ticks
    cpu_sample_state["monotonic"] = now_monotonic

    if previous_ticks is None or previous_monotonic is None:
        return None

    elapsed_seconds = now_monotonic - previous_monotonic
    if elapsed_seconds <= 0.0:
        return None

    ticks_per_second = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
    cpu_seconds = (cpu_ticks - previous_ticks) / ticks_per_second

    return 100.0 * cpu_seconds / elapsed_seconds


def format_ffmpeg_status(ffmpeg_status: dict) -> str:
    cpu_pct = ffmpeg_status["cpu_pct"]

    if cpu_pct is None:
        cpu_text = "-"
    else:
        cpu_text = f"{cpu_pct:.1f}%"

    return (
        f"ffmpeg pid: {ffmpeg_status['pid']}   "
        f"scheduling: {ffmpeg_status['sched_text']}   "
        f"cpu: {cpu_text}"
    )

def format_host_status(host_status: dict) -> str:
    return (
        f"host: {host_status['hostname']}   "
        f"local time: {host_status['now_text']}   "
        f"load 1m: {host_status['load1m']:.1f} "
        f"({host_status['load_pct']:.1f}% of {host_status['cores']} cores)"
    )


def make_host_status() -> dict:
    hostname = socket.gethostname()
    timestamp_struct = time.localtime()
    now_text = time.strftime("%Y-%m-%d %H:%M:%S", timestamp_struct)
    load1m = os.getloadavg()[0]
    cores = os.cpu_count()
    load_pct = 100.0 * load1m / cores

    return {
        "hostname": hostname,
        "timestamp_struct": timestamp_struct,
        "now_text": now_text,
        "load1m": load1m,
        "cores": cores,
        "load_pct": load_pct,
    }


def make_ffmpeg_status(server_socket: str) -> dict:
    pid = None

    try:
        pid = resolve_pid_from_server_socket(server_socket)
    except RuntimeError:
        pass

    if pid is None:
        pid = resolve_pid_from_cmdline_socket_path(server_socket)

    if pid is None:
        return {
            "pid": "unknown",
            "sched_text": "unknown",
            "cpu_pct": None,
            "cpu_sample_state": {},
        }

    sched_info = read_ffmpeg_sched_info(pid)

    return {
        "pid": sched_info["pid"],
        "sched_text": sched_info["sched_text"],
        "cpu_pct": None,
        "cpu_sample_state": {},
    }


def update_dynamic_statuses(host_status: dict,
                            ffmpeg_status: dict):
    fresh_host_status = make_host_status()
    host_status.clear()
    host_status.update(fresh_host_status)

    if isinstance(ffmpeg_status["pid"], int):
        ffmpeg_status["cpu_pct"] = sample_ffmpeg_cpu(
            ffmpeg_status["pid"],
            ffmpeg_status["cpu_sample_state"],
        )
    else:
        ffmpeg_status["cpu_pct"] = None


def maybe_update_dynamic_statuses(host_status: dict,
                                  ffmpeg_status: dict,
                                  status_state: dict,
                                  paused: bool,
                                  now_monotonic: float):
    if paused:
        return

    last_sample_monotonic = status_state["last_sample_monotonic"]
    if last_sample_monotonic is not None:
        if (now_monotonic - last_sample_monotonic) < STATUS_SAMPLE_INTERVAL_SECONDS:
            return

    update_dynamic_statuses(host_status, ffmpeg_status)
    status_state["last_sample_monotonic"] = now_monotonic


def make_timing_state():
    return {
        "prev_ok_timestamp": None,
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


def make_safety_margin_state():
    return {
        "count": 0,
        "sum": 0.0,
        "last": None,
        "min": None,
        "read_unit_size": None,
        "estimator": TDigestEstimator(),
    }


def make_stream_state():
    return {
        "have_data": False,
        "tail_index": 0,
        "head_index": 0,
        "read_index": 0,
        "read_start_index": 0,
        "read_end_index": 0,
        "mxl_status": 0,
        "too_late_count": 0,
        "timestamp": 0,
        "ok_video_frame_count": 0,
        "ok_audio_sample_count": 0,
        "read_history": deque(maxlen=READ_HISTORY_LEN),
        "timing": make_timing_state(),
        "too_late_timing": make_too_late_timing_state(),
        "exec": make_exec_state(),
        "safety_margin": make_safety_margin_state(),
    }


def reset_monitor_state():
    start_monotonic = time.monotonic()
    video = make_stream_state()
    audio = make_stream_state()
    return start_monotonic, video, audio


def update_timing_state(timing: dict, timestamp_ns: int):
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


def compute_tl_margin_units(msg: dict) -> int:
    if "read_size" in msg:
        return msg["read_index"] - msg["read_size"] + 1 - msg["tail_index"]

    return msg["read_index"] - msg["tail_index"]


def compute_read_safety_margin(msg: dict) -> float:
    if "read_size" in msg:
        ring_depth = msg["head_index"] - msg["tail_index"] + 1
        audio_read_margin = (
            msg["read_index"] - msg["read_size"] + 1 - msg["tail_index"]
        )
        return audio_read_margin - (ring_depth / 2.0)

    video_read_margin = msg["read_index"] - msg["tail_index"]
    return float(video_read_margin)


def compute_read_unit_size(msg: dict) -> float:
    if "read_size" in msg:
        return float(msg["read_size"])

    return 1.0


def update_safety_margin_state(safety_margin_state: dict,
                               margin: float,
                               read_unit_size: float):
    safety_margin_state["count"] += 1
    safety_margin_state["sum"] += margin
    safety_margin_state["last"] = margin
    safety_margin_state["read_unit_size"] = read_unit_size
    safety_margin_state["estimator"].add(margin)

    min_margin = safety_margin_state["min"]
    if min_margin is None or margin < min_margin:
        safety_margin_state["min"] = margin


def update_too_late_timing_on_ok(too_late_timing: dict, timestamp_ns: int,
                                 margin_units: int):
    too_late_timing["pending_ok_timestamp"] = timestamp_ns
    too_late_timing["pending_ok_margin"] = margin_units


def update_too_late_timing_on_too_late(too_late_timing: dict,
                                       timestamp_ns: int,
                                       margin_units: int):
    pending_ok_timestamp = too_late_timing["pending_ok_timestamp"]
    pending_ok_margin = too_late_timing["pending_ok_margin"]

    if pending_ok_timestamp is None:
        return

    if timestamp_ns < pending_ok_timestamp:
        return

    delta_ms = ns_to_ms(timestamp_ns - pending_ok_timestamp)
    too_late_margin = margin_units

    too_late_timing["interval_count"] += 1
    too_late_timing["interval_sum_ms"] += delta_ms
    too_late_timing["recent_pairs"].append(
        (delta_ms, pending_ok_margin, too_late_margin)
    )

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

    # [start,end) half-open interval
    if "read_size" in msg:
        state["read_start_index"] = msg["read_index"] - msg["read_size"] + 1
        state["read_end_index"] = msg["read_index"] + 1
    else:
        state["read_start_index"] = msg["read_index"]
        state["read_end_index"] = msg["read_index"] + 1

    state["mxl_status"] = msg["mxl_status"]
    state["timestamp"] = msg["timestamp"]

    tl_margin_units = compute_tl_margin_units(msg)
    if msg["mxl_status"] != MXL_ERR_OUT_OF_RANGE_TOO_EARLY:
        read_safety_margin = compute_read_safety_margin(msg)
        read_unit_size = compute_read_unit_size(msg)
        update_safety_margin_state(
            state["safety_margin"],
            read_safety_margin,
            read_unit_size,
        )

    if msg["mxl_status"] == MXL_ERR_OUT_OF_RANGE_TOO_LATE:
        state["too_late_count"] += 1
        update_too_late_timing_on_too_late(
            state["too_late_timing"],
            msg["timestamp"],
            tl_margin_units,
        )

    if msg["mxl_status"] == MXL_STATUS_OK:
        if "read_size" in msg:
            state["ok_audio_sample_count"] += msg["read_size"]
        else:
            state["ok_video_frame_count"] += 1

        update_timing_state(state["timing"], msg["timestamp"])
        update_too_late_timing_on_ok(
            state["too_late_timing"],
            msg["timestamp"],
            tl_margin_units,
        )
        update_exec_state(
            state["exec"],
            msg["exec_dur"],
        )


def map_index_position(inner: int, tail: int, head: int, index: int):
    if head < tail:
        return ("inside", 0)

    if index < tail:
        return ("left", None)

    if index > head:
        return ("right", None)

    count = head - tail + 1
    offset = index - tail

    mapped = (offset * inner) // count
    mapped = max(0, min(inner - 1, mapped))
    return ("inside", mapped)


def paint_region(chars, start_pos: int, end_pos_exclusive: int, mark: str):
    if start_pos > end_pos_exclusive:
        start_pos, end_pos_exclusive = end_pos_exclusive, start_pos

    for pos in range(start_pos, end_pos_exclusive):
        if 0 <= pos < len(chars) and chars[pos] != "|":
            chars[pos] = mark


def map_interval_boundary(inner: int, tail: int, head: int, boundary_index: int):
    total = (head + 1) - tail
    if total <= 0:
        return 0

    offset = boundary_index - tail
    mapped = (offset * inner) // total
    mapped = max(0, min(inner, mapped))
    return mapped


def render_bar(width: int,
               tail: int,
               head: int,
               read_start: int,
               read_end: int,
               read_history,
               show_current_region: bool = False,
               show_half_marker: bool = False) -> str:
    if width < 6:
        return " " * width

    inner = width - 4
    if inner < 1:
        inner = 1

    chars = [TIMELINE_CHAR] * inner
    left = " "
    right = " "

    if show_half_marker:
        chars[(inner - 1) // 2] = "|"

    for old_tail, old_head, old_read in read_history:
        where, mapped = map_index_position(inner, old_tail, old_head, old_read)

        if where == "inside":
            if chars[mapped] != "|":
                chars[mapped] = HISTORY_MARK_CHAR
        elif where == "left":
            left = HISTORY_MARK_CHAR
        elif where == "right":
            right = HISTORY_MARK_CHAR

    if show_current_region:
        if read_start > read_end:
            read_start, read_end = read_end, read_start

        if read_start < tail:
            left = CURRENT_REGION_CHAR

        if read_end > (head + 1):
            right = CURRENT_REGION_CHAR

        visible_start = max(read_start, tail)
        visible_end = min(read_end, head + 1)

        if visible_start < visible_end:
            mapped_start = map_interval_boundary(
                inner, tail, head, visible_start
            )
            mapped_end = map_interval_boundary(
                inner, tail, head, visible_end
            )

            if mapped_end <= mapped_start:
                mapped_end = min(inner, mapped_start + 1)

            paint_region(chars, mapped_start, mapped_end, CURRENT_REGION_CHAR)

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
        state["read_start_index"],
        state["read_end_index"],
        state["read_history"],
        show_current_region=(state["mxl_status"] == MXL_STATUS_OK),
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


def compute_safety_status(safety_margin_state: dict) -> str:
    min_margin = safety_margin_state["min"]
    read_unit_size = safety_margin_state["read_unit_size"]

    if min_margin is not None and min_margin < 0:
        return "FAIL"

    if read_unit_size is None:
        return ""

    p0_01_margin = safety_margin_state["estimator"].p0_01_estimate()
    if p0_01_margin is None:
        return ""

    if p0_01_margin < read_unit_size:
        return "CRITICAL"

    if p0_01_margin < (2.0 * read_unit_size):
        return "WARN"

    return ""


def render_safety_margin_header() -> str:
    return (
        f"{'':<{SAFETY_STATS_LABEL_WIDTH}}"
        f"{'last':>{STATS_TIME_WIDTH}}  "
        f"{'mean':>{STATS_TIME_WIDTH}}  "
        f"{'med':>{STATS_TIME_WIDTH}}  "
        f"{'p0.1':>{STATS_TIME_WIDTH}}  "
        f"{'p0.05':>{STATS_TIME_WIDTH}}  "
        f"{'p0.01':>{STATS_TIME_WIDTH}}  "
        f"{'min':>{STATS_TIME_WIDTH}}  "
        f"{'n':>{STATS_COUNT_WIDTH}}  "
        f"{'status':>{SAFETY_STATUS_WIDTH}}"
    )


def render_safety_margin_row(label: str, state: dict) -> str:
    safety_margin = state["safety_margin"]
    estimator = safety_margin["estimator"]
    status = compute_safety_status(safety_margin)

    mean_margin = None
    if safety_margin["count"] > 0:
        mean_margin = safety_margin["sum"] / safety_margin["count"]

    return (
        f"{label:<{SAFETY_STATS_LABEL_WIDTH}}"
        f"{format_safety_margin(safety_margin['last']):>{STATS_TIME_WIDTH}}  "
        f"{format_safety_margin(mean_margin):>{STATS_TIME_WIDTH}}  "
        f"{format_safety_margin(estimator.median_estimate()):>{STATS_TIME_WIDTH}}  "
        f"{format_safety_margin(estimator.p0_1_estimate()):>{STATS_TIME_WIDTH}}  "
        f"{format_safety_margin(estimator.p0_05_estimate()):>{STATS_TIME_WIDTH}}  "
        f"{format_safety_margin(estimator.p0_01_estimate()):>{STATS_TIME_WIDTH}}  "
        f"{format_safety_margin(safety_margin['min']):>{STATS_TIME_WIDTH}}  "
        f"{safety_margin['count']:>{STATS_COUNT_WIDTH}}  "
        f"{status:>{SAFETY_STATUS_WIDTH}}"
    )


def render_too_late_header() -> str:
    return (
        f"{'':<{TL_STATS_LABEL_WIDTH}}  "
        f"{'too_late':>{STATS_TOO_LATE_WIDTH}}  "
        f"{'mean':>{STATS_TIME_WIDTH}}  "
        f"last {TOO_LATE_HISTORY_DISPLAY_LEN} OK->TOO_LATE|ok_margin|tl_margin"
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
        format_interval_margins(interval_ms, ok_margin_units, tl_margin_units)
        for interval_ms, ok_margin_units, tl_margin_units
        in too_late_timing["recent_pairs"]
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


def draw_audio_min_marker(stdscr,
                          y: int,
                          state: dict,
                          total_width: int):
    if not state["have_data"]:
        return

    min_margin = state["safety_margin"]["min"]
    if min_margin is None:
        return

    tail = state["tail_index"]
    head = state["head_index"]

    ring_depth = head - tail + 1
    if ring_depth <= 0:
        return

    min_index = int(round(
        tail + (ring_depth / 2.0) + min_margin
    ))

    prefix_len = len(f"{'AUDIO':<5} {ring_depth:>{DEPTH_WIDTH}} ")
    suffix_len = 2 + OK_WIDTH + 2 + ERROR_WIDTH

    bar_width = total_width - prefix_len - suffix_len
    if bar_width < 8:
        bar_width = 8

    inner = max(1, bar_width - 4)

    where, mapped = map_index_position(
        inner,
        tail,
        head,
        min_index,
    )

    if where != "inside":
        return

    x = prefix_len + 1 + mapped

    safe_addnstr(
        stdscr,
        y,
        x,
        AUDIO_MIN_SAFETY_MARK_CHAR,
        1,
    )


def format_elapsed(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"


def compute_elapsed_fps(video: dict, elapsed_seconds: float):
    ok_video_frame_count = video["ok_video_frame_count"]
    if elapsed_seconds <= 0.0 or ok_video_frame_count <= 0:
        return "-"
    return f"{ok_video_frame_count / elapsed_seconds:.2f}"


def compute_elapsed_sps(audio: dict, elapsed_seconds: float):
    ok_audio_sample_count = audio["ok_audio_sample_count"]
    if elapsed_seconds <= 0.0 or ok_audio_sample_count <= 0:
        return "-"
    return f"{ok_audio_sample_count / elapsed_seconds:.0f}"


def draw_ui(stdscr,
            start_monotonic: float,
            video: dict,
            audio: dict,
            paused: bool,
            ffmpeg_status: dict,
            host_status: dict):
    stdscr.erase()
    rows, cols = stdscr.getmaxyx()

    elapsed_seconds = time.monotonic() - start_monotonic
    elapsed = format_elapsed(elapsed_seconds)
    elapsed_fps = compute_elapsed_fps(video, elapsed_seconds)
    elapsed_sps = compute_elapsed_sps(audio, elapsed_seconds)
    paused_text = "   PAUSED" if paused else ""

    safe_addnstr(
        stdscr,
        0,
        0,
        (
            f"FFmpeg MXL diagnostic monitor"
            f"   elapsed: {elapsed}"
            f"   elapsed FPS: {elapsed_fps}"
            f"   elapsed SPS: {elapsed_sps}"
            f"{paused_text}"
        ),
        cols - 1,
    )

    safe_addnstr(stdscr, 2, 0, render_stream_line("VIDEO", video, cols - 1), cols - 1)
    safe_addnstr(stdscr, 3, 0, render_stream_line("AUDIO", audio, cols - 1), cols - 1)

    draw_audio_min_marker(
        stdscr,
        4,
        audio,
        cols - 1,
    )

    safe_addnstr(stdscr, 6, 0, render_stats_header(), cols - 1)
    safe_addnstr(stdscr, 7, 0, render_stats_row("VIDEO OK", video), cols - 1)
    safe_addnstr(stdscr, 8, 0, render_stats_row("AUDIO OK", audio), cols - 1)

    safe_addnstr(stdscr, 10, 0, render_safety_margin_header(), cols - 1)
    safe_addnstr(stdscr, 11, 0, render_safety_margin_row("VIDEO SAFE", video), cols - 1)
    safe_addnstr(stdscr, 12, 0, render_safety_margin_row("AUDIO SAFE", audio), cols - 1)

    safe_addnstr(stdscr, 14, 0, render_too_late_header(), cols - 1)
    safe_addnstr(stdscr, 15, 0, render_too_late_row("VIDEO TL", video), cols - 1)
    safe_addnstr(stdscr, 16, 0, render_too_late_row("AUDIO TL", audio), cols - 1)

    safe_addnstr(stdscr, 18, 0, render_exec_header(), cols - 1)
    safe_addnstr(stdscr, 19, 0, render_exec_row("VIDEO EX", video), cols - 1)
    safe_addnstr(stdscr, 20, 0, render_exec_row("AUDIO EX", audio), cols - 1)

    safe_addnstr(stdscr, rows - 4, 0, "q quit   p pause/resume UI   c clear/restart", cols - 1)
    safe_addnstr(stdscr, rows - 2, 0, format_ffmpeg_status(ffmpeg_status), cols - 1)
    safe_addnstr(stdscr, rows - 1, 0, format_host_status(host_status), cols - 1)
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
           sock: socket.socket,
           ffmpeg_status: dict,
           host_status: dict):
    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    stdscr.nodelay(True)

    start_monotonic, video, audio = reset_monitor_state()
    paused = False
    status_state = {
        "last_sample_monotonic": None,
    }

    update_dynamic_statuses(host_status, ffmpeg_status)
    status_state["last_sample_monotonic"] = time.monotonic()

    draw_ui(
        stdscr,
        start_monotonic,
        video,
        audio,
        paused,
        ffmpeg_status,
        host_status,
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

        now_monotonic = time.monotonic()
        maybe_update_dynamic_statuses(
            host_status,
            ffmpeg_status,
            status_state,
            paused,
            now_monotonic,
        )

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
                ffmpeg_status,
                host_status,
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

    ffmpeg_status = make_ffmpeg_status(args.server_socket)
    host_status = make_host_status()

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        sock.bind(args.client_socket)
        sock.setblocking(True)
        sock.sendto(build_header_only_message(MXL_DIAG_MSG_CONNECT), args.server_socket)

        curses.wrapper(
            run_ui,
            sock,
            ffmpeg_status,
            host_status,
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
