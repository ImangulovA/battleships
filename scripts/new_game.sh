#!/usr/bin/env bash
# Copy this template into a new sibling folder and stamp in a new game id/title.
# For GitHub, prefer the "Use this template" button; this is the local equivalent.
#
# Usage: scripts/new_game.sh <new-folder-name> <game-id> "<Game Title>"
#   e.g. scripts/new_game.sh daily_sudoku daily-sudoku "Daily Sudoku"
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <new-folder-name> <game-id> \"<Game Title>\"" >&2
  exit 1
fi

NEW_DIR="$1"
GAME_ID="$2"
GAME_TITLE="$3"

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$(cd "$(dirname "$SRC")" && pwd)/$NEW_DIR"

if [ -e "$DEST" ]; then
  echo "error: $DEST already exists" >&2
  exit 1
fi

echo "Copying $SRC -> $DEST"
# Copy without build artifacts / deps / VCS.
rsync -a \
  --exclude node_modules \
  --exclude .git \
  --exclude 'app/build' \
  --exclude 'app/.svelte-kit' \
  --exclude .DS_Store \
  "$SRC/" "$DEST/"

CFG="$DEST/app/src/lib/game/index.js"
# Stamp id + title (BSD/macOS sed compatible).
sed -i '' "s/id: 'lights-out'/id: '${GAME_ID}'/" "$CFG"
sed -i '' "s/title: 'Daily Lights Out'/title: '${GAME_TITLE}'/" "$CFG"

echo "Done."
echo "Next:"
echo "  cd $DEST/app && npm install && npm run dev"
echo "  then replace app/src/lib/game/GameComponent.svelte + data/ with your puzzle"
echo "  and edit app/src/lib/config.js (STATS_API, UNLOCK_PASSWORD)."
