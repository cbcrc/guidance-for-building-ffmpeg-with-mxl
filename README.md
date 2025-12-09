# Building FFmpeg with MXL Support

This guide provides step-by-step instructions for building FFmpeg with Media eXchange Layer (MXL) support using the CBC/Radio-Canada fork.

## Overview

The MXL integration enables FFmpeg to use the Media eXchange Layer for video muxing and demuxing. This implementation currently supports video with audio support in development.

**Repository:** `cbcrc/FFmpeg`  
**Branch:** `dmf-mxl/master`  
**Latest MXL version:** hash `b876396` (as of Nov 17, 2025)

## Prerequisites

### Required Dependencies

- GCC 13 or compatible compiler
- MXL library (shared or static build)
- MXL-common library
- spdlog
- fmt
- SDL2 (for display/playback features)
- libfreetype
- libfontconfig
- libharfbuzz
- libfribidi

### MXL Installation

Ensure you have MXL installed in your environment. Note the installation paths:

- **Include path:** Location of MXL headers (e.g., `/path/to/mxl/install/include`)
- **Library path:** Location of MXL libraries (e.g., `/path/to/mxl/install/lib`)
- **vcpkg dependencies:** If using vcpkg (e.g., `/path/to/mxl/build/vcpkg_installed/x64-linux/lib`)

> **Note:** The reference implementation uses a static MXL build which requires an MXL patch. For simplicity, **it's recommended to use the shared library default** unless you specifically need static linking.

## Step-by-Step Build Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/cbcrc/FFmpeg.git
cd FFmpeg
git checkout dmf-mxl/master
```

### 2. Configure the Build

Run the configure script with MXL-specific options. **You must adapt the paths** in `--extra-cflags` and `--extra-ldflags` to match your MXL installation:

```bash
./configure \
  --disable-everything \
  --enable-demuxer=mxl \
  --enable-muxer=mxl \
  --enable-decoder=v210 \
  --enable-encoder=v210 \
  --enable-muxer=rawvideo \
  --enable-decoder=rawvideo \
  --enable-encoder=rawvideo \
  --enable-filter=scale \
  --enable-sdl2 \
  --extra-cflags='-I/path/to/your/mxl/install/include' \
  --extra-ldflags='-L/path/to/your/mxl/install/lib' \
  --extra-libs='-lmxl -lmxl-common -lspdlog -lfmt -lstdc++' \
  --enable-network \
  --enable-protocol=http \
  --enable-protocol=file \
  --enable-protocol=pipe \
  --enable-avfilter \
  --enable-indev=lavfi \
  --enable-filter=color \
  --enable-filter=testsrc \
  --enable-filter=testsrc2 \
  --enable-filter=drawtext \
  --enable-decoder=wrapped_avframe \
  --enable-libfreetype \
  --enable-libfontconfig \
  --enable-libharfbuzz \
  --enable-libfribidi \
  --enable-muxer=framemd5
```

#### For Development/Debug Build

Add these additional flags for debugging:

```bash
  --disable-optimizations \
  --disable-stripping \
  --enable-debug=2 \
  --assert-level=2 \
  --ignore-tests=source \
  --extra-cflags='-g -O0 -fno-inline -fno-omit-frame-pointer'
```

#### For Static Linking (Advanced)

If you need static linking with MXL:

```bash
  --pkg-config-flags=--static \
  --extra-ldflags='-L/path/to/mxl/build/vcpkg_installed/x64-linux/lib'
```

> **Important:** Static MXL builds require a patch. Contact the development team if needed.

### 3. Build FFmpeg

```bash
make -j$(nproc)
```

### 4. Verify the Build

Check that MXL support is properly compiled:

```bash
./ffmpeg -buildconf
```

You should see `--enable-demuxer=mxl` and `--enable-muxer=mxl` in the configuration output, along with the MXL library references in `--extra-libs`.

### 5. Run Regression Tests

Execute the FATE tests to verify MXL functionality:

```bash
make fate-mxl-json fate-mxl-encdec
```

- `fate-mxl-json`: Tests the JSON parser
- `fate-mxl-encdec`: Smoke test that runs a simple muxer→demuxer test with two FFmpeg instances

## Help messages

### MXL Muxer

```sh
./ffmpeg -hide_banner -help muxer=mxl
```

```sh
Muxer mxl [Media eXchange Layer]:
    Common extensions: mxl-flow.
    Default video codec: v210.
mxl muxer AVOptions:
  -flow_id           <string>     E..V....... MXL flow ID
  -teardown_sync_file <string>     E..V....... wait for sentinel file to appear before destroying flow
  -teardown_sync_timeout <int>        E..V....... maximum wait time in ms for teardown sync file (from 0 to 10000) (default 2000)
```

> **Note:** The muxer now automatically generates the JSON flow definition file. The flow ID is provided on the command line, and other parameters are derived from the FFmpeg stream.

### MXL Demuxer

```sh
./ffmpeg -hide_banner -help demuxer=mxl
```

```sh
Demuxer mxl [Media eXchange Layer]:
    Common extensions: mxl-flow.
mxl demuxer AVOptions:
  -zero_copy         <boolean>    .D......... Use zero-copy packet delivery (experimental). (default false)
  -non_blocking      <boolean>    .D......... Don't block waiting for data (default false)
  -reset_on_drop     <boolean>    .D......... Reset presentation timestamp to zero on frame drop. (default false)
  -max_frames        <int>        .D......... stop after N frames (from 0 to INT_MAX) (default 0)
  -grain_index_init  <int>        .D......... initial MXL grain index (from 0 to 2) (default current)
     current         0            .D......... current time
     head            1            .D......... ring buffer head
     tail            2            .D......... ring buffer tail
  -on_too_late       <int>        .D......... action when MXL reports grain index too late (from 0 to 1) (default increment)
     increment       0            .D......... increment the grain index
     reset           1            .D......... reset to position defined by grain_index_init
```

## Usage

### mxl-gst-videotestsrc mxl write → FFplay mxl read

```bash
/path/to/mxl-gst-videotstsrc -d /dev/shm/mxl -v v210_flow.json
./ffplay  /dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ef.mxl-flow
./ffprobe /dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ef.mxl-flow
```

#### Expected Output

```sh
Input #0, mxl, from '/dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ef.mxl-flow':
  Duration: N/A, start: 0.000000, bitrate: N/A
  Stream #0:0: Video: v210 (v210 / 0x30313276), yuv422p10le(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 50 fps, 50 tbr, 50 tbn
    Metadata:
      mxl_id          : 5fbec3b1-1b0f-417d-9059-8b94a47197ef
      mxl_format      : urn:x-nmos:format:video
      mxl_label       : MXL Test File
      mxl_description : MXL Test File
      mxl_media_type  : video/v210
      mxl_colorspace  : BT709
```

### FFmpeg mxl write → ffplay mxl read

```sh
./ffmpeg  -re -f lavfi -i testsrc2=size=1920x1080:rate=50 -c:v v210 -f mxl -flow_id 5fbec3b1-1b0f-417d-9059-8b94a47197ef /dev/shm/mxl
./ffplay  /dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ef.mxl-flow
```

### FFmpeg mxl write → mxl-info mxl read

```sh
./ffmpeg  -re -f lavfi -i testsrc2=size=1920x1080:rate=50 -c:v v210 -f mxl -flow_id 5fbec3b1-1b0f-417d-9059-8b94a47197ef /dev/shm/mxl
/path/to/mxl-info  -d /dev/shm/mxl -f 5fbec3b1-1b0f-417d-9059-8b94a47197ef
```

#### Expected Output

```sh
- Flow [5fbec3b1-1b0f-417d-9059-8b94a47197ef]
	           Version: 1
	       Struct size: 4096
	   Last write time: 1761923438514506210
	    Last read time: 1761923437532249279
	            Format: Video
	             Flags: 00000000
	        Grain rate: 30/1
	       Grain count: 3
	        Head index: 52857703157
	  Latency (grains): 18446744073709551615     <<<< ?? BUG !!
	            Active: true
```

## Code Structure

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
- `tests/fate/mxl.mak`
- `tests/ref/fate/mxl-encdec`
- `tests/ref/fate/mxl-json`

## Known Limitations & Future Work

- Audio support is currently in development
- pkg-config integration needed for cleaner dependency management
- Static linking requires an MXL patch (shared libraries recommended)

## Support & Contribution

For questions, code review, or comments, contact the development team:

- James P. Trainor (james.p.trainor@cbc.ca)

---

**Last Updated:** November 17, 2025  
**MXL Version:** b876396
