// ---------------------------------------------------------------------------
// Per-fork configuration. Edit this file when you spin up a new daily game.
// ---------------------------------------------------------------------------

// URL of the global-stats Worker (see ../../backend/README.md). Leave '' to run
// LOCAL-ONLY: every network call no-ops and nothing breaks. After
// `wrangler deploy`, paste the printed workers.dev URL here and redeploy.
export const STATS_API = 'https://battleships-stats.ru-catfishing.workers.dev';

// Password that unlocks playing FUTURE (not-yet-released) days early. Share a
// link like `?unlock=<this>&day=N` and the visitor can play ahead; the flag
// persists in localStorage. NOTE: OBFUSCATION, not security — future days ship
// in the static bundle, so a source-diver can still spoil them. Set to '' to
// disable the author-mode gate entirely.
export const UNLOCK_PASSWORD = 'flagship';
