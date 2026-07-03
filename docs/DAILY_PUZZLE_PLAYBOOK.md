# Daily Puzzle Playbook — build a new daily logic game end-to-end

This is a **replicable recipe** for shipping a "one puzzle a day" logic-puzzle web
game with **self-generated, provably unique, no-guessing puzzles**, a canvas UI
that works on desktop and mobile, global start/finish + time-percentile stats, and
GitHub Pages deploy. It is written from the finished **Train Tracks** build
(`~/Desktop/train_tracks/`) and generalised so a fresh Claude session can do the
same for another puzzle — the immediate next target is **Battleships (Bimaru /
Solitaire Battleships)**; see the last section.

Treat the Train Tracks repo as the **reference implementation**: when in doubt,
open the corresponding file there and mirror it.

---

## 0. TL;DR pipeline (do these in order)

1. **Fork the platform** `~/Desktop/daily_github_game/` → new sibling folder.
2. **Write a Python generator + solver** in `scripts/`:
   - random valid solution → derive row/col (and any other) clues,
   - reveal the **minimum given cells** until a **sound constraint-propagation
     solver** (forced moves only) fully solves it ⇒ *no-guess* AND (because the
     rules are sound) *unique*,
   - a **backtracking solver** as an independent uniqueness cross-check,
   - emit `app/src/lib/game/data/days.js` (`DAYS` map + `dayIndexes`/`loadDay`).
3. **Write `verify_days.py`** — an independent gate: for every day assert
   *unique + matches stored + clues consistent + no-guess*. Never ship a day that
   fails this.
4. **Write the Svelte component** `GameComponent.svelte` — canvas render + unified
   pointer input (desktop L/R-click + drag, mobile drag + mode toggle +
   long-press), and a win-check.
5. **Wire `GAME` config** `app/src/lib/game/index.js` (id, title, anchorDate,
   scoreOf, shareLine) and `config.js` (STATS_API, UNLOCK_PASSWORD).
6. **Difficulty schedule** by real weekday; preserve already-released days.
7. **Deploy stats**: Cloudflare Worker + D1 (`backend/`), set `STATS_API`.
8. **Git + GitHub Pages**: HTTPS remote, `actions/configure-pages`, CREDITS,
   gitignore source assets. **User pushes; assistant never pushes / never
   touches tokens.**

Everything below is the detail for each step + the traps we already hit.

---

## 1. The platform (`daily_github_game`)

A reusable SvelteKit + `adapter-static` template. The platform owns routing, the
active-play timer, per-day localStorage, the archive, the personal stats page, the
share loop, and the optional stats backend. **You only write the puzzle.**

Contract (see `docs/GAME_CONTRACT.md` in any fork):

- **`GAME` config** — `app/src/lib/game/index.js`: `id` (stable storage/backend
  namespace, never change post-launch), `title`, `tagline`, `anchorDate:[Y,
  monthIndex0..11, D]` (day 0's date), `component`, `dayIndexes()`, `loadDay(idx)`
  (returns your puzzle blob or null), `scoreOf(result)` (return `null` for
  time-only games), `shareLine(result, dayIdx, url)`.
- **Component** — `GameComponent.svelte`, props `{puzzle, dayIdx, saved}`,
  callbacks `onstart()` (once, first interaction — starts timer), `onprogress(state)`
  (resumable JSON blob, comes back as `saved`), `onfinish(result)` (once; platform
  attaches `ms` = active time).
- **Data** — `app/src/lib/game/data/days.js`: your generated days.

**Fork it** (the folder already contains a `sources/` for reference material, so
merge rather than clobber):

```bash
rsync -a --exclude node_modules --exclude .git --exclude 'app/build' \
  --exclude 'app/.svelte-kit' --exclude .DS_Store \
  ~/Desktop/daily_github_game/ ~/Desktop/<newgame>/
```

**Node is not system-wide on this machine.** Always:
`export PATH="$HOME/.local/node/bin:$PATH"` before `npm`. Dev:
`cd app && npm install && npm run dev -- --port 5174`.

---

## 2. Puzzle generation — THE core pattern (reused verbatim, only rules change)

The whole approach is generator-owns-the-answer, then reveal minimum clues:

### 2a. Represent the solution and generate a random valid one
Pick a random **valid full solution** directly (not by solving an empty board):
- Train Tracks: a random self-avoiding path between two border exits (randomised
  DFS with a step budget; resample on overflow).
- Battleships: random legal fleet placement (ships don't touch, even diagonally).

Use a **seeded RNG per day** (`random.Random(1000+idx)`) so generation is
reproducible.

### 2b. Derive the clues from the solution
Row/column counts of filled cells; plus any puzzle-specific clues (Battleships also
has the known **fleet composition**, and cell *type* hints from any revealed
cells).

### 2c. Reveal the MINIMUM givens for a no-guess puzzle
This is the key trick. Start with the unavoidable givens (Train Tracks: the two
exit pieces). Then loop:

```
while not logic_solve(givens).solved():
    reveal one more true-solution cell the logic solver hasn't pinned yet
```

`logic_solve` is a **constraint-propagation solver that only makes FORCED moves
(never guesses)**. Because every rule is **sound** (never sets a wrong value), if
it fully determines the board the result is *the* solution ⇒ the puzzle is both
**solvable without guessing** and **unique**. Revealing true-solution cells always
keeps the true solution valid, so the loop converges (worst case: reveal
everything).

> A weaker propagation ruleset just means slightly *easier* puzzles (more givens)
> — still correct and no-guess. So prioritise SOUND over complete.

### 2d. Independent uniqueness cross-check
Also run a **backtracking solver** counting solutions up to 2 and assert exactly
1. Belt-and-suspenders against a bug in the propagation solver.

### 2e. Backtracking solver design (generic)
Assign cells in row-major order; per cell try each legal state; prune with:
- consistency with already-placed neighbours (edges/adjacency),
- row/col clue upper-bound (never exceed) and lower-bound (must still be
  reachable) — check exact match at end of row/col,
- puzzle-specific structural rules,
- a `node_cap` (~120k) → on overflow, treat as "too hard", resample the puzzle.
At a full assignment, validate global structure (Train Tracks: single connected
path, no stray loops, via union-find).

### 2f. Constraint-propagation ("logic") solver design (generic)
Cell states `{UNKNOWN, FILLED, EMPTY}` (+ per-edge/per-type states as needed).
Init the hard constraints, then iterate rules to a fixpoint:
- translate any forced structure (borders, revealed cells, exits) into states,
- degree / shape rules (Train Tracks: a track cell has exactly 2 rails; can't
  reach 2 ⇒ EMPTY; has 2 ⇒ others OFF),
- **row/col clue saturation**: filled==clue ⇒ rest EMPTY; filled+unknown==clue ⇒
  rest FILLED,
- structural no-goods (Train Tracks anti-cycle: an unknown edge whose two cells
  are already connected must be OFF),
- set a `contradiction` flag on any conflict; stop.
`solved()` = no UNKNOWN cells/edges and no contradiction.

**Trap we hit:** initialise *positive* forced facts (exits ON) BEFORE the blanket
*negative* ones (all other borders OFF), or you get a false ON→OFF contradiction.

### 2g. Emit `days.js`
`export const DAYS = { "<idx>": {...blob...}, ... }` + `dayIndexes()` +
`loadDay(idx)`. Keep the blob JSON-ish (bare keys are fine; the verify script
quotes them). **Preserve already-released days** (see §5): read the existing
`days.js`, keep entries for a `PRESERVE` set verbatim, regenerate the rest.

### 2h. The verify gate (`verify_days.py`) — MANDATORY
Parse `days.js` (regex quote bare keys + strip trailing commas → `json.loads`).
For each day assert: backtracking `sols==1`, the unique solution `==` stored
solution, clues recomputed from solution match, cell-shape validity, and
`logic_solve()=='solved'` matching the stored solution (**no-guess**). Print a
line per day and exit non-zero on any failure. Run it after ANY change to the
generator/solver.

### 2i. Optional visual QA (`preview_day.py`)
Render a day to a PNG with Pillow, mirroring the component's draw math, since
headless browsers (Playwright/Chrome) are blocked on this machine. Read the PNG to
eyeball that puzzles look like the real thing.

Performance reference: Train Tracks 42 days (4×4..8×8) generate + verify in <1s.

---

## 3. The UI component (`GameComponent.svelte`)

**Canvas + pointer events** (unified mouse/touch). Key decisions we validated:

- **Input model** (Train Tracks used the edge model; pick the analogue):
  - Desktop: **left-click + drag** = primary action, **right-click / drag** =
    secondary ("mark empty"). `oncontextmenu` → `preventDefault`.
  - Mobile: **drag** performs the current tool; a **mode toggle** (primary /
    "empty") for bulk marking (this beats long-press for speed — the modern
    Google-Minesweeper pattern); plus **long-press (~450ms)** = quick secondary
    mark without switching mode.
  - A **stroke** decides add-vs-erase from its first cell/edge (paint behaviour).
- **Geometry**: compute `cell` from container width (clamp e.g. 30..64), reserve
  margins for clues; **DPR scaling** (`canvas.width = cssW*dpr`,
  `ctx.setTransform(dpr,...)`); `ResizeObserver` → refit.
- **CSS**: `touch-action: none; user-select: none;` on the canvas so drags don't
  scroll/select. Read theme colours via
  `getComputedStyle(canvas).getPropertyValue('--accent'|'--surface-2'|'--border'|
  '--muted'|'--ink')`.
- **Clue feedback**: colour a row/col clue green when satisfied, red when
  exceeded. Highlight local rule violations (Train Tracks: a >2-degree "fork"
  cell in red).
- **State**: keep player state as Sets/arrays; call `onprogress` on every change,
  `draw()` after mutations, and check win. **Win-check** = player's derived state
  equals the stored solution (given a unique solution). Provide **Undo** (stroke
  snapshots) and **Reset**.
- **Resume**: hydrate from `saved` on mount; init "given/locked" cells so they're
  always present and non-editable.

Also trim the platform end-screen / stats page to your game (remove Lights-Out
"moves"; we later removed the max-streak stat on request).

---

## 4. Stats backend (Cloudflare Worker + D1) — started/finished + time percentile

The platform ships `backend/` implementing exactly this pattern; reuse it.

**Endpoints** (`backend/src/index.js`): `POST /start`, `POST /finish`
(`{game,day,clientId,ms,score?}`), `GET /agg?game=&days=`. Bodies are parsed as
JSON but sent as `text/plain` by the client so `navigator.sendBeacon` stays a CORS
"simple request" (application/json beacons are silently dropped). Idempotent per
`(game,clientId,day,kind)`.

**Schema** (`backend/schema.sql`): `events` (idempotency log), `day_stats`
(counters: started, finished, total_ms, total_score, scored_count), and — added
for percentiles — **`finish_times(game,day,client_id,ms, PK(game,day,client_id))`**
(one time per solver; first solve counts). `/agg` returns per day `{started,
finished, ..., times:[sorted ms]}`.

**Percentile tier** (client, end screen): from `dayAgg().times` and the player's
`ms`, drop one self-matching entry (finish-beacon race), then
`pctFaster = 100 * (#times slower than me) / (#others)`; map to a badge
(≥90 Топ 10%, ≥75 Топ 25%, ≥50 Быстрее половины, else Финиш) + "Быстрее N%
игроков". Empty ⇒ "Первым решил!".

**Deploy** (wrangler is OAuth-authed to your own Cloudflare account; `wrangler
login` once, then it uses your account's `*.workers.dev` subdomain):

```bash
cd backend && export PATH="$HOME/.local/node/bin:$PATH"
npx wrangler d1 create <game>-stats            # paste database_id into wrangler.toml
npx wrangler d1 execute <game>-stats --remote --file=schema.sql --yes
npx wrangler deploy                            # prints the Worker URL
# put the URL in app/src/lib/config.js  ->  STATS_API
```

`wrangler.toml`: set `name`, `[[d1_databases]] database_id`, and
`ALLOWED_ORIGINS = "https://imangulova.github.io,http://localhost:5173,...5174,
...4173"` (origin is scheme+host only — one entry covers every Pages project).

**Traps:** `.wrangler/` caches the account id — **gitignore it** (we accidentally
committed it once and scrubbed). A **session security guard flags `curl`
POST/GET to the workers.dev domain as "data_exfiltration"** — validate the Worker
via `wrangler d1 execute ... SELECT`, `wrangler tail`, or the app instead of raw
curl. Clean out any smoke-test rows from D1 before launch.

---

## 5. Difficulty schedule (established weekly ramp)

Size by **real weekday** (Mon=0..Sun=6), computed from `ANCHOR = anchorDate`:
Train Tracks used `Mon 4×4 · Tue 5 · Wed 6 · Thu 7 · Fri 8 · Sat 7 · Sun 7`.
Map size→tier for display. **Preserve already-released days**: a `PRESERVE` set
(e.g. `{-1, 0}`) whose entries are copied verbatim from the existing `days.js` so
today's/past puzzles never change; regenerate the rest. Build a buffer ~60 days
ahead. Author-mode link to play unreleased days: `?unlock=<UNLOCK_PASSWORD>&day=N`.

---

## 6. Git + GitHub Pages deploy

- **Remote is HTTPS**, matching the user's working repos
  (`https://github.com/ImangulovA/<repo>.git`) — creds come from the macOS
  keychain, NOT a token in the URL. **SSH is not set up on this machine.**
- **GUARDRAIL: the assistant does local git (init/add/commit) ONLY. The user
  pushes** (`git push`) and creates the GitHub repo. **Never paste or handle
  GitHub tokens in chat** — a security guard blocks github ops when a PAT appears.
- **GitHub Pages** needs Source = **GitHub Actions**. The manual toggle alone
  didn't create the Pages site (deploy failed "try again later"). Fix that lives
  in the workflow: add to the build job
  ```yaml
  - name: Configure Pages
    uses: actions/configure-pages@v5
    with: { enablement: true }
  ```
  which enables Pages programmatically (workflow has `pages: write`). The
  `deploy.yml` derives `BASE_PATH=/<repo-name>` automatically. Live at
  `https://imangulova.github.io/<repo>/`. (The unauthenticated `/pages` REST API
  can return 404 even when the site is live — check the actual URL for 200.)
- **`.gitignore`**: `node_modules`, `app/build`, `app/.svelte-kit`, `.wrangler/`,
  `__pycache__/`, and **any third-party source assets** (Train Tracks git-ignores
  `sources/` — the Krazydad reference PDFs; do NOT republish them).
- **CREDITS.md**: independent build; credit the concept/reference sources without
  bundling their content.

Reference commit history in `train_tracks/`: game → stats → configure-pages fix →
weekday+percentile.

---

## 7. Gotchas checklist (all already paid for once)

- [ ] `export PATH="$HOME/.local/node/bin:$PATH"` before every npm/wrangler.
- [ ] Generator output must pass `verify_days.py` (unique + no-guess) — no
      exceptions.
- [ ] Logic solver: set positive forced facts before blanket negatives.
- [ ] Canvas: DPR scaling + `touch-action:none` + `preventDefault` on
      contextmenu + `setPointerCapture`.
- [ ] Stats beacons: `text/plain` content-type (not JSON).
- [ ] Gitignore `.wrangler/` and third-party assets; scrub if committed.
- [ ] Don't curl the workers.dev domain (guard); use wrangler/app.
- [ ] Pages: `actions/configure-pages@v5 { enablement: true }` in the workflow.
- [ ] Assistant commits locally; **user pushes**; no tokens in chat.
- [ ] Preserve already-released days when regenerating.

---

## 8. Applying this to BATTLESHIPS (Bimaru / Solitaire Battleships)

**Rules.** An N×N grid hides a fixed **fleet** of ships (straight, length 1..k).
Ships **never touch, not even diagonally**. Row/column clues = number of ship
segments in that row/col. The fleet composition is known. A few cells may be
pre-revealed (water, or a specific ship part: single, end ▲▶▼◀, or middle ■).
**Unique solution, solvable without guessing** — same guarantees as Train Tracks.

**Fleet (scale by grid size).** Classic 10×10 = 1×(len4) + 2×(len3) + 3×(len2) +
4×(len1). Scale down for smaller daily grids, e.g. 6×6 ~ {3,2,2,1,1}, 8×8 ~
{4,3,2,2,1,1}. Decide a per-tier grid/fleet table (mirror Train Tracks' weekday
ramp).

**Data blob.** `{rows, cols, tier, rowClues, colClues, fleet:[lengths...],
givens:[[r,c,type]], solution:[[r,c,type]]}` where `type ∈
{water, single, end-N/E/S/W, mid}` (or store the fleet as a grid of ship-ids and
derive part types for rendering).

**Generator (§2 analogue).**
1. Random legal placement of the fleet: for each ship (largest first) pick random
   cell+orientation; reject if it overlaps or **touches** any placed ship
   (check the 8-neighbourhood). Backtrack/resample if stuck.
2. Clues = per-row/col segment counts (fleet composition is a fixed clue).
3. Reveal minimum givens until the **logic solver** solves it; cross-check
   uniqueness with backtracking. Seeded RNG per day; preserve released days.

**Logic solver rules (sound; Bimaru techniques).** Cell states
`{UNKNOWN, WATER, SHIP}` (+ part type once determined):
- **No-touch**: every cell diagonally adjacent to a SHIP is WATER; cells around a
  completed ship's perimeter are WATER.
- **Clue saturation** (rows & cols): ship-count==clue ⇒ rest WATER;
  ship+unknown==clue ⇒ rest SHIP.
- **Part inference**: a SHIP cell with WATER/border on 3 sides is a `single` or an
  `end` pointing to its only ship-neighbour; a SHIP with ship-neighbours on
  opposite sides is a `mid`; ends fix orientation ⇒ neighbour in that direction is
  SHIP, perpendicular neighbours are WATER.
- **Fleet accounting**: once all ships of a length are placed, no remaining
  segment run may have that length; the largest unplaced ship constrains where
  long runs can still go.
- Contradiction on conflict; `solved()` when every cell is WATER/SHIP with a
  consistent part type and the fleet composition matches.
Backtracking solver: assign cells water/ship with the same prunes + a final
"fleet composition matches exactly & no two ships touch" validation, count to 2.

**UI (§3 analogue).** Canvas grid. **Left-click cycles a cell** UNKNOWN→SHIP→WATER
(or drag to paint SHIP), **right-click = WATER** (the "empty"/sea marker). Mobile:
drag + Ship/Water mode toggle + long-press for the secondary. Render ship parts
by inferring shape from ship-neighbours (single circle, rounded end pointing at
the neighbour, square middle); water as a dot/·. Row/col clues green/red like
Train Tracks; show remaining fleet with checkmarks as ships are completed.
**Win-check** = player's ship cells == solution ship cells (unique).

**Everything else is identical**: same platform fork, same `verify_days.py` gate
(swap in the battleships solvers), same stats backend (new `id` = `battleships`,
new D1 `battleships-stats`), same weekday ramp + preserve, same git/Pages/CREDITS
flow. Reference `~/Desktop/train_tracks/scripts/{gen_days,verify_days,preview_day}.py`
and `GameComponent.svelte` and adapt the rules.

**Credit** the concept as *Battleships / Bimaru* (traditional; popularised by
various publishers); independent build, no third-party puzzle content bundled.
