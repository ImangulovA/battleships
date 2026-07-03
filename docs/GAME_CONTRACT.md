# The platform ↔ game contract

The platform handles routing, the timer, persistence, the backend, the archive,
the stats page and the share loop. Your game plugs in through **one config
object** and **one component with three callbacks**. Nothing else couples them.

## 1. `GAME` config — `app/src/lib/game/index.js`

```js
export const GAME = {
  id: 'lights-out',            // storage + backend namespace. Unique & STABLE.
  title: 'Daily Lights Out',   // header / share / <title>
  tagline: '…',                // intro screen subtitle
  anchorDate: [2026, 5, 8],    // day 0 = [year, monthIndex(0-11), day]

  component: GameComponent,    // your Svelte puzzle component

  dayIndexes() { return [/* day indexes that have data */]; },
  loadDay(idx) { return /* puzzle blob */ || null; },

  // optional. Higher = better (return -moves, -mistakes for lower-is-better).
  // null => unscored: stats track only time + completion.
  scoreOf(result) { return null; },

  // one or more lines for the share sheet. Keep it spoiler-free.
  shareLine(result, dayIdx, url) { return `${this.title} #${dayIdx}\n${url}`; }
};
```

Rules:

- **`id` must never change** after launch — it namespaces every player's saved
  progress and every backend row. Changing it orphans all of it.
- `anchorDate` fixes the numbering. Day N is `anchorDate + N` calendar days.
  Build days **ahead** of today; if today's index has no data the platform
  gracefully falls back to the latest available day.
- `dayIndexes()` may include **negative** indexes (a pre-anchor day is handy for
  a private pre-launch test).

## 2. Component contract — `app/src/lib/game/GameComponent.svelte`

Props in:

| prop     | meaning                                                        |
| -------- | ------------------------------------------------------------- |
| `puzzle` | the day's data, exactly what `GAME.loadDay(dayIdx)` returned  |
| `dayIdx` | the day index being played                                    |
| `saved`  | the previously stored `state` blob (for resume), or `null`    |

Callbacks out (passed as props — call them, don't dispatch events):

| callback             | when to call                                                                 |
| -------------------- | --------------------------------------------------------------------------- |
| `onstart()`          | **once**, on the first real interaction. Starts the timer + `/start` event. |
| `onprogress(state)`  | whenever resumable state changes. `state` is any JSON-serializable blob; you get it back as `saved` next visit. |
| `onfinish(result)`   | **once**, when the game is over. `result` is your blob; the platform attaches `ms` (active time) before storing/sharing. |

Minimal skeleton:

```svelte
<script>
  let { puzzle, dayIdx, saved = null, onstart, onprogress, onfinish } = $props();
  let started = false;
  function move() {
    if (!started) { started = true; onstart?.(); }
    // …mutate state…
    onprogress?.({ /* serializable */ });
    if (/* solved */) onfinish?.({ won: true, /* your fields */ });
  }
</script>
```

## 3. What the platform stores

Per day, in `localStorage["<GAME.id>_day<N>"]`:

```
{ started, finished, startedAt, finishedAt, elapsedMs, live, state, result }
```

- `state` = your last `onprogress` blob (resume).
- `result` = your `onfinish` blob **plus** `ms` (the platform merges active time).
- `live` = whether it was played on the puzzle's own date (used for stats).

The platform never reads inside `state`/`result` except through `GAME.scoreOf`
and `GAME.shareLine`. That's what keeps it game-agnostic.

## 4. Styling

Keep these CSS variables available to your component (defined in
`routes/+layout.svelte`): `--accent`, `--surface-2`, `--border`, `--shadow`,
`--mono`, `--muted`, `--ink`. Restyle the layout however you like otherwise.

## 5. Checklist for a new fork

- [ ] `config.js`: set `STATS_API` (or leave '' for local-only) and `UNLOCK_PASSWORD`.
- [ ] `GAME.id`, `title`, `tagline`, `anchorDate`.
- [ ] Replace `data/` + `dayIndexes()` / `loadDay()`.
- [ ] Replace `GameComponent.svelte`, wiring the three callbacks.
- [ ] Decide `scoreOf` (or return null) and write `shareLine`.
- [ ] `npm run build` passes; play locally.
- [ ] (Optional) deploy `backend/`, set `STATS_API`.
