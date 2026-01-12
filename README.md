# Building FFmpeg with MXL Support

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
audio and video muxing and demuxing. Development on Windows is
supported via Docker containers.

The FFmpeg/MXL integration currently supports only Linux.

## Github Repositories

| component | repository | branch | tag/commit |
|-----------|------------|--------|------------|
| MXL | /dmf-mxl/mxl |  main | 52aea5a |
| FFmpeg | /cbcrc/ffmpeg | dmf-mxl/master | a8441ff |


The tag/commit is the last known good version.

Clone the entire repository:

```
$ git clone https://github.com/<repository>
```

Or reduce the size of the download, especially with FFmpeg, using:

```
$ git clone --single-branch --branch <branch> --depth 1 https://github.com/<repository>
```

Followed by:

```
$ git switch --detach <tag/commit>
```

The branch is the point from which development can optionally continue
after this revision:

```
$ git switch <branch>
```

## Platform Support

**Operating System**
* Ubuntu 24.04

**Execution Environment**
* native host
* Docker container

**Compiler**
* GCC 13

**Build tools**
* Cmake >= 3.24 (for MXL)

## MXL Build

Ensure MXL is built and installed in your environment. The MXL project
does not publish pre-built binaries. It's necessary to build the MXL
libraries from source.

See also: [MXL project's build documentation](https://github.com/dmf-mxl/mxl/blob/main/docs/Building.md).

## FFmpeg Build

This section describes the minimal FFmpeg configuration required to
build and run the regression tests for the MXL-related FFmpeg
components. The configuration enables only the FFmpeg components that
implement MXL support, rather than a full-featured FFmpeg build. It
also includes the components necessary to run ffplay with MXL sources.

### System Dependencies

System dependencies are [`apt` packages](https://documentation.ubuntu.com/server/how-to/software/package-management/index.html).

The FFmpeg build shares most of its system dependencies with the MXL
build. For reference, the MXL build dependencies are listed here:

* [`mxl-apt-pkgs.txt`](scripts/deps/mxl-apt-pkgs.txt)

The additional packages required to build FFmpeg with MXL support are listed here:

* [`ffmpeg-apt-pkgs.txt`](scripts/deps/ffmpeg-apt-pkgs.txt)

### Configure Options

The FFmpeg configure options that are required to enable MXL support
are:

* `--enable-demuxer=mxl`
* `--enable-muxer=mxl`
* `--enable-libmxl`

The FFmpeg build requires MXL to be discoverable via
`pkg-config`. Ensure that `PKG_CONFIG_PATH` includes the directory
containing the MXL `libmxl.pc` file. For example, test with:

```bash
$ PKG_CONFIG_PATH=~/build/mxl/build/Linux-GCC-Debug/shared/lib pkg-config --modversion libmxl
```

The FFmpeg `./configure` options used to build and run the FFmpeg/MXL
regression tests are listed in the following file:

* [`ffmpeg-configure-base-options.txt`](scripts/deps/ffmpeg-configure-base-options.txt)
* [`ffmpeg-configure-debug-options.txt`](scripts/deps/ffmpeg-configure-debug-options.txt)
* [`ffmpeg-configure-static-options.txt`](scripts/deps/ffmpeg-configure-static-options.txt)
* [`ffmpeg-configure-shared-options.txt`](scripts/deps/ffmpeg-configure-shared-options.txt)

This configuration enables the MXL-related FFmpeg components and disables
unrelated features where possible. It also includes the components
required to run ffplay with MXL sources.

See also: [FFmpeg Compilation Guide](https://trac.ffmpeg.org/wiki/CompilationGuide)

## Regression Tests

The FFmpeg/MXL integration has three FFmpeg regression tests:

|   |   |
|---|---|
| fate-mxl-json | JSON parser test |
| fate-mxl-video-encdec | MXL video muxer to MXL video demuxer smoke test |
| fate-mxl-audio-encdec| MXL audio muxer to MXL audio demuxer smoke test |

Run these in the FFmpeg build directory:

```bash
$ make fate-mxl-json fate-mxl-video-encdec fate-mxl-audio-encdec
```

## FFmpeg/MXL Integration Code Structure

### Modified/Added Files

**Core Implementation:**

- `libavformat/mxldec.c` - **MXL demuxer** (START HERE for demuxer code)
- `libavformat/mxlenc.c` - **MXL muxer** (START HERE for muxer code)

**Supporting Files:**

- `libavformat/Makefile`
- `libavformat/allformats.c`
- `libavformat/jsmn.c` / `libavformat/jsmn.h` - JSON parser
- `libavformat/mxl_common.h` - Common MXL definitions
- `libavformat/mxl_flow_def.h` - Flow definition structures
- `libavformat/mxl_json.c` / `libavformat/mxl_json.h` - JSON utilities

**Tests:**

- `libavformat/tests/mxl_json.c`
- `tests/Makefile`
- `tests/fate/mxl.mak` - Primary test integration makefile
- `tests/ref/fate/mxl-video-encdec`
- `tests/ref/fate/mxl-audio-encdec`
- `tests/ref/fate/mxl-json`

## Build scripts

|   |   |
|---|---|
| setup-env-mxl.sh | Install MXL build dependencies |
| setup-env-ffmpeg.sh | Install FFmpeg build dependencies |
| build-mxl.sh | Build MXL, test, and install. |
| build-ffmpeg.sh | Build FFmpeg, test, and install |
| cmake-repo-upgrade.sh | Update to latest cmake repositories. |
| host-full-build.sh | Full environment setup and build on host |
| docker-full-build.sh | Full environment setup and build in container |

The [scripts](scripts) directory has a set of Bash scripts to setup
the environment and build both MXL and FFmpeg. These scripts are a
canonical source for detailed FFmpeg/MXL environment configuration and
build instructions.

Note that these scripts set up the *minimum* set of system
dependencies and the *minimum* ffmpeg configuration that is necessary
to build FFmpeg with MXL and the FFmpeg/MXL regression tests.

The `setup-env-{mxl,ffmpeg}.sh` scripts install system dependencies
for the MXL and FFmpeg builds. Both will ask for a `sudo` password for
commands that require elevated permission. Avoid the `sudo` prompt by
running the setup script as root and using the `--allow-root` option.

```bash
$ setup-env-mxl.sh [--allow-root]
$ setup-env-ffmpeg.sh [--allow-root]
```

The `build-{mxl,ffmpeg}.sh` scripts download, configure, build, and
test MXL and FFmpeg. Both scripts build debug/release and
static/shared variants.

```bash
$ build-mxl.sh <build-dir>
$ build-ffmpeg.sh <build-dir>
```

For example, to build FFmpeg with MXL support in the `~/build`
directory:

```bash
$ build-mxl.sh ~/build && build-ffmpeg.sh ~/build
```

Look in the `~/build` for the results:

```bash
$ tree -L 4 ~/build
~/build
├── ffmpeg
│   ├── build
│   │   ├── Linux-GCC-Debug
│   │   │   ├── shared
│   │   │   └── static
│   │   └── Linux-GCC-Release
│   │       ├── shared
│   │       └── static
│   ├── install
│   │   ├── Linux-GCC-Debug
│   │   │   ├── shared
│   │   │   └── static
│   │   └── Linux-GCC-Release
│   │       ├── shared
│   │       └── static
│   └── src
│       └── FFmpeg
└── mxl
    ├── build
    │   ├── Linux-GCC-Debug
    │   │   ├── shared
    │   │   └── static
    │   └── Linux-GCC-Release
    │       ├── shared
    │       └── static
    ├── install
    │   ├── Linux-GCC-Debug
    │   │   ├── shared
    │   │   └── static
    │   └── Linux-GCC-Release
    │       ├── shared
    │       └── static
    └── src
        ├── mxl
```

A full Docker container setup and build is possible with:

``` bash
$ docker-full-build.sh <build-dir> [--skip-setup]
```

For example:

```bash
$ docker-full-build.sh ~/build
```

Will create the Docker container, run the setup scripts, and build MXL
and FFmpeg. The results will be in the host's ~/build directory.

To rebuild, but skip the setup, use:

```bash
$ docker-full-build.sh ~/build --skip-setup
```

The `host-full-build.sh` script works similarly but operates directly
on the host.

## Usage Examples

The following examples assume that MXL and FFmpeg were built using
`host-full-build.sh ~/build` or `docker-full-build.sh ~/build`.

### mxl-gst-videotestsrc mxl write → FFplay mxl read


```bash
$ mkdir -p /dev/shm/mxl
$ (cd ~/build/mxl/build/Linux-GCC-Debug/static && \
   ./tools/mxl-gst/mxl-gst-testsrc --video-config-file ./lib/tests/data/v210_flow.json --domain /dev/shm/mxl)&
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffplay /dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ed.mxl-flow
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffprobe /dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ed.mxl-flow
```

```bash
$ mkdir -p /dev/shm/mxl
$ (cd ~/build/mxl/build/Linux-GCC-Debug/static && ./tools/mxl-gst/mxl-gst-testsrc --audio-config-file ./lib/tests/data/audio_flow.json --domain /dev/shm/mxl )&
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffplay /dev/shm/mxl/b3bb5be7-9fe9-4324-a5bb-4c70e1084449.mxl-flow
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffprobe /dev/shm/mxl/b3bb5be7-9fe9-4324-a5bb-4c70e1084449.mxl-flow
```

#### ffprobe Expected Output

```sh
Input #0, mxl, from '/dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ed.mxl-flow':
  Duration: N/A, start: 0.000000, bitrate: N/A
  Stream #0:0: Video: v210 (v210 / 0x30313276), yuv422p10le(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 29.97 fps, 29.97 tbr, 29.97 tbn
    Metadata:
      mxl_id          : 5fbec3b1-1b0f-417d-9059-8b94a47197ed
      mxl_description : MXL Test Flow, 1080p29
      mxl_label       : MXL Test Flow, 1080p29
      mxl_format      : urn:x-nmos:format:video
      mxl_media_type  : video/v210
      mxl_colorspace  : BT709
```

```sh
Input #0, mxl, from '/dev/shm/mxl/b3bb5be7-9fe9-4324-a5bb-4c70e1084449.mxl-flow':
  Duration: N/A, start: 0.000000, bitrate: 3072 kb/s
  Stream #0:0: Audio: pcm_f32le, 48000 Hz, 2 channels, flt, 3072 kb/s
    Metadata:
      mxl_id          : b3bb5be7-9fe9-4324-a5bb-4c70e1084449
      mxl_description : MXL Audio Flow
      mxl_label       : MXL Audio Flow
      mxl_format      : urn:x-nmos:format:audio
      mxl_media_type  : audio/float32

```

### FFmpeg mxl write → ffplay mxl read

```bash
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffmpeg  -re -f lavfi -i testsrc2=size=1920x1080:rate=50 -c:v v210 -f mxl -video_flow_id fe781cad-8a82-4b8e-a3c2-f833c70ac73e /dev/shm/mxl &
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffplay /dev/shm/mxl/fe781cad-8a82-4b8e-a3c2-f833c70ac73e.mxl-flow
```

``` bash
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffmpeg -re -f lavfi -i "sine=frequency=200:sample_rate=48000,aformat=sample_fmts=flt:channel_layouts=stereo" -map 0:a:0 -c:a pcm_f32le -f mxl -audio_flow_id ca28b9ff-9d44-41ba-9c88-99329e7995a6 /dev/shm/mxl &
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffplay /dev/shm/mxl/ca28b9ff-9d44-41ba-9c88-99329e7995a6.mxl-flow
```

### FFmpeg mxl write → mxl-info mxl read

```bash
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffmpeg  -re -f lavfi -i testsrc2=size=1920x1080:rate=50 -c:v v210 -f mxl -video_flow_id fe781cad-8a82-4b8e-a3c2-f833c70ac73e /dev/shm/mxl
$ ~/build/mxl/install/Linux-GCC-Debug/static/bin/mxl-info --domain /dev/shm/mxl --flow fe781cad-8a82-4b8e-a3c2-f833c70ac73e
```

```bash
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffmpeg -re -f lavfi -i "sine=frequency=200:sample_rate=48000,aformat=sample_fmts=flt:channel_layouts=stereo" -map 0:a:0 -c:a pcm_f32le -f mxl -audio_flow_id ca28b9ff-9d44-41ba-9c88-99329e7995a6 /dev/shm/mxl &
$ ~/build/mxl/install/Linux-GCC-Debug/static/bin/mxl-info --domain /dev/shm/mxl --flow ca28b9ff-9d44-41ba-9c88-99329e7995a6
```

#### mxl-info Expected Output

```bash
- Flow [fe781cad-8a82-4b8e-a3c2-f833c70ac73e]
	           Version: 1
	       Struct size: 2048
	            Format: Video
	 Grain/sample rate: 50/1
	 Commit batch size: 1080
	   Sync batch size: 1080
	  Payload Location: Host
	      Device Index: -1
	             Flags: 00000000
	       Grain count: 10

	        Head index: 88411783498
	   Last write time: 1768235669455895609
	    Last read time: 1768235648241778461
	  Latency (grains): 18446744073709551591
	            Active: true
```


```bash
- Flow [ca28b9ff-9d44-41ba-9c88-99329e7995a6]
	           Version: 1
	       Struct size: 2048
	            Format: Audio
	 Grain/sample rate: 48000/1
	 Commit batch size: 480
	   Sync batch size: 480
	  Payload Location: Host
	      Device Index: -1
	             Flags: 00000000
	     Channel count: 2
	     Buffer length: 10240

	        Head index: 84875304606224
	   Last write time: 1768235403360202151
	    Last read time: 1768235403360202151
	  Latency (grains): 18446744073709528025
	            Active: true
```

## Known Limitations & Future Work

* v201a (v210+alpha) is not supported
* MacOS is not supported

## Support & Contribution

For questions, code review, or comments, contact the development team:

- Jim Trainor (james.p.trainor@cbc.ca)

---
**Last Updated:** January 12, 2026  
