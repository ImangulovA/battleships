<script>
  // ===========================================================================
  // DAILY BATTLESHIPS (Bimaru) — puzzle UI.
  //
  // Find the hidden fleet. Ships are straight, never touch (not even at a
  // corner). The numbers on the top/right count how many ship segments sit in
  // that column/row. The fleet composition is shown below the board. Unique
  // solution, solvable by pure logic — no guessing.
  //
  // INPUT
  //   Desktop: left-click a cell cycles  empty → ship → water → empty.
  //            left-drag paints ship · right-click / right-drag paints water.
  //   Mobile : pick a tool (🚢 Ship / 🌊 Water), then drag to paint;
  //            long-press a cell for a quick water mark.
  //
  // CONTRACT (see docs/GAME_CONTRACT.md): props puzzle/dayIdx/saved; callbacks
  // onstart() once, onprogress(state) on change, onfinish(result) once.
  // ===========================================================================
  import { onMount } from 'svelte';

  let { puzzle, dayIdx, saved = null, onstart, onprogress, onfinish } = $props();

  const R = puzzle.rows;
  const C = puzzle.cols;
  const key = (r, c) => `${r},${c}`;
  const inGrid = (r, c) => r >= 0 && r < R && c >= 0 && c < C;

  // --- givens (locked) ------------------------------------------------------
  const givenShip = new Set();
  const givenWater = new Set();
  for (const [r, c, t] of puzzle.givens) {
    if (t === 'water') givenWater.add(key(r, c));
    else givenShip.add(key(r, c));
  }
  const solutionShips = new Set(puzzle.solution.map(([r, c]) => key(r, c)));

  // --- mutable player state -------------------------------------------------
  let ship = new Set(saved?.ship ?? []); // player-marked ship cells
  let water = new Set(saved?.water ?? []); // player-marked water cells
  let mode = $state('ship'); // mobile tool: 'ship' | 'water'
  let done = $state(saved?.done ?? false);
  let rowCount = $state(new Array(R).fill(0));
  let colCount = $state(new Array(C).fill(0));
  let fleetState = $state([]); // [{len, done}] for the fleet tray
  let canUndo = $state(false);
  let history = [];
  let startedOnce = false;

  // effective state of a cell, givens included
  const isShip = (r, c) => givenShip.has(key(r, c)) || ship.has(key(r, c));
  const isWater = (r, c) => givenWater.has(key(r, c)) || water.has(key(r, c));
  const isLocked = (r, c) => givenShip.has(key(r, c)) || givenWater.has(key(r, c));

  // --- geometry -------------------------------------------------------------
  let wrap, canvas, ctx;
  let cell = 40;
  let originX = 0;
  let originY = 0;
  let accent = '#fdc800';

  function layout(cssW) {
    cell = Math.max(28, Math.min(60, Math.floor(cssW / (C + 1.6))));
    originX = Math.round(cell * 0.2);
    originY = Math.round(cell * 0.95);
    const w = originX + C * cell + Math.round(cell * 1.4);
    const h = originY + R * cell + Math.round(cell * 0.2);
    return { w, h };
  }

  function fit() {
    if (!wrap || !canvas) return;
    const cssW = Math.min(wrap.clientWidth, 560);
    const { w, h } = layout(cssW);
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    accent = cssVar('--accent', '#fdc800');
    draw();
  }

  // --- derived --------------------------------------------------------------
  function recount() {
    const rc = new Array(R).fill(0);
    const cc = new Array(C).fill(0);
    for (let r = 0; r < R; r++)
      for (let c = 0; c < C; c++)
        if (isShip(r, c)) {
          rc[r]++;
          cc[c]++;
        }
    rowCount = rc;
    colCount = cc;
    computeFleet();
  }

  // Confirmed ships = orthogonal runs of ship cells whose every orthogonal
  // neighbour is water or the border (i.e. the ship is fully boxed in). Tick
  // those off against the required fleet.
  function computeFleet() {
    const seen = new Set();
    const lens = [];
    for (let r = 0; r < R; r++)
      for (let c = 0; c < C; c++) {
        if (!isShip(r, c) || seen.has(key(r, c))) continue;
        const stack = [[r, c]];
        seen.add(key(r, c));
        const comp = [];
        let boxed = true;
        while (stack.length) {
          const [cr, cc] = stack.pop();
          comp.push([cr, cc]);
          for (const [dr, dc] of [
            [-1, 0],
            [1, 0],
            [0, -1],
            [0, 1]
          ]) {
            const nr = cr + dr,
              nc = cc + dc;
            if (!inGrid(nr, nc)) continue;
            if (isShip(nr, nc)) {
              if (!seen.has(key(nr, nc))) {
                seen.add(key(nr, nc));
                stack.push([nr, nc]);
              }
            } else if (!isWater(nr, nc)) {
              boxed = false; // an unknown neighbour — ship not confirmed yet
            }
          }
        }
        if (boxed) lens.push(comp.length);
      }
    // Build the tray: fleet lengths (desc), each ticked if a confirmed ship of
    // that length is still unclaimed.
    const pool = lens.slice();
    fleetState = puzzle.fleet.map((len) => {
      const i = pool.indexOf(len);
      if (i >= 0) {
        pool.splice(i, 1);
        return { len, done: true };
      }
      return { len, done: false };
    });
  }

  function isWin() {
    let all = new Set(givenShip);
    for (const k of ship) all.add(k);
    if (all.size !== solutionShips.size) return false;
    for (const k of all) if (!solutionShips.has(k)) return false;
    return true;
  }

  // --- mutation -------------------------------------------------------------
  function firstTouch() {
    if (!startedOnce) {
      startedOnce = true;
      onstart?.();
    }
  }

  function pushHistory() {
    history.push({ ship: new Set(ship), water: new Set(water) });
    if (history.length > 200) history.shift();
    canUndo = true;
  }

  function commit() {
    recount();
    onprogress?.({ ship: [...ship], water: [...water], done });
    if (!done && isWin()) {
      done = true;
      onfinish?.({ won: true, tier: puzzle.tier, size: `${R}×${C}`, fleet: puzzle.fleet });
    }
    draw();
  }

  // target ∈ 'ship' | 'water' | 'empty'
  function setCell(r, c, target) {
    if (isLocked(r, c)) return;
    const k = key(r, c);
    ship.delete(k);
    water.delete(k);
    if (target === 'ship') ship.add(k);
    else if (target === 'water') water.add(k);
  }

  function cycle(r, c) {
    if (isLocked(r, c)) return;
    const k = key(r, c);
    if (ship.has(k)) setCell(r, c, 'water');
    else if (water.has(k)) setCell(r, c, 'empty');
    else setCell(r, c, 'ship');
  }

  // --- pointer handling -----------------------------------------------------
  let dragging = false;
  let dragTool = 'ship';
  let strokeTarget = 'ship'; // what a drag paints
  let strokeDecided = false;
  let lastCell = null;
  let moved = false;
  let longTimer = null;

  function cellAt(evt) {
    const rect = canvas.getBoundingClientRect();
    const x = evt.clientX - rect.left - originX;
    const y = evt.clientY - rect.top - originY;
    const c = Math.floor(x / cell);
    const r = Math.floor(y / cell);
    if (!inGrid(r, c)) return null;
    return { r, c };
  }

  function onDown(evt) {
    if (done) return;
    const p = cellAt(evt);
    if (!p) return;
    evt.preventDefault();
    canvas.setPointerCapture?.(evt.pointerId);
    firstTouch();
    pushHistory();
    dragging = true;
    moved = false;
    strokeDecided = false;
    lastCell = p;
    dragTool = evt.button === 2 ? 'water' : mode;

    if (dragTool === 'water') {
      // paint water; erase if the first cell is already water
      strokeTarget = isWater(p.r, p.c) && !givenWater.has(key(p.r, p.c)) ? 'empty' : 'water';
      strokeDecided = true;
      setCell(p.r, p.c, strokeTarget);
      commit();
    } else {
      // ship tool: long-press => quick water mark (mobile)
      longTimer = setTimeout(() => {
        if (dragging && !moved) {
          setCell(p.r, p.c, isWater(p.r, p.c) ? 'empty' : 'water');
          commit();
          dragging = false;
        }
      }, 450);
    }
  }

  function onMove(evt) {
    if (!dragging) return;
    const p = cellAt(evt);
    if (!p) return;
    if (p.r !== lastCell.r || p.c !== lastCell.c) {
      moved = true;
      if (longTimer) {
        clearTimeout(longTimer);
        longTimer = null;
      }
    } else return;

    if (dragTool === 'ship' && !strokeDecided) {
      strokeTarget = isShip(p.r, p.c) && !givenShip.has(key(p.r, p.c)) ? 'empty' : 'ship';
      strokeDecided = true;
    }
    setCell(p.r, p.c, strokeTarget);
    lastCell = p;
    commit();
  }

  function onUp() {
    if (longTimer) {
      clearTimeout(longTimer);
      longTimer = null;
    }
    if (!dragging) return;
    dragging = false;
    if (!moved) {
      // a plain tap
      if (dragTool === 'ship') cycle(lastCell.r, lastCell.c);
      commit();
      // (water tap already applied on down)
    }
  }

  function undo() {
    if (!history.length) return;
    const snap = history.pop();
    ship = snap.ship;
    water = snap.water;
    done = false;
    canUndo = history.length > 0;
    commit();
  }

  function clearAll() {
    pushHistory();
    ship = new Set();
    water = new Set();
    done = false;
    commit();
  }

  // --- drawing --------------------------------------------------------------
  function cssVar(name, fallback) {
    const v = getComputedStyle(canvas).getPropertyValue(name).trim();
    return v || fallback;
  }

  function roundRect(x, y, w, h, r) {
    const rr = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
  }

  function draw() {
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.width / dpr;
    const h = canvas.height / dpr;
    ctx.clearRect(0, 0, w, h);

    const surface = cssVar('--surface-2', '#fff');
    const border = cssVar('--border-col', '#111');
    const muted = cssVar('--muted', '#94a3b8');
    const ink = cssVar('--ink', '#0f172a');
    const shipCol = cssVar('--ink', '#0f172a');
    const givenCol = cssVar('--accent-2', '#a855f7');
    const GREEN = cssVar('--good', '#16a34a');
    const RED = cssVar('--bad', '#e0404a');

    // grid background
    ctx.fillStyle = surface;
    ctx.fillRect(originX, originY, C * cell, R * cell);

    // grid lines
    ctx.strokeStyle = border;
    ctx.globalAlpha = 0.35;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let c = 0; c <= C; c++) {
      ctx.moveTo(originX + c * cell + 0.5, originY);
      ctx.lineTo(originX + c * cell + 0.5, originY + R * cell);
    }
    for (let r = 0; r <= R; r++) {
      ctx.moveTo(originX, originY + r * cell + 0.5);
      ctx.lineTo(originX + C * cell, originY + r * cell + 0.5);
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
    // outer frame heavier
    ctx.strokeStyle = ink;
    ctx.lineWidth = 2;
    ctx.strokeRect(originX + 0.5, originY + 0.5, C * cell, R * cell);

    // clues
    ctx.font = `700 ${Math.round(cell * 0.42)}px var(--mono, ui-monospace, monospace)`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let c = 0; c < C; c++) {
      const cur = colCount[c];
      const clue = puzzle.colClues[c];
      ctx.fillStyle = cur === clue ? GREEN : cur > clue ? RED : ink;
      ctx.fillText(String(clue), originX + c * cell + cell / 2, originY - cell * 0.46);
    }
    ctx.textAlign = 'center';
    for (let r = 0; r < R; r++) {
      const cur = rowCount[r];
      const clue = puzzle.rowClues[r];
      ctx.fillStyle = cur === clue ? GREEN : cur > clue ? RED : ink;
      ctx.fillText(String(clue), originX + C * cell + cell * 0.7, originY + r * cell + cell / 2);
    }

    // water marks (small dots), ships (merged rounded capsules)
    for (let r = 0; r < R; r++) {
      for (let c = 0; c < C; c++) {
        const x = originX + c * cell;
        const y = originY + r * cell;
        if (isWater(r, c)) {
          ctx.fillStyle = givenWater.has(key(r, c)) ? givenCol : muted;
          ctx.globalAlpha = givenWater.has(key(r, c)) ? 0.9 : 0.55;
          ctx.beginPath();
          ctx.arc(x + cell / 2, y + cell / 2, Math.max(2.5, cell * 0.1), 0, Math.PI * 2);
          ctx.fill();
          ctx.globalAlpha = 1;
        } else if (isShip(r, c)) {
          const m = cell * 0.16;
          const n = isShip(r - 1, c);
          const s = isShip(r + 1, c);
          const e = isShip(r, c + 1);
          const wst = isShip(r, c - 1);
          const x0 = x + (wst ? 0 : m);
          const y0 = y + (n ? 0 : m);
          const x1 = x + cell - (e ? 0 : m);
          const y1 = y + cell - (s ? 0 : m);
          const single = !n && !s && !e && !wst;
          ctx.fillStyle = givenShip.has(key(r, c)) ? givenCol : shipCol;
          if (single) {
            ctx.beginPath();
            ctx.arc(x + cell / 2, y + cell / 2, (cell - 2 * m) / 2, 0, Math.PI * 2);
            ctx.fill();
          } else {
            roundRect(x0, y0, x1 - x0, y1 - y0, cell * 0.28);
            ctx.fill();
          }
        }
      }
    }
  }

  onMount(() => {
    recount();
    fit();
    const ro = new ResizeObserver(() => fit());
    ro.observe(wrap);
    return () => ro.disconnect();
  });
</script>

<div class="bs" bind:this={wrap}>
  <p class="hint">
    Find the fleet. Numbers count ship segments in each column / row. Ships are
    straight and never touch, not even diagonally.
  </p>

  <canvas
    bind:this={canvas}
    class="board"
    role="img"
    aria-label={`Battleships ${R}×${C}`}
    onpointerdown={onDown}
    onpointermove={onMove}
    onpointerup={onUp}
    onpointercancel={onUp}
    oncontextmenu={(e) => e.preventDefault()}
  ></canvas>

  <div class="fleet" aria-label="Fleet">
    {#each fleetState as f}
      <span class="ship" class:done={f.done} title={`Ship of ${f.len}`}>
        {#each Array(f.len) as _}<i></i>{/each}
      </span>
    {/each}
  </div>

  <div class="tools">
    <div class="seg" role="group" aria-label="Tool">
      <button class:active={mode === 'ship'} onclick={() => (mode = 'ship')}>🚢 Ship</button>
      <button class:active={mode === 'water'} onclick={() => (mode = 'water')}>🌊 Water</button>
    </div>
    <button class="ghost" onclick={undo} disabled={!canUndo}>↶ Undo</button>
    <button class="ghost" onclick={clearAll}>Reset</button>
  </div>

  <p class="legend">
    Desktop: <b>left-click</b> cycles empty → ship → water, <b>right-click</b> = water.
    Mobile: pick a tool and <b>drag</b>; <b>long-press</b> = water.
  </p>
</div>

<style>
  .bs {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
  }
  .hint {
    margin: 0;
    max-width: 34rem;
    text-align: center;
    color: var(--muted, #64748b);
    font-size: 0.9rem;
    line-height: 1.35;
  }
  .board {
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    max-width: 100%;
    cursor: pointer;
  }
  .fleet {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    justify-content: center;
    align-items: center;
    max-width: 34rem;
  }
  .ship {
    display: inline-flex;
    gap: 2px;
    padding: 3px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--muted) 16%, transparent);
  }
  .ship i {
    width: 12px;
    height: 12px;
    border-radius: 3px;
    background: var(--ink);
    opacity: 0.45;
  }
  .ship.done {
    background: color-mix(in srgb, var(--good) 22%, transparent);
  }
  .ship.done i {
    opacity: 1;
    background: var(--good);
  }
  .tools {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
    justify-content: center;
  }
  .seg {
    display: inline-flex;
    border: 2px solid var(--ink, #111);
    border-radius: 0.6rem;
    overflow: hidden;
  }
  .seg button {
    border: none;
    background: var(--surface-2, #fff);
    color: var(--ink, #0f172a);
    padding: 0.5rem 0.8rem;
    font-size: 0.95rem;
    cursor: pointer;
  }
  .seg button.active {
    background: var(--accent, #fdc800);
    color: #111;
    font-weight: 700;
  }
  .ghost {
    border: 2px solid var(--ink, #111);
    background: var(--surface-2, #fff);
    color: var(--ink, #0f172a);
    padding: 0.5rem 0.8rem;
    border-radius: 0.6rem;
    font-size: 0.95rem;
    cursor: pointer;
  }
  .ghost:disabled {
    opacity: 0.45;
    cursor: default;
  }
  .legend {
    margin: 0;
    max-width: 34rem;
    text-align: center;
    color: var(--muted, #64748b);
    font-size: 0.8rem;
    line-height: 1.4;
  }
</style>
