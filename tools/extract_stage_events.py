#!/usr/bin/env python3
#
# Extract ffmpeg stage events from an ffmpeg -debug_ts log file. Used by extract_stages.sh to
# report latency statistics. Reports median, 99th percentile, and maximum latency.
#
# For example:
#
# $ ffmpeg -loglevel debug -debug_ts ... > debug_ts.log 2>&1
#
# $ ./extract_stage_events.py mux "[vost#0:0/h264_nvenc @ 0x5da879b2f440]" debug_ts.log 15 15  --summary
# count=289, median=4.478 p99=5.162 max=7.089 ms
#
# $ ./extract_stage_events.py mux "[vost#0:0/h264_nvenc @ 0x5da879b2f440]" debug_ts.log 15 15  
# count: 289
# median: 4.478 ms
# p99: 5.162 ms
# max: 7.089 ms
#
# requires: sudo apt install python3-numpy

import sys
import re
import argparse
import pathlib

try:
    import numpy as np
except ImportError:
    sys.exit("Error: numpy is required. Install with: sudo apt install python3-numpy")

parser = argparse.ArgumentParser(
    prog="extract_stage_events.py",
    usage="%(prog)s stage identifier logfile ignore_first ignore_last [--summary] [--outfile FILE]",
    description="Analyze ffmpeg -debug_ts timing events extracted from log data."
)

parser.add_argument("stage",
    help="pipeline stage name (demux, decode, filter, encode, mux)")

parser.add_argument("identifier",
    help="event name within the stage")

parser.add_argument("logfile",
    help="the ffmpeg log file to read")

parser.add_argument("ignore_first", type=int, nargs='?', default=0,
                    help="number of initial samples to ignore (default: 0)")

parser.add_argument("ignore_last", type=int, nargs='?', default=0,
                    help="number of final samples to ignore (default: 0)")

parser.add_argument("--summary",
    action="store_true",
    help="print summary statistics instead of raw values")

parser.add_argument("--outfile",
    metavar="FILE",
    help="write latencies as MATLAB/Octave variable to FILE")

args = parser.parse_args()

re_latency_total = re.compile(r'latency\(total:([0-9]+(?:\.[0-9]+)?)ms')

latencies = []

if args.stage != "mux":
    sys.exit("Error: only 'mux' stage currently supported")

with open(args.logfile, "r", errors="ignore") as f:
    for line in f:
        if args.identifier not in line:
            continue

        if args.stage == "mux":
            m = re_latency_total.search(line)
            if m:
                latencies.append(float(m.group(1)))

if args.stage == "mux":

    total_samples = len(latencies)

    if total_samples == 0:
        print("No samples found.", file=sys.stderr)
        sys.exit(1)

    if args.ignore_first + args.ignore_last >= total_samples:
        print("Ignore window too large for sample size.", file=sys.stderr)
        sys.exit(1)

    latencies = latencies[args.ignore_first: total_samples - args.ignore_last]

    p50, p99 = np.percentile(latencies, [50,99])
    mx = max(latencies)
    count = len(latencies)

    if args.summary:        
        print(f"count={count}, median={p50:.3f} p99={p99:.3f} max={mx:.3f} ms")
    else:
        print("count:", count)
        print(f"median: {p50:.3f} ms")
        print(f"p99: {p99:.3f} ms")
        print(f"max: {mx:.3f} ms")
        
    if args.outfile:
        varname = pathlib.Path(args.outfile).stem
        with open(args.outfile, "w") as f:
            f.write(f"% extracted from {args.logfile}\n")
            f.write(f"{varname} = [\n")
            for v in latencies:
                f.write(f"{v}\n")
            f.write("];\n")
