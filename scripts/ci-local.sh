#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p .cache/actions .cache/act .cache/artifacts
exec .tools/act/act push -W .github/workflows/main.yml \
  -P ubuntu-latest=catthehacker/ubuntu:act-22.04 \
  --action-cache-path "$PWD/.cache/actions" --cache-server-path "$PWD/.cache/act" \
  --artifact-server-path "$PWD/.cache/artifacts" --container-daemon-socket /var/run/docker.sock "$@"
