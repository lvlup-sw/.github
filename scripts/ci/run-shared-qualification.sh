#!/usr/bin/env bash
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
release=https://github.com/astral-sh/uv/releases/download/0.9.26
archive=uv-x86_64-unknown-linux-gnu.tar.gz
curl --proto '=https' --fail --silent --show-error --location "$release/$archive" --output "$work/$archive"
curl --proto '=https' --fail --silent --show-error --location "$release/$archive.sha256" --output "$work/$archive.sha256"
(cd "$work" && sha256sum -c "$archive.sha256")
tar -xzf "$work/$archive" -C "$work"
uv="$work/uv-x86_64-unknown-linux-gnu/uv"
export UV_CACHE_DIR="$work/uv-cache"
cd actions/ci-lanes
"$uv" run --no-project --no-config --managed-python --python 3.12 \
  --with 'mypy==2.3.1' --with 'types-PyYAML==6.0.12.20260906' --with 'PyYAML==6.0.2' \
  mypy --strict --no-incremental ci_lanes tests
"$uv" run --no-project --no-config --managed-python --python 3.12 --with 'PyYAML==6.0.2' \
  python -m unittest discover --start-directory tests --top-level-directory . --verbose
