#!/usr/bin/env bash

set -euo pipefail

. /etc/os-release

if [ "$VERSION_ID" = "20.04" ]; then
    apt-get update
    apt-get install -y --no-install-recommends software-properties-common
    add-apt-repository -y ppa:ubuntu-toolchain-r/test
    apt-get update
fi
