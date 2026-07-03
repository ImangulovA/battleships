# Global-stats backend (Cloudflare Worker + D1)

Records two lifecycle events per player-day and serves cross-player aggregates
(% started, % finished, average time, optional average score). Entirely optional:
with no backend the app runs local-only and every network call no-ops.

## Deploy

```bash
cd backend
npm i -g wrangler            # if needed
wrangler login

# 1. create the database, paste the printed id into wrangler.toml -> database_id
wrangler d1 create daily-game-stats

# 2. apply the schema to the remote DB
wrangler d1 execute daily-game-stats --remote --file=./schema.sql

# 3. set ALLOWED_ORIGINS in wrangler.toml (your Pages origin + localhost), then
wrangler deploy
```

`wrangler deploy` prints a URL like
`https://daily-game-stats.<you>.workers.dev`. Paste it into
`app/src/lib/config.js` -> `STATS_API` and redeploy the app. Done.

## API

| Method | Path                          | Body / query                              |
| ------ | ----------------------------- | ----------------------------------------- |
| POST   | `/start`                      | `{ game, day, clientId }`                 |
| POST   | `/finish`                     | `{ game, day, clientId, ms, score? }`     |
| GET    | `/agg?game=<id>&days=1,2,3`   | (days optional — omit for all days)       |

`/agg` returns `{ ok, agg: { [day]: { started, finished, finishRate, avgMs, avgScore } } }`.

Notes:
- Events are idempotent per `(game, clientId, day, kind)`, so retries/backfills
  never double-count.
- The `game` column namespaces rows, so one DB can serve several forks if you
  reuse it; or give each fork its own DB. Keep `GAME.id` unique per fork.
- Bodies arrive as `text/plain` (so `navigator.sendBeacon` avoids a CORS
  preflight); the Worker JSON-parses regardless of Content-Type.
- Raw guesses / per-move data never leave the browser — only counts and times.
