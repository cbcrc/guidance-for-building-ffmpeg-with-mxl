# Bootstrap an FFmpeg/MXL development environment.

This is one method to quickly bring up an FFmpeg/MXL development
environment. The end result is the FFmpeg source configured and built
with local directory executables.

Assumed starting point: a fresh Ubuntu 24.04, with `git` installed

Clone this guide to access the build scripts.

```
$ git clone https://github.com/cbcrc/guidance-for-building-ffmpeg-with-mxl.git guide
```

Get the FFmpeg plus MXL source and build. The
`host-setup-and-build.sh` script will prompt for a sudo password to
install `apt` package dependencies. This will produce a tested MXL
build, a tested FFmpeg build with a minimal configuration.

```
$ ./guide/scripts/get-src.sh ~/dev/src
$ ./guide/scripts/host-setup-and-build.sh ~/dev/src ~/dev/build --dev --allow-root
```

Clone the FFmpeg repository from which you will work. For example


```
$ git clone git@github.com:cbcrc/FFmpeg.git  # Or your fork
$ cd ./FFmpeg
$ git switch dmf-mxl/master                  # Or your branch
```

Set up PKG_CONFIG_PATH in your shell environment so that `pkg-config`
can locate your MXL build.

```
# Pull PKG_CONFIG_PATH from the script's FFmpeg build:
$ grep PKG_CONFIG_PATH= ~/dev/build/ffmpeg/build/Linux-GCC-Debug/static/ffbuild/config.log 
PKG_CONFIG_PATH='$HOME/dev/build/mxl/install/Linux-GCC-Debug/static/lib/pkgconfig:$HOME/dev/build/mxl/install/Linux-GCC-Debug/static/x64-linux/lib/pkgconfig'

# For example, this will set PKG_CONFIG_PATH in your environment:
$ eval "$(grep PKG_CONFIG_PATH= ~/dev/build/ffmpeg/build/Linux-GCC-Debug/static/ffbuild/config.log )"

# Confirm:
$ echo $PKG_CONFIG_PATH
$HOME/dev/build/mxl/install/Linux-GCC-Debug/static/lib/pkgconfig:$HOME/dev/build/mxl/install/Linux-GCC-Debug/static/x64-linux/lib/pkgconfig
```

Configure your FFmpeg development repository to match the build
script's configuration.

Run the build script's FFmpeg binary to see its configuration:

```
$ ~/dev/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffmpeg -version
ffmpeg version git-2026-03-24-b2ad5e2 Copyright (c) 2000-2025 the FFmpeg developers
built with gcc 13 (Ubuntu 13.3.0-6ubuntu2~24.04.1)
configuration: --prefix=$HOME/dev/build/ffmpeg/install/Linux-GCC-Debug/static --disable-everything --enable-demuxer=mxl --enable-muxer=mxl --enable-libmxl --enable-muxer=framemd5 --enable-muxer=null --enable-encoder=pcm_f32le --enable-decoder=pcm_f32le --enable-encoder=pcm_s16le --enable-decoder=pcm_s16le --enable-encoder=rawvideo --enable-decoder=rawvideo --enable-encoder=v210 --enable-decoder=v210 --enable-encoder=wrapped_avframe --enable-decoder=wrapped_avframe --enable-indev=lavfi --enable-filter=scale --enable-filter=testsrc2 --enable-filter=anoisesrc --enable-filter=sine --enable-filter=aresample --enable-filter=nullsrc --enable-protocol=pipe --extra-cflags='-march=core-avx2 -mtune=icelake-server' --enable-debug=2 --assert-level=2 --disable-optimizations --disable-stripping --pkg-config-flags=--static --enable-static --disable-shared --extra-libs=/usr/lib/gcc/x86_64-linux-gnu/13/libstdc++.a
```

Configure your development FFmpeg to match the build script's
configuration. For example, this will pull the configuration from the
build script's FFmpeg and apply it to your development repository.

```
$ eval "./configure $(~/dev/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffmpeg -version | sed -n 's/^configuration: //p')"
```

Build and test in your development FFmpeg repository.

```
$ make -j
$ make $(make fate-list | grep mxl)
TEST    mxl-audio-encdec
TEST    mxl-audio-probe
TEST    mxl-av-encdec
TEST    mxl-av-probe
TEST    mxl-bad-domain
TEST    mxl-bad-flow
TEST    mxl-bad-loc
TEST    mxl-json
TEST    mxl-loc
TEST    mxl-uri
TEST    mxl-video-encdec
TEST    mxl-video-probe
```

Check your local build:

```
$ ./ffmpeg -version
ffmpeg version N-121611-gb2ad5e20d2 Copyright (c) 2000-2025 the FFmpeg developers
built with gcc 13 (Ubuntu 13.3.0-6ubuntu2~24.04.1)
configuration: --prefix=$HOME/dev/build/ffmpeg/install/Linux-GCC-Debug/static --disable-everything --enable-demuxer=mxl --enable-muxer=mxl --enable-libmxl --enable-muxer=framemd5 --enable-muxer=null --enable-encoder=pcm_f32le --enable-decoder=pcm_f32le --enable-encoder=pcm_s16le --enable-decoder=pcm_s16le --enable-encoder=rawvideo --enable-decoder=rawvideo --enable-encoder=v210 --enable-decoder=v210 --enable-encoder=wrapped_avframe --enable-decoder=wrapped_avframe --enable-indev=lavfi --enable-filter=scale --enable-filter=testsrc2 --enable-filter=anoisesrc --enable-filter=sine --enable-filter=aresample --enable-filter=nullsrc --enable-protocol=pipe --extra-cflags='-march=core-avx2 -mtune=icelake-server' --enable-debug=2 --assert-level=2 --disable-optimizations --disable-stripping --pkg-config-flags=--static --enable-static --disable-shared --extra-libs=/usr/lib/gcc/x86_64-linux-gnu/13/libstdc++.a
libavutil      60. 16.100 / 60. 16.100
libavcodec     62. 17.100 / 62. 17.100
libavformat    62.  6.101 / 62.  6.101
libavdevice    62.  2.100 / 62.  2.100
libavfilter    11.  9.100 / 11.  9.100
libswscale      9.  3.100 /  9.  3.100
libswresample   6.  2.100 /  6.  2.100

Exiting with exit code 0
```

The development repository is ready.
