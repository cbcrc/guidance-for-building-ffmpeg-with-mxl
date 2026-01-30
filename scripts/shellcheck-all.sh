#!/usr/bin/env bash

# Run ShellCheck on project scripts.
#
# Install `shellcheck` first: "apt install shellcheck"
#
# See: https://www.shellcheck.net

set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

for f in *.sh deps/*.sh module/*.sh; do
    shellcheck -x "$f"
done
