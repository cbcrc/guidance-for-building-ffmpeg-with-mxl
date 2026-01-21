#!/usr/bin/env bash

set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

shellcheck -x setup-env-mxl.sh
shellcheck -x setup-env-ffmpeg.sh
shellcheck -x setup-env-all.sh
shellcheck -x build-mxl.sh
shellcheck -x build-ffmpeg.sh
shellcheck -x build-ffmpeg-extended.sh
shellcheck -x host-setup-and-build.sh
shellcheck -x docker-setup-and-build.sh

shellcheck -x deps/mxl-update-alternatives.sh
shellcheck -x deps/cmake-repo-upgrade.sh

shellcheck -x module/bootstrap.sh
shellcheck -x module/exit_trap.sh
shellcheck -x module/logging.sh
shellcheck -x module/safe_sudo.sh
shellcheck -x module/user_context.sh
shellcheck -x module/read_list.sh
