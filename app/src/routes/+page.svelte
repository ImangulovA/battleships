<script>
  // ===========================================================================
  // GAME SHELL — PLATFORM code. Loads the right day, owns the timer, persistence,
  // backend events, the end screen and the share loop. The actual puzzle is the
  // pluggable <GAME.component>. You should rarely need to touch this per fork.
  // ===========================================================================
  import { onMount, onDestroy } from 'svelte';
  import { base } from '$app/paths';
  import { GAME } from '$lib/game/index.js';
  import { resolveDay, todayIndex, fmtDate, msUntilLocalMidnight } from '$lib/platform/days.js';
  import { loadDay as loadRecord, saveDay } from '$lib/platform/storage.js';
  import { makeTimer, fmtTime } from '$lib/platform/timer.js';
  import { submitStart, submitFinish, fetchAgg, statsEnabled } from '$lib/platform/api.js';
  import { applyUnlockFromUrl, isUnlocked } from '$lib/platform/unlock.js';

  let dayIdx = $state(0);
  let puzzle = $state(null);
  let record = $state(null);
  let view = $state('loading'); // loading | intro | play | end | empty
  let isFuture = $state(false);
  let agg = $state(null); // global cross-player numbers for this day
  let untilMidnight = $state('');

  let timer = null;
  let tick = null;

  onMount(() => {
    const unlocked = applyUnlockFromUrl();
    const requested = new URLSearchParams(location.search).get('day');
    dayIdx = resolveDay(requested, new Date(), unlocked);
    puzzle = GAME.loadDay(dayIdx);
    if (!puzzle) {
      view = 'empty';
      return;
    }
    isFuture = dayIdx > todayIndex();
    record = loadRecord(dayIdx);

    timer = makeTimer(record.elapsedMs || 0);

    if (record.finished) {
      view = 'end';
      // Backfill stats for a day finished before the event was recorded (dropped
      // request, or the global backend didn't exist yet). once() + server-side
      // dedup by clientId make these idempotent, so re-sending is safe. Read the
      // aggregates only after the finish is confirmed, so a recovered (earlier
      // lost) solve is reflected in the counts.
      submitStart(dayIdx);
      Promise.resolve(
        submitFinish(dayIdx, record.elapsedMs || 0, GAME.scoreOf ? GAME.scoreOf(record.result) : null)
      ).then(() => loadAgg({ settle: true }));
    } else if (record.started) {
      // Backfill a possibly-missed start beacon for an in-progress day.
      submitStart(dayIdx);
      timer.start();
      view = 'play';
    } else {
      view = 'intro';
    }

    // Tick every second: the countdown shows seconds, so a 30s interval made it
    // look frozen.
    tick = setInterval(() => {
      untilMidnight = fmtTime(msUntilLocalMidnight());
    }, 1000);
    untilMidnight = fmtTime(msUntilLocalMidnight());
  });

  onDestroy(() => {
    timer?.destroy();
    if (tick) clearInterval(tick);
  });

  function persist() {
    saveDay(dayIdx, record);
  }

  function beginPlay() {
    view = 'play';
  }

  // --- callbacks handed to the game component -------------------------------
  function handleStart() {
    if (!record.started) {
      record.started = true;
      record.startedAt = Date.now();
      record.live = dayIdx === todayIndex();
      timer.start();
      persist();
      submitStart(dayIdx);
    }
  }

  function handleProgress(state) {
    record.state = state;
    record.elapsedMs = timer.elapsed();
    persist();
  }

  async function handleFinish(result) {
    const ms = timer.stop();
    record.finished = true;
    record.finishedAt = Date.now();
    record.elapsedMs = ms;
    record.result = { ...result, ms };
    persist();
    view = 'end';
    // Wait for the finish to be recorded before reading aggregates, so the end
    // screen counts our own solve. (settle: true adds a short buffer on top, in
    // case D1's read-after-write lags slightly behind the write ack.)
    await submitFinish(dayIdx, ms, GAME.scoreOf ? GAME.scoreOf(record.result) : null);
    loadAgg({ settle: true });
  }

  // --- end screen -----------------------------------------------------------
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function loadAgg({ settle = false } = {}) {
    if (!statsEnabled()) return;
    agg = await fetchAgg([dayIdx]);
    if (settle) {
      // Give a just-submitted finish a moment to become visible, then refresh
      // so our own solve is reflected in the counts and time distribution.
      await sleep(1200);
      const fresh = await fetchAgg([dayIdx]);
      if (fresh) agg = fresh;
    }
  }

  function dayAgg() {
    return agg?.agg?.[dayIdx] || null;
  }

  // Percentile tier from the cross-player time distribution: how the player's
  // time compares to everyone else who solved this day. `times` may or may not
  // already include the player's own time (finish beacon race), so we drop one
  // matching entry before ranking.
  function speedTier() {
    if (!record.result?.won) return null;
    const my = record.result?.ms;
    if (my == null) return null;
    const times = (dayAgg()?.times || []).slice();
    const i = times.indexOf(my);
    if (i >= 0) times.splice(i, 1);
    if (times.length === 0) return { label: '🥇 First to solve!', pctFaster: null };
    const slower = times.filter((t) => t > my).length;
    const pctFaster = Math.round((100 * slower) / times.length);
    let label;
    if (pctFaster >= 90) label = '🥇 Top 10%';
    else if (pctFaster >= 75) label = '🥈 Top 25%';
    else if (pctFaster >= 50) label = '🥉 Faster than half';
    else label = '🚢 Finished';
    return { label, pctFaster };
  }

  function shareText() {
    const url = `${location.origin}${base}/`;
    return GAME.shareLine(record.result, dayIdx, url);
  }

  let shared = $state('');
  let showBoard = $state(false); // end screen: reveal the solved board

  // Last-resort copy for desktop browsers without navigator.share and without a
  // secure-context clipboard (http/file://, older browsers). Uses a hidden
  // textarea + execCommand('copy'), which works from a user gesture almost
  // everywhere.
  function legacyCopy(text) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.top = '-1000px';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      ta.setSelectionRange(0, text.length);
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    } catch (e) {
      return false;
    }
  }

  function flashCopied() {
    shared = 'Copied!';
    setTimeout(() => (shared = ''), 2000);
  }

  async function share() {
    const text = shareText();

    // Native share sheet (mainly mobile, some desktop browsers).
    if (navigator.share) {
      try {
        await navigator.share({ text });
        shared = '';
        return;
      } catch (e) {
        // User cancelled the share sheet on purpose — do nothing, don't copy.
        if (e && e.name === 'AbortError') return;
        // Any other failure: fall through to clipboard copy below.
      }
    }

    // Secure-context clipboard API.
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        flashCopied();
        return;
      } catch (e) {
        /* fall through to legacy copy */
      }
    }

    // Last resort for http/file:// and older desktop browsers.
    if (legacyCopy(text)) {
      flashCopied();
    } else {
      shared = 'Copy failed';
    }
  }

  const pct = (x) => Math.round((x || 0) * 100);
</script>

{#if view === 'loading'}
  <p class="status">Loading…</p>
{:else if view === 'empty'}
  <div class="card">
    <h1>No puzzle for this day</h1>
    <p class="muted">This day isn't available yet. <a href="{base}/archive">Open the archive →</a></p>
  </div>
{:else}
  <div class="daybar">
    <span class="daychip" class:future={isFuture}>
      #{dayIdx} · {fmtDate(dayIdx)}{#if isFuture} · preview{/if}
    </span>
  </div>

  {#if view === 'intro'}
    <div class="card intro">
      <h1>{GAME.title}</h1>
      <p class="muted">{GAME.tagline}</p>
      {#if isFuture}<p class="future-note">🔓 Author mode: future day</p>{/if}
      <button class="primary" onclick={beginPlay}>Play</button>
    </div>
  {/if}

  {#if view === 'play'}
    <div class="card">
      <GAME.component
        {puzzle}
        {dayIdx}
        saved={record.state}
        onstart={handleStart}
        onprogress={handleProgress}
        onfinish={handleFinish}
      />
    </div>
  {/if}

  {#if view === 'end'}
    <div class="card end">
      <h1>{record.result?.won ? '🚢 Solved!' : 'Game over'}</h1>
      <div class="bigstats">
        <div><span class="num">{record.result?.size ?? '—'}</span><span class="lbl">grid</span></div>
        <div><span class="num">{fmtTime(record.elapsedMs)}</span><span class="lbl">time</span></div>
        {#if record.result?.won && GAME.scoreOf}
          {@const sc = GAME.scoreOf(record.result)}
          {#if sc != null}
            <div><span class="num score">{sc}</span><span class="lbl">score</span></div>
          {/if}
        {/if}
      </div>

      {#if record.result?.won && (record.result?.hintsUsed?.length ?? 0) === 0}
        <p class="perfect">✨ Perfect: no hints used!</p>
      {:else if record.result?.won && record.result?.hintsUsed?.length}
        <p class="hintline">
          {record.result.hintsUsed.length} hint{record.result.hintsUsed.length > 1 ? 's' : ''} used
          (−{record.result.hintsUsed.reduce((s, l) => s + l * l, 0)} pts)
        </p>
      {/if}

      {#if record.result?.won}
        {@const t = speedTier()}
        {#if t}
          <div class="tier">
            <span class="tier-badge">{t.label}</span>
            {#if t.pctFaster != null}
              <span class="tier-sub">Faster than {t.pctFaster}% of players</span>
            {/if}
          </div>
        {/if}
      {/if}

      {#if dayAgg()}
        <div class="global">
          <h2>All players</h2>
          <div class="grow">
            <div><span class="num">{dayAgg().started}</span><span class="lbl">started</span></div>
            <div><span class="num">{dayAgg().finished}</span><span class="lbl">finished</span></div>
          </div>
        </div>
      {/if}

      <div class="actions">
        <button class="primary" onclick={share}>Share</button>
        {#if record?.result?.won && record?.state}
          <button class="ghost" onclick={() => (showBoard = !showBoard)}>
            {showBoard ? 'Hide board' : 'View board'}
          </button>
        {/if}
        <a class="ghost" href="{base}/stats">All stats →</a>
      </div>
      {#if shared}<p class="copied">{shared}</p>{/if}

      {#if showBoard && record?.state}
        <div class="solvedboard">
          <GAME.component
            {puzzle}
            {dayIdx}
            saved={{ ...record.state, done: true }}
            onstart={() => {}}
            onprogress={() => {}}
            onfinish={() => {}}
          />
        </div>
      {/if}

      <p class="nextgame">Next puzzle in {untilMidnight}</p>
    </div>
  {/if}
{/if}

<style>
  .status {
    text-align: center;
    color: var(--muted);
    margin-top: 40px;
  }
  .daybar {
    display: flex;
    justify-content: center;
    margin-bottom: 12px;
  }
  .daychip {
    font-family: var(--mono);
    font-size: 13px;
    border: var(--border);
    background: var(--surface);
    box-shadow: var(--shadow);
    border-radius: 999px;
    padding: 4px 12px;
  }
  .daychip.future {
    border-style: dashed;
    color: var(--accent-2);
  }
  .card {
    background: var(--surface);
    border: var(--border);
    box-shadow: var(--shadow);
    border-radius: 14px;
    padding: 22px;
  }
  .intro,
  .end {
    text-align: center;
  }
  h1 {
    margin: 0 0 8px;
    font-size: 26px;
  }
  h2 {
    font-size: 16px;
    margin: 0 0 10px;
  }
  .muted {
    color: var(--muted);
  }
  .future-note {
    color: var(--accent-2);
    font-weight: 600;
  }
  .primary {
    border: var(--border);
    background: var(--accent);
    color: #111;
    box-shadow: var(--shadow);
    border-radius: 10px;
    padding: 10px 22px;
    font-weight: 800;
    font-size: 16px;
    cursor: pointer;
  }
  .primary:active {
    transform: translate(2px, 2px);
    box-shadow: none;
  }
  .ghost {
    color: var(--ink);
    font-weight: 600;
    text-decoration: none;
    font-size: 15px;
  }
  .ghost:hover {
    text-decoration: underline;
  }
  .bigstats,
  .grow {
    display: flex;
    justify-content: center;
    gap: 26px;
    margin: 16px 0;
  }
  .bigstats div,
  .grow div {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .num {
    font-family: var(--mono);
    font-size: 28px;
    font-weight: 700;
  }
  .grow .num {
    font-size: 22px;
  }
  .num.score {
    color: var(--accent-2);
  }
  .perfect {
    color: var(--accent-2);
    font-weight: 700;
    font-size: 14px;
    margin: 0;
  }
  .hintline {
    color: var(--muted);
    font-size: 13px;
    margin: 0;
  }
  .lbl {
    color: var(--muted);
    font-size: 12px;
  }
  .tier {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    margin: 6px 0 4px;
  }
  .tier-badge {
    font-size: 20px;
    font-weight: 800;
    color: var(--accent);
  }
  .tier-sub {
    color: var(--muted);
    font-size: 13px;
  }
  .global {
    border-top: var(--border);
    margin-top: 16px;
    padding-top: 14px;
  }
  .actions {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 18px;
    margin-top: 18px;
  }
  .copied {
    color: var(--good);
    font-size: 14px;
    margin: 8px 0 0;
  }
  .solvedboard {
    margin-top: 18px;
    padding-top: 16px;
    border-top: var(--border);
  }
  .nextgame {
    color: var(--muted);
    font-family: var(--mono);
    font-size: 13px;
    margin: 16px 0 0;
  }
</style>
