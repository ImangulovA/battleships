#!/usr/bin/env python3
"""
Daily Battleships (Bimaru / Solitaire Battleships) — generator + uniqueness solver.

We GENERATE our own puzzles (independent build; the Krazydad PDFs in sources/ are
used only to calibrate grid sizes / fleets per difficulty tier). Each puzzle hides
a fixed FLEET of straight ships on an N×N grid. Ships never touch, not even
diagonally. Row/column clues count how many ship segments sit in that row/column.
The fleet composition is known. We reveal the MINIMUM extra given cells (water, or
a specific ship part) needed for a provably UNIQUE, no-guessing solution.

Key geometry fact used throughout: "ships never touch, not even diagonally" is
equivalent to "no two ship cells are diagonally adjacent" — because any bend in an
orthogonally-connected blob of ship cells forces a diagonal pair. So every ship
component is automatically a straight line, and the only adjacency rule the solvers
need is: NO two ship cells share a corner.

Output: app/src/lib/game/data/days.js  (DAYS map + dayIndexes/loadDay).
"""

import os
import random
import sys

# Cell states.
UNK, WATER, SHIP = 0, 1, 2

# Orthogonal directions.
DIRS = ["N", "E", "S", "W"]
DELTA = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}
DIAG = [(-1, -1), (-1, 1), (1, -1), (1, 1)]


# --------------------------------------------------------------------------- #
# Part-type of a ship cell, derived from the full solution grid.              #
#   single            — no ship neighbour                                     #
#   endN/endE/endS/endW — exactly one ship neighbour, in that direction       #
#   mid               — two (opposite) ship neighbours                        #
# --------------------------------------------------------------------------- #
def part_type(grid, r, c):
    R, C = len(grid), len(grid[0])
    nb = []
    for d in DIRS:
        dr, dc = DELTA[d]
        nr, nc = r + dr, c + dc
        if 0 <= nr < R and 0 <= nc < C and grid[nr][nc] == SHIP:
            nb.append(d)
    if not nb:
        return "single"
    if len(nb) == 1:
        return "end" + nb[0]
    return "mid"


# --------------------------------------------------------------------------- #
# Random legal fleet placement (largest ship first; reject on touch/overlap). #
# --------------------------------------------------------------------------- #
def place_fleet(R, C, fleet, rng):
    """Return (grid, ships) or None if placement got stuck this attempt."""
    grid = [[WATER] * C for _ in range(R)]
    ships = []

    def fits(cells):
        cellset = set(cells)
        for (r, c) in cells:
            if not (0 <= r < R and 0 <= c < C):
                return False
            if grid[r][c] == SHIP:
                return False
            # no other ship in the 8-neighbourhood
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < R and 0 <= nc < C and (nr, nc) not in cellset and grid[nr][nc] == SHIP:
                        return False
        return True

    for length in sorted(fleet, reverse=True):
        placed = False
        for _ in range(500):
            horiz = True if length == 1 else rng.random() < 0.5
            if horiz:
                r = rng.randrange(R)
                c = rng.randrange(C - length + 1)
                cells = [(r, c + i) for i in range(length)]
            else:
                r = rng.randrange(R - length + 1)
                c = rng.randrange(C)
                cells = [(r + i, c) for i in range(length)]
            if fits(cells):
                for (rr, cc) in cells:
                    grid[rr][cc] = SHIP
                ships.append(cells)
                placed = True
                break
        if not placed:
            return None
    return grid, ships


# --------------------------------------------------------------------------- #
# Given-cell constraints: what a revealed hint tells the solvers directly.    #
# Returns {(r,c): WATER|SHIP} of forced cells implied by the hint list.       #
#   water   -> that cell WATER                                                #
#   single  -> cell SHIP; 4 orthogonal neighbours WATER                       #
#   endD    -> cell SHIP; neighbour D SHIP; other 3 orthogonal WATER          #
#   mid/ship-> cell SHIP (no-touch handles the diagonals)                     #
# --------------------------------------------------------------------------- #
def given_constraints(R, C, givens):
    forced = {}

    def setf(r, c, v):
        if 0 <= r < R and 0 <= c < C:
            forced[(r, c)] = v

    for (r, c, t) in givens:
        if t == "water":
            setf(r, c, WATER)
            continue
        setf(r, c, SHIP)
        if t == "single":
            for d in DIRS:
                dr, dc = DELTA[d]
                setf(r + dr, c + dc, WATER)
        elif t.startswith("end"):
            body = t[3]
            for d in DIRS:
                dr, dc = DELTA[d]
                setf(r + dr, c + dc, SHIP if d == body else WATER)
        # "mid" / "ship": just SHIP; the no-touch rule supplies the rest
    return forced


# --------------------------------------------------------------------------- #
# Logic solver — constraint propagation ONLY (forced moves, never guesses).   #
# Every rule is SOUND, so a fully-determined board is THE unique solution.    #
# --------------------------------------------------------------------------- #
class LogicSolver:
    def __init__(self, R, C, row_clues, col_clues, fleet, givens):
        self.R, self.C = R, C
        self.row_clues = row_clues
        self.col_clues = col_clues
        self.lmax = max(fleet)
        self.contra = False
        self.cell = [[UNK] * C for _ in range(R)]
        for (r, c), v in given_constraints(R, C, givens).items():
            self.set(r, c, v)

    def set(self, r, c, v):
        cur = self.cell[r][c]
        if cur != UNK and cur != v:
            self.contra = True
            return False
        if cur == v:
            return False
        self.cell[r][c] = v
        return True

    def propagate(self):
        R, C = self.R, self.C
        changed = True
        while changed and not self.contra:
            changed = False

            # --- no-touch: diagonal neighbours of any SHIP are WATER ----------
            for r in range(R):
                for c in range(C):
                    if self.cell[r][c] != SHIP:
                        continue
                    for dr, dc in DIAG:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < R and 0 <= nc < C:
                            changed |= self.set(nr, nc, WATER)

            # --- max-length cap: a straight SHIP run of length lmax can't grow;
            #     a run longer than lmax is impossible -------------------------
            for r in range(R):
                c = 0
                while c < C:
                    if self.cell[r][c] == SHIP:
                        start = c
                        while c < C and self.cell[r][c] == SHIP:
                            c += 1
                        run = c - start
                        if run > self.lmax:
                            self.contra = True
                        elif run == self.lmax:
                            if start - 1 >= 0:
                                changed |= self.set(r, start - 1, WATER)
                            if c < C:
                                changed |= self.set(r, c, WATER)
                    else:
                        c += 1
            for c in range(C):
                r = 0
                while r < R:
                    if self.cell[r][c] == SHIP:
                        start = r
                        while r < R and self.cell[r][c] == SHIP:
                            r += 1
                        run = r - start
                        if run > self.lmax:
                            self.contra = True
                        elif run == self.lmax:
                            if start - 1 >= 0:
                                changed |= self.set(start - 1, c, WATER)
                            if r < R:
                                changed |= self.set(r, c, WATER)
                    else:
                        r += 1

            # --- row / column clue saturation --------------------------------
            for r in range(R):
                ship = sum(self.cell[r][c] == SHIP for c in range(C))
                unk = [c for c in range(C) if self.cell[r][c] == UNK]
                if ship > self.row_clues[r]:
                    self.contra = True
                elif ship == self.row_clues[r]:
                    for c in unk:
                        changed |= self.set(r, c, WATER)
                elif ship + len(unk) == self.row_clues[r]:
                    for c in unk:
                        changed |= self.set(r, c, SHIP)
            for c in range(C):
                ship = sum(self.cell[r][c] == SHIP for r in range(R))
                unk = [r for r in range(R) if self.cell[r][c] == UNK]
                if ship > self.col_clues[c]:
                    self.contra = True
                elif ship == self.col_clues[c]:
                    for r in unk:
                        changed |= self.set(r, c, WATER)
                elif ship + len(unk) == self.col_clues[c]:
                    for r in unk:
                        changed |= self.set(r, c, SHIP)

        return not self.contra

    def solved(self):
        if self.contra:
            return False
        for r in range(self.R):
            for c in range(self.C):
                if self.cell[r][c] == UNK:
                    return False
        return True

    def ship_set(self):
        return {(r, c) for r in range(self.R) for c in range(self.C) if self.cell[r][c] == SHIP}


def logic_solve(R, C, row_clues, col_clues, fleet, givens):
    """Returns (status, LogicSolver). status in {'solved','stuck','contra'}."""
    ls = LogicSolver(R, C, row_clues, col_clues, fleet, givens)
    ls.propagate()
    if ls.contra:
        return "contra", ls
    return ("solved" if ls.solved() else "stuck"), ls


# --------------------------------------------------------------------------- #
# Backtracking solver — independent uniqueness cross-check (counts up to 2).  #
# Assign each cell WATER/SHIP row-major; prune with the diagonal no-touch     #
# rule, row/col clue bounds and given constraints; validate the fleet at the  #
# end.                                                                        #
# --------------------------------------------------------------------------- #
class Solver:
    def __init__(self, R, C, row_clues, col_clues, fleet, givens):
        self.R, self.C = R, C
        self.row_clues = row_clues
        self.col_clues = col_clues
        self.fleet_key = tuple(sorted(fleet))
        self.forced = given_constraints(R, C, givens)
        self.node_cap = 300000
        self.nodes = 0
        self.solutions = []

    def solve(self, limit=2):
        R, C = self.R, self.C
        grid = [[WATER] * C for _ in range(R)]
        row_cnt = [0] * R
        col_cnt = [0] * C

        def ok_ship(r, c):
            # No diagonal ship neighbour among already-placed cells (row r-1 done,
            # current row up to c-1 done).
            for dr, dc in ((-1, -1), (-1, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < R and 0 <= nc < C and grid[nr][nc] == SHIP:
                    return False
            return True

        def bt(idx):
            if self.nodes > self.node_cap or len(self.solutions) >= limit:
                return
            if idx == R * C:
                if self.valid_full(grid):
                    self.solutions.append([row[:] for row in grid])
                return
            r, c = divmod(idx, C)
            self.nodes += 1
            forced = self.forced.get((r, c))
            options = (SHIP, WATER) if forced is None else (forced,)
            for v in options:
                if v == SHIP:
                    if not ok_ship(r, c):
                        continue
                    nr_row = row_cnt[r] + 1
                    nc_col = col_cnt[c] + 1
                    if nr_row > self.row_clues[r] or nc_col > self.col_clues[c]:
                        continue
                else:
                    nr_row = row_cnt[r]
                    nc_col = col_cnt[c]
                # end-of-row / end-of-column exact clue checks
                if c == C - 1 and nr_row != self.row_clues[r]:
                    continue
                cells_left_row = C - 1 - c
                if nr_row + cells_left_row < self.row_clues[r]:
                    continue
                rows_left = R - 1 - r
                if nc_col + rows_left < self.col_clues[c]:
                    continue
                grid[r][c] = v
                row_cnt[r] = nr_row
                col_cnt[c] = nc_col
                bt(idx + 1)
                row_cnt[r] = nr_row - (1 if v == SHIP else 0)
                col_cnt[c] = nc_col - (1 if v == SHIP else 0)
                grid[r][c] = WATER
                if len(self.solutions) >= limit:
                    return

        bt(0)
        return self.solutions

    def valid_full(self, grid):
        R, C = self.R, self.C
        # No two ship cells diagonally adjacent (⇒ every component is straight).
        for r in range(R):
            for c in range(C):
                if grid[r][c] != SHIP:
                    continue
                for dr, dc in DIAG:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < R and 0 <= nc < C and grid[nr][nc] == SHIP:
                        return False
        # Component lengths (orthogonal connectivity) must match the fleet.
        seen = [[False] * C for _ in range(R)]
        lengths = []
        for r in range(R):
            for c in range(C):
                if grid[r][c] == SHIP and not seen[r][c]:
                    stack = [(r, c)]
                    seen[r][c] = True
                    size = 0
                    while stack:
                        cr, cc = stack.pop()
                        size += 1
                        for d in DIRS:
                            dr, dc = DELTA[d]
                            nr, nc = cr + dr, cc + dc
                            if 0 <= nr < R and 0 <= nc < C and grid[nr][nc] == SHIP and not seen[nr][nc]:
                                seen[nr][nc] = True
                                stack.append((nr, nc))
                    lengths.append(size)
        return tuple(sorted(lengths)) == self.fleet_key


# --------------------------------------------------------------------------- #
# Build one puzzle of a given size + fleet, solvable by LOGIC ALONE.          #
# --------------------------------------------------------------------------- #
def _solve_one(R, C, fleet, seed):
    """One placement attempt. Returns (row_clues, col_clues, given_cells, target)
    for a unique, no-guess puzzle, or None if this placement did not work out."""
    rng = random.Random(seed)
    got = place_fleet(R, C, fleet, rng)
    if not got:
        return None
    grid, _ships = got
    row_clues = [sum(grid[r][c] == SHIP for c in range(C)) for r in range(R)]
    col_clues = [sum(grid[r][c] == SHIP for r in range(R)) for c in range(C)]

    # NO-GUESS construction: reveal grid cells (with their true value / part type)
    # in row-major order until the logic solver fully determines the board. Every
    # revealed fact is true, so the true solution stays valid and the loop
    # converges (worst case: reveal everything).
    given_cells = []          # list of (r, c, type)
    given_set = set()
    target = {(r, c) for r in range(R) for c in range(C) if grid[r][c] == SHIP}

    ok = False
    for _iter in range(R * C + 2):
        status, ls = logic_solve(R, C, row_clues, col_clues, fleet, given_cells)
        if status == "contra":
            break
        if status == "solved" and ls.ship_set() == target:
            ok = True
            break
        revealed = False
        for r in range(R):
            for c in range(C):
                if (r, c) in given_set or ls.cell[r][c] != UNK:
                    continue
                t = "water" if grid[r][c] == WATER else part_type(grid, r, c)
                given_cells.append((r, c, t))
                given_set.add((r, c))
                revealed = True
                break
            if revealed:
                break
        if not revealed:
            break
    if not ok:
        return None

    # Independent uniqueness cross-check via backtracking search.
    solver = Solver(R, C, row_clues, col_clues, fleet, given_cells)
    sols = solver.solve(limit=2)
    if len(sols) != 1:
        return None
    if {(r, c) for r in range(R) for c in range(C) if sols[0][r][c] == SHIP} != target:
        return None
    return row_clues, col_clues, given_cells, target


def build_puzzle(R, C, fleet, seed, tier):
    """Try many placements (seeded, reproducibly) and keep the CLEANEST one:
    fewest givens, but never a fully-given (trivial) board."""
    ncells = R * C
    best = None  # (given_count, row_clues, col_clues, given_cells, target)
    for attempt in range(160):
        res = _solve_one(R, C, fleet, seed * 1000 + attempt)
        if res is None:
            continue
        row_clues, col_clues, given_cells, target = res
        g = len(given_cells)
        # Reject fully-given boards (every ship cell handed to the player).
        if g >= len(target):
            continue
        if best is None or g < best[0]:
            best = (g, row_clues, col_clues, given_cells, target)
        # A handful of hints is the sweet spot; stop early once we find one.
        if best[0] <= max(1, ncells // 12):
            break
    if best is None:
        raise RuntimeError(f"could not build a unique {R}x{C} battleships puzzle at seed {seed}")

    _g, row_clues, col_clues, given_cells, target = best
    solution = sorted([r, c] for (r, c) in target)
    givens = sorted(([r, c, t] for (r, c, t) in given_cells), key=lambda g: (g[0], g[1]))
    return {
        "rows": R,
        "cols": C,
        "tier": tier,
        "rowClues": row_clues,
        "colClues": col_clues,
        "fleet": sorted(fleet, reverse=True),
        "givens": givens,
        "solution": solution,
    }


# --------------------------------------------------------------------------- #
# Difficulty schedule + emit days.js                                          #
# --------------------------------------------------------------------------- #
import datetime

# Calendar anchor: day 0 = anchorDate in app/src/lib/game/index.js.
ANCHOR = datetime.date(2026, 7, 3)  # [2026, monthIndex 6, 3]

# Grid size + fleet per difficulty tier (calibrated against Krazydad tiers).
TIER_SIZE = {"beginner": 4, "easy": 5, "medium": 6, "hard": 7, "expert": 8}
SIZE_TIER = {v: k for k, v in TIER_SIZE.items()}
FLEET_BY_SIZE = {
    4: [2, 1, 1],
    5: [3, 2, 1],
    6: [3, 2, 2, 1],
    7: [4, 3, 2, 1],
    8: [4, 3, 2, 2, 1],
}

# Established weekly ramp by REAL weekday (Mon=0 .. Sun=6):
#   Mon 4x4 · Tue 5x5 · Wed 6x6 · Thu 7x7 · Fri 8x8 · Sat 7x7 · Sun 7x7
SIZE_BY_WEEKDAY = {0: 4, 1: 5, 2: 6, 3: 7, 4: 8, 5: 7, 6: 7}

# Days never regenerated (already released / kept as-is).
PRESERVE = {-1, 0}


def size_for(idx):
    d = ANCHOR + datetime.timedelta(days=idx)
    return SIZE_BY_WEEKDAY[d.weekday()]


def js_day(blob):
    def arr(a):
        return "[" + ",".join(str(x) for x in a) + "]"

    parts = [
        f'rows:{blob["rows"]}',
        f'cols:{blob["cols"]}',
        f'tier:"{blob["tier"]}"',
        f'rowClues:{arr(blob["rowClues"])}',
        f'colClues:{arr(blob["colClues"])}',
        f'fleet:{arr(blob["fleet"])}',
        "givens:[" + ",".join(f'[{r},{c},"{t}"]' for (r, c, t) in blob["givens"]) + "]",
        "solution:[" + ",".join(f"[{r},{c}]" for (r, c) in blob["solution"]) + "]",
    ]
    return "{" + ",".join(parts) + "}"


def load_existing(out):
    """Return {idx: raw_js_object_string} from an existing days.js, or {}."""
    import re

    if not os.path.exists(out):
        return {}
    txt = open(out).read()
    existing = {}
    for m in re.finditer(r'"(-?\d+)":\s*(\{[^{}]*\})', txt):
        existing[int(m.group(1))] = m.group(2)
    return existing


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else -1
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.normpath(os.path.join(here, "..", "app", "src", "lib", "game", "data", "days.js"))

    existing = load_existing(out)
    entries = []
    for idx in range(lo, hi + 1):
        if idx in PRESERVE and idx in existing:
            entries.append((idx, existing[idx]))
            print(f"day {idx:>3}  PRESERVED (kept as-is)")
            continue
        size = size_for(idx)
        tier = SIZE_TIER[size]
        fleet = FLEET_BY_SIZE[size]
        blob = build_puzzle(size, size, fleet, seed=1000 + idx, tier=tier)
        entries.append((idx, js_day(blob)))
        wd = (ANCHOR + datetime.timedelta(days=idx)).strftime("%a")
        print(
            f"day {idx:>3}  {wd}  {tier:<8} {size}x{size}  "
            f"fleet={blob['fleet']}  givens={len(blob['givens'])}  ships={len(blob['solution'])}"
        )

    lines = [
        "// AUTO-GENERATED by scripts/gen_days.py — do not hand-edit.",
        "// Daily Battleships (Bimaru) puzzles (independent build). `solution` lists",
        "// the ship cells [r,c]; every other cell is water. See gen_days.py.",
        "export const DAYS = {",
    ]
    for idx, raw in entries:
        lines.append(f'  "{idx}": {raw},')
    lines.append("};")
    lines.append("")
    lines.append("export function dayIndexes() { return Object.keys(DAYS).map(Number); }")
    lines.append("export function loadDay(idx) { return DAYS[idx] ?? null; }")
    lines.append("")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"\nwrote {out}  ({len(entries)} days)")


if __name__ == "__main__":
    main()
