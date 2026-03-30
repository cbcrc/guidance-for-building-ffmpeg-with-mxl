# FFmpeg/MXL Integration

See [bootstrap-dev-env.md](bootstrap-dev-env.md) for a quick start on setting up a fresh development environment.

## Modified/added Files 

Repo: [/cbcrc/ffmpeg](https://github.com/cbcrc/FFmpeg/tree/dmf-mxl/master)

**Core Implementation:**

- `libavformat/mxldec.c` - **MXL demuxer** (START HERE for demuxer code)
- `libavformat/mxlenc.c` - **MXL muxer** (START HERE for muxer code)

**Supporting Files:**

- `libavformat/Makefile`
- `libavformat/allformats.c`
- `libavformat/jsmn.c` / `libavformat/jsmn.h` - JSON tokenizer
- `libavformat/mxl_common.h` - Common MXL definitions
- `libavformat/mxl_status.h` - MXL status to string helper
- `libavformat/mxl_flow_def.h` - MXL JSON flow definition formatting
- `libavformat/mxl_uri.c` / `libavformat/mxl_uri.h` - URI parser
- `libavformat/mxl_loc.c` / `libavformat/mxl_loc.h` - Locator parser
- `libavformat/mxl_json.c` / `libavformat/mxl_json.h` - JSON parser

**Tests:**

- `libavformat/tests/mxl_uri.c` - URI parser tests
- `libavformat/tests/mxl_loc.c` - Locator parser tests
- `libavformat/tests/mxl_json.c` - JSON parser tests
- `tests/Makefile`- FATE test registration
- `tests/fate/mxl.mak` - MXL FATE test definitions
- `tests/ref/fate/mxl-*` - Reference outputs

## MXL Build

Ensure MXL is built and installed in your environment. The MXL
libraries must be built from source.

See also: [MXL project's build documentation](https://github.com/dmf-mxl/mxl/blob/main/docs/Building.md).

## FFmpeg Build

This section describes the minimal FFmpeg configuration options to
build the FFmpeg/MXL regression tests and to ensure that `ffplay`
works with flows produced by the MXL SDK examples.

### System Dependencies

System dependencies are [`apt` packages](https://documentation.ubuntu.com/server/how-to/software/package-management/index.html).

The FFmpeg build shares most of its system dependencies with the MXL
build. For reference, the MXL build dependencies are listed here:

* [`mxl-apt-pkgs.txt`](/scripts/deps/mxl-apt-pkgs.txt)

The additional packages required to build FFmpeg with MXL support are listed here:

* [`ffmpeg-apt-pkgs.txt`](/scripts/deps/ffmpeg-apt-pkgs.txt)

### Configure Options

The FFmpeg configure options that are required to enable MXL support
are:

```bash
$ configure --enable-demuxer=mxl --enable-muxer=mxl --enable-libmxl ...
```

The FFmpeg build requires MXL to be discoverable via
`pkg-config`. Ensure that `PKG_CONFIG_PATH` includes the directory
containing the MXL `libmxl.pc` file. For example, test with:

```bash
$ PKG_CONFIG_PATH=~/build/mxl/install/Linux-GCC-Debug/static/lib/pkgconfig pkg-config --modversion libmxl
```

The FFmpeg `configure` option used to build and run the FFmpeg/MXL
regression tests are listed in the following files:

* [`ffmpeg-configure-base-options.txt`](/scripts/deps/ffmpeg-configure-base-options.txt)
* [`ffmpeg-configure-debug-options.txt`](/scripts/deps/ffmpeg-configure-debug-options.txt)
* [`ffmpeg-configure-static-options.txt`](/scripts/deps/ffmpeg-configure-static-options.txt)
* [`ffmpeg-configure-shared-options.txt`](/scripts/deps/ffmpeg-configure-shared-options.txt)

Additional build option files exist to disable the `ffplay` build and to
enable a selected group of streaming-related protocols and codecs.

* [`ffmpeg-configure-noplay-options.txt`](/scripts/deps/ffmpeg-configure-noplay-options.txt)
* [`ffmpeg-configure-streaming-options.txt`](/scripts/deps/ffmpeg-configure-streaming-options.txt)

See also: [FFmpeg Compilation Guide](https://trac.ffmpeg.org/wiki/CompilationGuide)

## Regression Tests

The FFmpeg/MXL integration has the following FFmpeg regression tests:

| Test | Description |
|---|---|
| `fate-mxl-uri` | URI parser test |
| `fate-mxl-loc` | Locator parser test |
| `fate-mxl-json` | JSON parser test |
| `fate-mxl-video-encdec` | MXL video muxer-to-demuxer test |
| `fate-mxl-audio-encdec` | MXL audio muxer-to-demuxer test |
| `fate-mxl-av-encdec` | MXL multi-flow audio+video muxer-to-demuxer test |
| `fate-mxl-video-probe` | MXL video probe test |
| `fate-mxl-audio-probe` | MXL audio probe test |
| `fate-mxl-av-probe` | MXL multi-flow audio+video probe test |
| `fate-mxl-bad-domain` | MXL demuxer test with non-existent MXL domains |
| `fate-mxl-bad-flow`   | MXL demuxer test with non-existent MXL flows |
| `fate-mxl-bad-loc`    | MXL demuxer test with malformed MXL locators |

Run these in the FFmpeg build directory:

```bash
$ make \
    fate-mxl-uri \
    fate-mxl-loc \
    fate-mxl-json \
    fate-mxl-video-encdec \
    fate-mxl-audio-encdec \
    fate-mxl-av-encdec \
    fate-mxl-video-probe \
    fate-mxl-audio-probe \
    fate-mxl-av-probe \
    fate-mxl-bad-domain \
    fate-mxl-bad-flow \
    fate-mxl-bad-loc \
```

Or

```bash
$ make $(make fate-list | grep mxl)
```
