#!/bin/sh
# Pack all sessions (takes, reports, picks) into a dated tar. usage: scripts/backup.sh [target-dir]
set -eu
cd "$(dirname "$0")/.."
target="${1:-backups}"
mkdir -p "$target"
file="$target/recording-assistant-$(date +%Y-%m-%d-%H%M).tar"
tar -cf "$file" sessions
echo "$file"
