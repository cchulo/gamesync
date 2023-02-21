#!/usr/bin/env bash

set -e -o pipefail

echo 'Installing gamesync'
sudo cp gamesync /usr/local/bin/
mkdir -p ~/.local/share/gamesync
echo 'gamesync installed!'
