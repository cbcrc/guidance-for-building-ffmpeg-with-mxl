#!/usr/bin/env bash

set -euo pipefail

if dpkg-query -W clang-19 llvm-19 lld-19 >/dev/null 2>&1; then
    update-alternatives --install /usr/bin/clang clang /usr/bin/clang-19 100
    update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-19 100
    update-alternatives --install /usr/bin/ld.lld ld.lld /usr/bin/ld.lld-19 100
fi
