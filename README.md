# Daily Battleships 🚢

A **one-puzzle-a-day** Battleships (Bimaru / Solitaire Battleships) game: find the
hidden fleet using only the row and column clues. Ships are straight and never
touch, not even at a corner. The numbers above each column and beside each row
count how many ship segments sit there, and the fleet composition is shown below
the board. Every puzzle has a **unique solution reachable by pure logic — no
guessing**.

Play daily, track your time, share your result. Built on a small reusable
daily-game platform (routing, timer, archive, personal stats, share loop,
optional global stats). See **[docs/GAME_CONTRACT.md](docs/GAME_CONTRACT.md)** for
how the puzzle plugs into the platform.

## How to play

- **Desktop:** left-click a cell to cycle **empty → ship → water → empty**;
  left-drag paints ship; **right-click** (or right-drag) paints water.
- **Mobile:** pick a tool (**🚢 Ship / 🌊 Water**) and **drag** to paint;
  **long-press** a cell for a quick water mark.
- Column/row numbers turn **green** when satisfied, **red** when exceeded.
- The fleet tray under the board ticks off each ship as you box it in.

## Quick start

```bash
cd app
export PATH="$HOME/.local/node/bin:$PATH"   # node is not system-wide here
npm install
npm run dev -- --port 5174                  # http://localhost:5174
```

## Generating puzzles

```bash
cd scripts
python3 gen_days.py -1 75      # generate days -1..75 into app/src/lib/game/data/days.js
python3 verify_days.py         # MANDATORY gate: unique + no-guess + clue/fleet consistent
python3 preview_day.py 0       # optional: render /tmp/bs_preview_0.png for visual QA
```

`gen_days.py` places a random legal fleet, derives the row/column clues, then
reveals the minimum given cells needed for a constraint-propagation (no-guess)
solver to finish the board. A separate backtracking solver cross-checks that the
solution is unique. `verify_days.py` re-checks every day independently — never
ship a day that fails it.

## Deploy

Static SvelteKit (`adapter-static`) to GitHub Pages via
`.github/workflows/deploy.yml`. Optional global stats run on a Cloudflare Worker
+ D1 (`backend/`); see `backend/README.md`.

Independent build. See **[CREDITS.md](CREDITS.md)**.
