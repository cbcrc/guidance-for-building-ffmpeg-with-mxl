#!/usr/bin/env bash

set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

shellcheck -x cmake_repo_upgrade.sh
shellcheck -x setup-env-mxl.sh
shellcheck -x setup-env-ffmpeg.sh
shellcheck -x build-mxl.sh
shellcheck -x build-ffmpeg.sh
shellcheck -x host.full.build.sh
shellcheck -x docker.full.build.sh

shellcheck -x module/bootstrap.sh
shellcheck -x module/exit_trap.sh
shellcheck -x module/logging.sh
shellcheck -x module/safe_sudo.sh
shellcheck -x module/user_context.sh
