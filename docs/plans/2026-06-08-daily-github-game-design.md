# daily_github_game — design

Date: 2026-06-08
Author: Amal Imangulov

## Goal

A reusable template repo for "one puzzle a day" web games (sudoku-like, distinct
puzzle UIs), sharing the daily cadence + social/stats plumbing of ru-catfishing
but decoupled from any specific game. Each new puzzle is a fork. Every fork gets
simple aggregate stats out of the box: % started, % finished, average play time.

## Approach (decisions)

- **Stack:** SvelteKit + adapter-static → GitHub Pages (reuse ru-catfishing's
  proven setup).
- **Backend:** one generalized Cloudflare Worker + D1 recording `start`/`finish`
  events (finish carries active ms + optional score) and serving aggregates.
  Optional — empty `STATS_API` ⇒ local-only, nothing breaks.
- **Distribution:** GitHub *template repository* ("Use this template"); plus a
  local `scripts/new_game.sh` scaffolder.

## Architecture

Clean split between a **platform layer** (never edited per fork) and a **game
layer** (the only place a fork changes), coupled through one config object and a
three-callback component contract.

### Platform — `app/src/lib/platform/`
- `days.js` — anchor-date ↔ index mapping; today/archive/future resolution.
- `timer.js` — active-time tracker, pauses on tab hidden.
- `storage.js` — per-day localStorage record: `{started, finished, startedAt,
  finishedAt, elapsedMs, live, state, result}`.
- `stats.js` — completion rate, current/max streak, avg & best time, optional
  score; game-agnostic via `GAME.scoreOf`.
- `api.js` — best-effort Worker client (`/start`, `/finish`, `/agg`), text/plain
  beacons, idempotent.
- `unlock.js` — `?unlock=` author-mode for future days (obfuscation, off when
  password empty).
- Routes `/`, `/archive`, `/stats`; `+layout.svelte` (neobrutalism light/dark).

### Game — `app/src/lib/game/` (fork edits only here)
- `index.js` — `GAME = {id, title, tagline, anchorDate, component, dayIndexes,
  loadDay, scoreOf, shareLine}`.
- `GameComponent.svelte` — puzzle UI; callbacks `onstart/onprogress/onfinish`.
- `data/` — day data in any shape.
- Ships a working **Lights Out 3×3** demo (solvable-by-construction scrambles).

### Backend — `backend/`
- `schema.sql` — `events` (idempotency, PK game+client+day+kind) + `day_stats`
  (started/finished/total_ms/total_score/scored_count, PK game+day).
- `src/index.js` — Worker routes; `game` column namespaces forks.
- `wrangler.toml`, `README.md`.

## Data flow

interaction → `onstart` → platform stamps started/live, starts timer, `/start`
→ moves → `onprogress(state)` → persisted for resume → solved → `onfinish(result)`
→ platform stops timer, merges `ms` into result, persists, `/finish(ms,score)`,
shows end screen → `fetchAgg` → cross-player numbers; share text via
`GAME.shareLine`.

## Key decisions

- **Generic metrics, not per-puzzle correctness.** start/finish/time generalize
  across any puzzle; a game's own score is opt-in through `scoreOf`.
- **Opaque state/result blobs.** Platform never inspects game internals → true
  reusability.
- **Idempotent events keyed by client+day+kind** so retries/backfills never
  double-count; raw per-move data stays local, only counts/times go global.
- **Build days ahead; graceful fallback** to latest available day.

## Open questions / future

- Richer archive (calendar grid like ru-catfishing) — currently a list.
- Optional confetti / celebration hook on finish.
- Per-game leaderboard if `scoreOf` set (backend already sums scores).
