#!/usr/bin/env bash

# Update repositories to make the latest cmake available to the
# package mangager.
#
# Run this script as super user.
#
# This is an adapted version of the instructions at: https://apt.kitware.com

set -euo pipefail

echo "deb [signed-by=/usr/share/keyrings/kitware-archive-keyring.gpg] https://apt.kitware.com/ubuntu/ $(lsb_release -sc) main" >/etc/apt/sources.list.d/kitware.list

wget --quiet --output-document - https://apt.kitware.com/keys/kitware-archive-latest.asc |
    gpg --dearmor --batch --yes -o /usr/share/keyrings/kitware-archive-keyring.gpg

apt-get update

apt-get install kitware-archive-keyring
