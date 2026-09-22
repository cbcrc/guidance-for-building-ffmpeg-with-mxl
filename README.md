# FFmpeg with MXL Support

This guide provides instructions for building and running
[FFmpeg](https://www.ffmpeg.org/) with [Media eXchange Layer
(MXL)](https://github.com/dmf-mxl/mxl) using the CBC/Radio-Canada
[FFmpeg fork](https://github.com/cbcrc/FFmpeg/tree/dmf-mxl/master).

## Overview

FFmpeg is a mature open-source project for decoding, encoding,
transcoding, multiplexing, demultiplexing, filtering, and streaming
audio, video, and data. MXL is an open-source media exchange layer
that uses shared memory to transport audio, video, and data.

FFmpeg is cross-platform, supporting most modern operating systems and
CPU architectures. MXL targets Linux systems and includes support for
macOS. Other platforms are not currently supported.

The MXL integration enables FFmpeg to use the Media eXchange Layer for
audio and video muxing and demuxing.

The FFmpeg/MXL integration currently supports Linux only.

## Requirements

| component | repository | branch | tag/commit |
|-----------|------------|--------|------------|
| MXL | [/dmf-mxl/mxl](https://github.com/dmf-mxl/mxl/tree/release/v1.0) | release/1.0 | 80623d7 |
| FFmpeg | [/cbcrc/ffmpeg](https://github.com/cbcrc/FFmpeg/tree/dmf-mxl/8.x-orig) | dmf-mxl/8.x-orig | 5c5d59370e |
| FFmpeg | [/cbcrc/ffmpeg](https://github.com/cbcrc/FFmpeg/tree/dmf-mxl/8.1) | dmf-mxl/8.1 | 9eddb90ac0 |
| FFmpeg | [/cbcrc/ffmpeg](https://github.com/cbcrc/FFmpeg/tree/dmf-mxl/9.0) | dmf-mxl/9.0 | 16abbf0413 |
| FFmpeg | [/cbcrc/ffmpeg](https://github.com/cbcrc/FFmpeg/tree/dmf-mxl/master) | dmf-mxl/master | 361268ffa2 |

The FFmpeg rows are the supported FFmpeg variants. `8.x-orig`
preserves the original FFmpeg/MXL development integration and is based
on upstream FFmpeg development between the 8.0 and 8.1 releases. `8.1`
and `9.0` track the corresponding FFmpeg release branches, while
`master` tracks the master branch of the cbcrc/FFmpeg fork.

The tag/commit is the last known good revision. These repos are cloned
by build scripts.

**Supported Operating System**
- Ubuntu 24.04

**Execution Environment**
- native host
- Docker container

**Compiler**
- GCC 13

**Build tools**
- CMake >= 3.24 (for MXL)


## FFmpeg/MXL integration

See the code structure, how to compile manually and test regressions [here](./docs/ffmpeg-devel.md)

## Build

- Build and package FFmpeg by following these [instructions](./docs/build.md).

## Usage

- [Simple examples](./docs/usage.md)
- [Streaming example](./docs/streaming.md)
- [Measurements tools](./tools/)

## Known Limitations & Future Work

- video/v210a (v210+alpha) is not supported 
- video/smpt201 (ancillary data) is not supported
- macOS FFmpeg/MXL build is not supported
- Writing MXL from file or test pattern results in jitter, especially when combining audio with video

## Support & Contribution

For questions, code review, or comments, contact the development team:

- Jim Trainor (james.p.trainor@cbc.ca)
