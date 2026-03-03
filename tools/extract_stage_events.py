#!/usr/bin/env python3
#
# Extract ffmpeg stage events from an ffmpeg -debug_ts log file. Used by extract_stages.sh to
# compute average and stdev of the muxer latency.
#
# For example:
# $ ffmpeg -loglevel debug -debug_ts ... > debug_ts.log 2>&1
# $ ./extract_stage_events.py mux "[vost#0:0/h264_nvenc @ 0x5da879b2f440]" /dev/shm/mxl/test-rtsp-ffmpeg.log 15 15  --summary
# latency=4.5 ± 0.25 ms
# $ ./extract_stage_events.py mux "[vost#0:0/h264_nvenc @ 0x5da879b2f440]" /dev/shm/mxl/test-rtsp-ffmpeg.log 15 15  
# count: 289
# mean_latency_ms: 4.5
# stddev_latency_ms: 0.25
# min_latency_ms: 3.93
# max_latency_ms: 7.09

import sys
import re
import statistics

if len(sys.argv) < 4:
    print("Usage: extract_stage_events.py <stage> '<identifier>' <logfile> "
          "[ignore_first_N] [ignore_last_N] [--summary]")
    sys.exit(1)

stage = sys.argv[1]
identifier = sys.argv[2]
logfile = sys.argv[3]

ignore_first = 0
ignore_last = 0
summary_mode = False

# Parse optional args
for arg in sys.argv[4:]:
    if arg == "--summary":
        summary_mode = True
    elif ignore_first == 0:
        ignore_first = int(arg)
    elif ignore_last == 0:
        ignore_last = int(arg)

re_latency_total = re.compile(r'latency\(total:([0-9.]+)ms')

latencies = []

with open(logfile, "r", errors="ignore") as f:
    for line in f:
        if identifier not in line:
            continue

        if stage == "mux":
            m = re_latency_total.search(line)
            if m:
                latencies.append(float(m.group(1)))

if stage == "mux":

    total_samples = len(latencies)

    if total_samples == 0:
        print("No samples found.")
        sys.exit(0)

    if ignore_first + ignore_last >= total_samples:
        print("Ignore window too large for sample size.")
        sys.exit(0)

    latencies = latencies[ignore_first: total_samples - ignore_last]

    mean_val = statistics.mean(latencies)
    std_val = statistics.stdev(latencies) if len(latencies) > 1 else 0.0

    mean_i = round(mean_val,2)
    std_i = round(std_val, 2)



    if summary_mode:
        print(f"latency={mean_i} ± {std_i} ms")
    else:
        print("count:", len(latencies))
        print("mean_latency_ms:", mean_i)
        print("stddev_latency_ms:", std_i)
        print("min_latency_ms:", round(min(latencies), 2))
        print("max_latency_ms:", round(max(latencies), 2))
        
