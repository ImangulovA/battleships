-- Global-stats schema for daily_github_game. One D1 database per fork (or share
-- one DB across forks — the `game` column namespaces every row).

-- Idempotency log: one row per (game, client, day, kind). Used to dedupe so a
-- client double-posting (retry, backfill) never inflates the aggregates.
CREATE TABLE IF NOT EXISTS events (
  game      TEXT NOT NULL,
  client_id TEXT NOT NULL,
  day       INTEGER NOT NULL,
  kind      TEXT NOT NULL,        -- 'start' | 'finish'
  ts        INTEGER NOT NULL,     -- epoch ms (client-supplied; informational)
  PRIMARY KEY (game, client_id, day, kind)
);

-- Rolled-up counters per (game, day). Updated transactionally as events land.
CREATE TABLE IF NOT EXISTS day_stats (
  game          TEXT NOT NULL,
  day           INTEGER NOT NULL,
  started       INTEGER NOT NULL DEFAULT 0,
  finished      INTEGER NOT NULL DEFAULT 0,
  total_ms      INTEGER NOT NULL DEFAULT 0,  -- sum of finish times
  total_score   INTEGER NOT NULL DEFAULT 0,  -- sum of finish scores
  scored_count  INTEGER NOT NULL DEFAULT 0,  -- # finishes that carried a score
  PRIMARY KEY (game, day)
);

-- Individual finish times: one row per (game, day, client). Powers the time
-- distribution used for percentile tiers ("faster than N% of solvers").
CREATE TABLE IF NOT EXISTS finish_times (
  game      TEXT NOT NULL,
  day       INTEGER NOT NULL,
  client_id TEXT NOT NULL,
  ms        INTEGER NOT NULL,
  PRIMARY KEY (game, day, client_id)
);
CREATE INDEX IF NOT EXISTS idx_finish_times_game_day ON finish_times (game, day);
