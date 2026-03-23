# Build scripts

1. [Build on host](build-on-host)

|---|---|
| [`setup-env-mxl.sh`](scripts/setup-env-mxl.sh) | Install MXL build dependencies |
| [`setup-env-ffmpeg.sh`](scripts/setup-env-ffmpeg.sh) | Install FFmpeg build dependencies |
| [`setup-env-all.sh`](scripts/setup-env-all.sh) | Install MXL and FFmpeg build dependencies |
| [`get-src.sh`](scripts/get-src.sh) | Clone the MXL and FFmpeg source repositories at known-good revisions |
| [`build-mxl.sh`](scripts/build-mxl.sh) | Build MXL, test, and install |
| [`build-codecs.sh`](scripts/build-codecs.sh) | Build H.264 and Opus codecs from source for streaming |
| [`build-ffmpeg.sh`](scripts/build-ffmpeg.sh) | Build FFmpeg, test, and install |
| [`mxl-update-alternatives.sh`](scripts/deps/mxl-update-alternatives.sh) | Configure tool versions required by MXL |
| [`cmake-repo-upgrade.sh`](scripts/deps/cmake-repo-upgrade.sh) | Configure CMake repository to the version required by MXL |
| [`host-setup-and-build.sh`](scripts/host-setup-and-build.sh) | Full environment setup and build on host |
| [`docker-setup-and-build.sh`](scripts/docker-setup-and-build.sh) | Full environment setup and build in development container |
| [`Dockerfile.dev`](scripts/Dockerfile.dev)  | Development container with build dependencies |
| [`docker/prod/Dockerfile`](docker/prod/Dockerfile) | Production container with runtime dependencies and built artifacts |

The [scripts](scripts) directory has a set of Bash scripts to set up
the environment and build both MXL and FFmpeg. These scripts are a
canonical source for detailed FFmpeg/MXL environment configuration and
build instructions.

Note that these scripts set up the *minimum* set of system
dependencies and the *minimum* FFmpeg configuration that is necessary
to build FFmpeg with MXL and the FFmpeg/MXL regression tests.

The `get-src.sh` script installs all the MXL and FFmpeg source code at
the correct revision.

```bash
$ get-src.sh <src-dir>
```

The `setup-env-all.sh` script installs system dependencies for both MXL
and FFmpeg. It will ask for a `sudo` password to execute commands that
require elevated permissions. To avoid repeated requests for a `sudo`
password execute the script as root and use the `--allow-root`
option:

```bash
$ sudo setup-env-all.sh --allow-root
```

The `setup-env-{mxl,ffmpeg}.sh` scripts install system dependencies
for the MXL and FFmpeg builds individually.

The `build-{mxl,ffmpeg}.sh` scripts configure, build, and test MXL and
FFmpeg. Both scripts build static/shared and debug/release
variants. By default all variants are built: static+debug,
static+release, shared+debug, shared+release. Use the "--prod" option
to build only the static+release variant.  Use the "--dev" option to
build only the static+debug variant.

```bash
$ build-mxl.sh <src-dir> <build-dir> [--prod|--dev]
$ build-ffmpeg.sh <src-dir> <build-dir> [--prod|--dev]
```

For example, to build FFmpeg with MXL support in the `~/build`
directory:

```bash
$ get-src.sh ~/src
$ build-mxl.sh ~/src ~/build && build-ffmpeg.sh ~/src ~/build
```

Or, to build a single development variant:
```bash
$ get-src.sh ~/src
$ build-mxl.sh ~/src ~/build --dev && build-ffmpeg.sh ~/src ~/build --dev
```

Look in the `~/build` directory for the results:

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

### Host setup and build

The `host-setup-and-build.sh` script sets up the host environment
(`setup-env-all.sh`) and builds both MXL (`build-mxl.sh`) and FFmpeg
(`build-ffmpeg.sh`) in one command:

``` bash
$ host-setup-and-build.sh <src-dir> <build-dir> [--dev|--prod]
```
For example:

```bash
$ get-src.sh ~/src
$ host-setup-and-build.sh ~/src ~/build --dev
```

It will ask for a `sudo` password to execute commands that require
elevated permissions. To avoid repeated requests for a `sudo`
password, use the `--allow-root` option:

```bash
$ get-src.sh ~/src
$ host-setup-and-build.sh ~/src ~/build --dev --allow-root
```

#### Options pass-through

Command-line options are passed through to the underlying MXL and
FFmpeg setup and build scripts in order to control setup and build
configuration. For example, in the following command `--streaming` is
passed through to the `build-ffmpeg.sh` script:

```bash
$ get-src.sh ~/src
$ host-setup-and-build.sh ~/src ~/build --prod --streaming
```

#### FFmpeg FATE suite mirror

The `--streaming` build option runs the FFmpeg FATE test suite. The
tests access a local copy of the FATE test suite that is, by default,
copied from `rsync://fate-suite.ffmpeg.org/fate-suite/`.

The `ffmpeg.org` rsync copy can sometimes be quite slow. An optional
improvement is to pre-populate the fate-suite from a local mirror and
set the `FATE_SUITE_MIRROR` environment variable to make the mirror
available to the build scripts. This prevents `build-ffmpeg.sh` from
running `make fate-rsync`, which in turn avoids the potentially
lengthy `ffmpeg.org` rsync.

```bash
# rsync the fate-suite one time
$ rsync -av rsync://fate-suite.ffmpeg.org/fate-suite/ /mirror/fate-suite/

# set environment variable for the build scripts
$ export FATE_SUITE_MIRROR=/mirror/fate-suite/
#
# or configure an rsync server
$ export FATE_SUITE_MIRROR=rsync://192.168.1.100/fate-suite/

# get-src.sh will rsync the fate-suite from FATE_SUITE_MIRROR
$ ./get-src.sh ~/src

# build will not rsync the `ffmpeg.org` fate-suite
$ ./build-ffmpeg.sh ~/src ~/build --streaming --prod
```

### Streaming build

Use the `--streaming` and `--no-ffplay` options to build FFmpeg with:

* RTSP protocol support
* H.264 and Opus encoder support
* H.264 and Opus codecs built from source
* Nvidia NVENC and CUDA support
* `ffplay` and related dependencies disabled

```bash
$ get-src.sh ~/src --streaming
$ host-setup-and-build.sh ~/src ~/bin --prod --streaming --no-ffplay --allow-root
```

Note: the streaming build only supports `--prod`, resulting in a
static, optimized release build.

Reading more about streaming: [streaming details](docs/streaming.md)

### Docker development container

Docker development container setup and build is possible with:

``` bash
$ docker-setup-and-build.sh <src-dir> <build-dir> [--dev|--prod]
```

For example:

```bash
$ get-src.sh ~/src
$ docker-setup-and-build.sh ~/src ~/build --dev
```

```bash
$ get-src.sh ~/src --streaming
$ docker-setup-and-build.sh ~/src ~/bin --prod --streaming --no-ffplay
```

The `docker-setup-and-build.sh` script uses `Dockerfile.dev` to create
a reusable Docker image (named `ffmpeg-mxl-<mxl_version>-dev`), mount the host `~/src` and
`~/build` directories, run the setup scripts, and build MXL and
FFmpeg. The results will be in the host `~/build` directory.

### Docker production image

Use `docker/prod/Dockerfile` to build a production image:

```bash
$ docker build -f docker/prod/Dockerfile -t ffmpeg-mxl .
```

If using `FATE_SUITE_MIRROR` with the Docker build, it must be an rsync
server:

```bash
$ docker build --build-arg FATE_SUITE_MIRROR=rsync://192.168.1.100/fate-suite/ \
    -f docker/prod/Dockerfile -t ffmpeg-mxl .
```

`docker/prod/Dockerfile` stages an intermediate build environment
(`setup-env-all.sh`), retrieves the source code (`get-src.sh`), builds
MXL (`build-mxl.sh`), and builds FFmpeg (`build-ffmpeg.sh`). It then
stages a smaller final image containing only the runtime dependencies
and copies the FFmpeg build artifacts to `/opt`. The build is
configured for streaming and excludes `ffplay`.

## Ubuntu 20.04 Build (experimental)

Ubuntu 20.04 support is experimental. The MXL build requires
GCC 13. The FFmpeg build uses the OS-provided GCC 9. GCC 13 for Ubuntu
20.04 is sourced from an [Ubuntu
PPA](https://launchpad.net/~ubuntu-toolchain-r/+archive/ubuntu/test)
and may install more slowly than packages from the standard Ubuntu
release archive.

```bash
$ get-src.sh ~/src --mxl-patch mxl-ubuntu20.04-build.diff
$ host-setup-and-build.sh ~/src ~/build --mxl-gcc-preset GCC13 --mxl-cmake-config-args "-DBUILD_TOOLS=OFF" --prod --allow-root
```

```bash
$ get-src.sh ~/src --mxl-patch mxl-ubuntu20.04-build.diff
$ docker-setup-and-build.sh ~/src ~/build --mxl-gcc-preset GCC13 --mxl-cmake-config-args "-DBUILD_TOOLS=OFF" --dockerfile Dockerfile.ubuntu20.04.dev --prod
```

Streaming builds are supported:

```bash
$ get-src.sh ~/src --mxl-patch mxl-ubuntu20.04-build.diff
$ host-setup-and-build.sh ~/src ~/build --mxl-gcc-preset GCC13 --mxl-cmake-config-args "-DBUILD_TOOLS=OFF" --skip-setup --prod --streaming --no-ffplay --allow-root
```

```bash
$ get-src.sh ~/src --mxl-patch mxl-ubuntu20.04-build.diff
$ docker-setup-and-build.sh ~/src ~/build --mxl-gcc-preset GCC13 --mxl-cmake-config-args "-DBUILD_TOOLS=OFF" --dockerfile Dockerfile.ubuntu20.04.dev --prod --streaming --no-ffplay
```

Docker images built on Ubuntu 24.04 hosts are not guaranteed to be
backward-compatible with Ubuntu 20.04 hosts. For reliable deployment
on 20.04, images should be built using a 20.04 environment. See:
[Docker Multi-platform builds](https://docs.docker.com/build/building/multi-platform/)

## Extended FFmpeg Build (experimental)

Build support for an experimental *extended* configuration is
implemented by
[`setup-env-ffmpeg-extended.sh`](scripts/setup-env-ffmpeg-extended.sh)
and [`build-ffmpeg-extended.sh`](scripts/build-ffmpeg-extended.sh).
This build includes additional codecs and activates additional FFmpeg
features.

The extended configuration is enabled in both host and Docker builds
by adding the `--extended` option. Only the release build variant
(`--prod`) is supported.

``` bash
$ get-src.sh ~/src
$ host-setup-and-build.sh ~/src ~/build --prod --allow-root --extended
```

```bash
$ get-src.sh ~/src
$ docker-setup-and-build.sh ~/src ~/build --prod --extended
```

The extended build has been tested on Ubuntu 20.04 and Ubuntu 24.04.

## Addendum

### Docker Setup Hints

Ubuntu >= 20.04:

```bash
$ sudo apt install docker.io docker-buildx
$ sudo usermod -aG docker "$USER"

# start a new shell that refreshes group membership, or use `newgrp docker`
$ docker-setup-and-build.sh ...
```
