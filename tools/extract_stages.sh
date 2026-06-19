#!/usr/bin/env bash

# Extract stage names produced by FFmpeg's -debug_ts option and report
# muxer stage latency. Uses ./extract_stage_events.py.
#
# The first and last N -debug_ts events may be discarded using the
# --discard-first and --discard-last options. Discarding initial events
# can avoid startup transients, particularly one-time GPU/container
# initialization effects that can inflate early -debug_ts latency when
# FFmpeg runs with GPU encoding in a Docker container.
#
# By default, the first 200 and the last 20 events are discarded.
#
# For example:
#
# $ ffmpeg -loglevel debug -debug_ts ... > debug_ts.log 2>&1
#
# The ffmpeg sample collection should run for at least ~15 seconds.
#
# $ extract_stages.sh --discard-first 200 --discard-last 20 debug_ts.log
# ==== input side (demux->decode)
# == demux
# [vist#0:0/v210 @ 0x5da879b18c80] demuxer ->
# [vist#0:0/v210 @ 0x5da879b18c80] demuxer+ffmpeg ->
# [vist#0:0/v210 @ 0x5da879b18c80] demuxer+tsfixup ->
# [aist#1:0/pcm_f32le @ 0x5da879b1a100] demuxer ->
# [aist#1:0/pcm_f32le @ 0x5da879b1a100] demuxer+ffmpeg ->
# [aist#1:0/pcm_f32le @ 0x5da879b1a100] demuxer+tsfixup ->
# == decode
# [vist#0:0/v210 @ 0x5da879b18c80] [dec:v210 @ 0x5da879f743c0] decoder ->
#
# ==== output side (filter->encode->mux)
# == filter
# [vf#0:0 @ 0x5da879b4b740] filter ->
# [vf#0:0 @ 0x5da879fce0c0] filter_raw ->
# [af#0:1 @ 0x5da879c6ac80] filter_raw ->
# == encode
# [vost#0:0/h264_nvenc @ 0x5da879b2f440] [enc:h264_nvenc @ 0x5da879b2f980] encoder ->
# [vost#0:0/h264_nvenc @ 0x5da879b2f440] [enc:h264_nvenc @ 0x5da879b2f980] encoder <-
# [aost#0:1/libopus @ 0x5da879f83700] [enc:libopus @ 0x5da879b5f900] encoder ->
# [aost#0:1/libopus @ 0x5da879f83700] [enc:libopus @ 0x5da879b5f900] encoder <-
# == mux
# [vost#0:0/h264_nvenc 0x5da879b2f440] muxer <- [count=465, median=5.060 p99=8.149 max=8.295 ms]
# [aost#0:1/libopus @ 0x5da879f83700] muxer <- [count=1582, median=0.022 p99=0.387 max=0.607 ms]

set -euo pipefail

discard_first=200
discard_last=20

while [[ $# -gt 0 ]]; do
    case "$1" in
        --discard-first)
            discard_first="$2"
            shift 2
            ;;
        --discard-last)
            discard_last="$2"
            shift 2
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

[[ $# -lt 1 ]] && {
    echo "Usage: $0 [--discard-first N] [--discard-last N] <logfile>"
    exit 1
}

log=$(realpath -- "$1")

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

mkdir -p /tmp/ffstage
tmpdir="$(mktemp -d /tmp/ffstage/XXXX)"
mkdir -p "$tmpdir"

declare -A stage_patterns=(
  [demux]=' demuxer(\+[^ ]+)? ->'
  [decode]=' decoder ->'
  [filter]=' filter(_raw)? ->'
  [encode]=' encoder (->|<-)'
  [mux]=' muxer <-'
)

for stage in demux decode filter encode mux; do

    if [[ "$stage" == demux ]]; then
        echo "==== input side (demux->decode)"
    elif [[ "$stage" == filter ]]; then
        echo
        echo "==== output side (filter->encode->mux)"
    fi

    echo "== $stage"

    stage_log="$tmpdir/${stage}.log"
    grep -E "${stage_patterns[$stage]}" "$log" > "$stage_log"

    mapfile -t streams < <(grep -oE '#[0-9]+:[0-9]+' "$stage_log" | sort -u)

    for s in "${streams[@]}"; do
        readarray -t identifiers < <(
            grep -E "^\[[^]]*${s}[^]]*\].* (->|<-)" "$stage_log" |
                grep -oE '^\[[^]]+\]( \[[^]]+\])? [^ ]+ (->|<-)' |
                sort -u
        )

        for id in "${identifiers[@]}"; do
            if [[ "$stage" == "mux" ]]; then
                tmp="${id#\[}"
                outfile="${tmp%%#*}"
                echo "$id [$(./extract_stage_events.py "$stage" "$id" "$log" "$discard_first" "$discard_last" --summary --outfile "${outfile}.m")]"
            else
                echo "$id"
            fi
        done
    done
done

rm -rf /tmp/ffstage
