#!/usr/bin/env bash
# Deploy to Fly.io with the combat simulator bundled in.
#
# The GM's NPCs are built by the combat simulator (combat-design/design.md
# 4.1). Like every other file in the image, it comes from this machine: the
# simulator checkout's COMMITTED HEAD is exported into build-simulator/
# (gitignored), and its commit is passed as SIMULATOR_COMMIT so each
# generated NPC records exactly what built it. Uncommitted simulator edits
# never ship; the script says so when there are any.
#
#   scripts/deploy.sh                 # simulator from /host-l7r-repo/simulator
#   SIMULATOR_DIR=/path scripts/deploy.sh
#
# Extra arguments go to `fly deploy`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIM="${SIMULATOR_DIR:-/host-l7r-repo/simulator}"
OUT="$ROOT/build-simulator"

git -C "$SIM" rev-parse --verify HEAD >/dev/null 2>&1 || {
    echo "deploy: $SIM is not a git checkout of the combat simulator" >&2; exit 1; }
COMMIT="$(git -C "$SIM" rev-parse --short=12 HEAD)"
if [ -n "$(git -C "$SIM" status --porcelain --untracked-files=no)" ]; then
    echo "deploy: note - $SIM has uncommitted changes; deploying its committed HEAD ($COMMIT) only"
fi

rm -rf "$OUT"
mkdir -p "$OUT"
git -C "$SIM" archive --format=tar HEAD | tar -x -C "$OUT"
echo "deploy: bundled simulator $COMMIT"

set -a
# shellcheck disable=SC1091
[ -f "$ROOT/.env" ] && . "$ROOT/.env"
set +a
cd "$ROOT"
PATH="$HOME/.fly/bin:$PATH" flyctl deploy --build-arg "SIMULATOR_COMMIT=$COMMIT" "$@"
