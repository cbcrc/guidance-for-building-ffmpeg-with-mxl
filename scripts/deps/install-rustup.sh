#!/usr/bin/env bash
#
# See: https://rust-lang.org/tools/install

set -euo pipefail

# install rustup (official installer)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# verify
export PATH="$HOME/.cargo/bin:$PATH"
rustup --version
cargo --version
rustc --version
