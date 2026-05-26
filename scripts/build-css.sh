#!/usr/bin/env bash
#
# Compile the purged Tailwind stylesheet (app/static/css/app.css) using the
# standalone Tailwind CLI - no Node/npm required. The deploy does this in the
# Docker `cssbuild` stage; run this locally after editing templates/classes.
#
#   scripts/build-css.sh            # one-shot build
#   scripts/build-css.sh --watch    # rebuild on change during local dev
#
set -euo pipefail
cd "$(dirname "$0")/.."

TW_VERSION="${TAILWIND_VERSION:-v3.4.17}"
BIN="./bin/tailwindcss"

if [ ! -x "$BIN" ]; then
  mkdir -p bin
  echo "Downloading tailwindcss standalone ${TW_VERSION}..."
  curl -fsSL -o "$BIN" \
    "https://github.com/tailwindlabs/tailwindcss/releases/download/${TW_VERSION}/tailwindcss-linux-x64"
  chmod +x "$BIN"
fi

exec "$BIN" \
  -c tailwind.config.js \
  -i app/static/css/tailwind-input.css \
  -o app/static/css/app.css \
  --minify "$@"
