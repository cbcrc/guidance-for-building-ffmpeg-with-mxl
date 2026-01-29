#!/usr/bin/env bash

set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

for f in *.sh deps/*.sh module/*.sh; do
    shellcheck -x "$f"
done
