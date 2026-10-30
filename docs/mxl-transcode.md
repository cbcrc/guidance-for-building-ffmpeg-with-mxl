# FFmpeg/MXL Index-Preserving Transcode

FFmpeg/MXL supports preserving MXL video grain and audio sample
indices when transferring media between MXL domains. The MXL demuxer
encodes the MXL read index as the FFmpeg packet PTS (Presentation
Timestamp). The MXL muxer then uses packet PTS values as MXL write
indices. This allows the indices to be preserved through an FFmpeg
processing pipeline, provided the original timestamp mapping is
maintained.

## Example

The following command is adapted from the MXL demux-to-mux FATE test
in [`mxl.mak`](https://github.com/cbcrc/FFmpeg/blob/dmf-mxl/master/tests/fate/mxl.mak).
The source flows must be active and the destination domain directory
must exist. Set the domain paths and source/destination flow IDs for
the intended flows.

```bash
ffmpeg -hide_banner -loglevel info \
    -f mxl -mxl_read_index_init head \
    -copytb 1 \
    -i "mxl:///path/to/src_domain?id=SOURCE_VIDEO_UUID&id=SOURCE_AUDIO_UUID" \
    -map 0:v:0 -map 0:a:0 \
    -copyts -c:v copy -c:a copy \
    -avoid_negative_ts disabled \
    -f mxl -mxl_write_index pts \
    -video_flow_id DEST_VIDEO_UUID \
    -audio_flow_id DEST_AUDIO_UUID \
    /path/to/dst_domain
```

## Options for MXL Index Preservation

| Option | Purpose |
|---|---|
| `-copytb 1` | Use the MXL demuxer time base for stream copying, preserving the original timestamp units and avoiding PTS rescaling that could alter the MXL write indices. For example, changing the time base from 1/48000 to 1/90000 would rescale a PTS of 48000 to 90000, and would change the PTS values, even though both represent 1 second. |
| `-copyts` | Prevent FFmpeg from removing the initial timestamp offset (rebasing). |
| `-avoid_negative_ts disabled` | Disable timestamp shifting by FFmpeg's output muxing layer. Even with `-copyts`, FFmpeg may adjust output timestamps, depending on the muxer configuration. For example, shifting the first PTS from 48000 to 0 would also shift all subsequent PTS values, changing the MXL write indices. This option prevents such adjustments. |
| `-mxl_write_index pts` | Use packet PTS in the MXL muxer to derive destination MXL indices instead of generating new indices (the default). |

## Validation Status

**Note:** This functionality is newly implemented and has been
validated through the FFmpeg/MXL FATE regression tests. It has not yet
undergone broader testing in production or other real-world usage
scenarios.
