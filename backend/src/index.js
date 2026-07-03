// ===========================================================================
// daily_github_game — global-stats Worker. Records two lifecycle events per
// player-day (start, finish) and serves cross-player aggregates. Stateless,
// CORS-guarded, idempotent. One D1 binding `DB`.
//
// Routes:
//   POST /start   { game, day, clientId }
//   POST /finish  { game, day, clientId, ms, score? }
//   GET  /agg?game=<id>&days=1,2,3
//
// Bodies are parsed as JSON regardless of Content-Type (clients send text/plain
// so navigator.sendBeacon stays a CORS "simple request" — see app api.js).
// ===========================================================================

const DAY_MIN = -100;
const DAY_MAX = 100000;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin') || '';
    const cors = corsHeaders(origin, env);

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });

    try {
      if (request.method === 'POST' && url.pathname === '/start') {
        return await handleEvent(request, env, cors, 'start');
      }
      if (request.method === 'POST' && url.pathname === '/finish') {
        return await handleEvent(request, env, cors, 'finish');
      }
      if (request.method === 'GET' && url.pathname === '/agg') {
        return await handleAgg(url, env, cors);
      }
      if (url.pathname === '/') {
        return json({ ok: true, service: 'daily_github_game stats' }, 200, cors);
      }
      return json({ ok: false, error: 'not found' }, 404, cors);
    } catch (e) {
      return json({ ok: false, error: String(e) }, 500, cors);
    }
  }
};

function corsHeaders(origin, env) {
  const allowed = (env.ALLOWED_ORIGINS || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const allow = allowed.length === 0 || allowed.includes(origin) ? origin || '*' : allowed[0];
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
  };
}

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json', ...cors }
  });
}

async function readBody(request) {
  const text = await request.text();
  try {
    return JSON.parse(text);
  } catch (e) {
    return {};
  }
}

function validDay(d) {
  return Number.isInteger(d) && d >= DAY_MIN && d <= DAY_MAX;
}

async function handleEvent(request, env, cors, kind) {
  const body = await readBody(request);
  const game = String(body.game || '').slice(0, 64);
  const day = Number(body.day);
  const clientId = String(body.clientId || '').slice(0, 64);
  if (!game || !clientId || !validDay(day)) {
    return json({ ok: false, error: 'bad request' }, 400, cors);
  }

  // Idempotent insert: if this (game, client, day, kind) already exists, the
  // INSERT is ignored and we skip the counter bump.
  const ins = await env.DB.prepare(
    'INSERT OR IGNORE INTO events (game, client_id, day, kind, ts) VALUES (?, ?, ?, ?, ?)'
  )
    .bind(game, clientId, day, kind, Date.now())
    .run();

  const isNew = ins.meta && ins.meta.changes > 0;
  if (!isNew) return json({ ok: true, deduped: true }, 200, cors);

  // Ensure the day_stats row exists, then bump the relevant counters.
  await env.DB.prepare(
    'INSERT OR IGNORE INTO day_stats (game, day) VALUES (?, ?)'
  )
    .bind(game, day)
    .run();

  if (kind === 'start') {
    await env.DB.prepare('UPDATE day_stats SET started = started + 1 WHERE game = ? AND day = ?')
      .bind(game, day)
      .run();
  } else {
    const ms = Number.isFinite(Number(body.ms)) ? Math.max(0, Math.round(Number(body.ms))) : 0;
    const hasScore = body.score !== null && body.score !== undefined && Number.isFinite(Number(body.score));
    const score = hasScore ? Math.round(Number(body.score)) : 0;
    await env.DB.prepare(
      `UPDATE day_stats
         SET finished = finished + 1,
             total_ms = total_ms + ?,
             total_score = total_score + ?,
             scored_count = scored_count + ?
       WHERE game = ? AND day = ?`
    )
      .bind(ms, score, hasScore ? 1 : 0, game, day)
      .run();

    // Record this solver's individual time (first solve counts) so aggregates
    // can return the time distribution for percentile tiers.
    await env.DB.prepare(
      'INSERT OR IGNORE INTO finish_times (game, day, client_id, ms) VALUES (?, ?, ?, ?)'
    )
      .bind(game, day, clientId, ms)
      .run();
  }

  return json({ ok: true }, 200, cors);
}

async function handleAgg(url, env, cors) {
  const game = String(url.searchParams.get('game') || '').slice(0, 64);
  if (!game) return json({ ok: false, error: 'missing game' }, 400, cors);

  const daysParam = (url.searchParams.get('days') || '').trim();
  const days = daysParam
    ? daysParam.split(',').map((x) => Number(x)).filter((n) => validDay(n))
    : [];

  let rows;
  if (days.length) {
    const placeholders = days.map(() => '?').join(',');
    rows = await env.DB.prepare(
      `SELECT day, started, finished, total_ms, total_score, scored_count
         FROM day_stats WHERE game = ? AND day IN (${placeholders})`
    )
      .bind(game, ...days)
      .all();
  } else {
    rows = await env.DB.prepare(
      `SELECT day, started, finished, total_ms, total_score, scored_count
         FROM day_stats WHERE game = ?`
    )
      .bind(game)
      .all();
  }

  const agg = {};
  for (const r of rows.results || []) {
    agg[r.day] = {
      started: r.started,
      finished: r.finished,
      finishRate: r.started ? r.finished / r.started : 0,
      avgMs: r.finished ? Math.round(r.total_ms / r.finished) : 0,
      avgScore: r.scored_count ? r.total_score / r.scored_count : null,
      times: []
    };
  }

  // Attach the sorted per-day time distribution so clients can compute a
  // percentile tier ("faster than N% of solvers").
  let timeRows;
  if (days.length) {
    const ph = days.map(() => '?').join(',');
    timeRows = await env.DB.prepare(
      `SELECT day, ms FROM finish_times WHERE game = ? AND day IN (${ph}) ORDER BY ms ASC`
    )
      .bind(game, ...days)
      .all();
  } else {
    timeRows = await env.DB.prepare(
      'SELECT day, ms FROM finish_times WHERE game = ? ORDER BY ms ASC'
    )
      .bind(game)
      .all();
  }
  for (const r of timeRows.results || []) {
    if (!agg[r.day]) {
      agg[r.day] = { started: 0, finished: 0, finishRate: 0, avgMs: 0, avgScore: null, times: [] };
    }
    agg[r.day].times.push(r.ms);
  }

  return json({ ok: true, agg }, 200, cors);
}
