#!/usr/bin/env python3
"""Independent gate: every generated Battleships day must be UNIQUE, match its
stored solution, have consistent clues/fleet/givens, and be solvable by pure
logic (no guessing). Run after ANY change to the generator/solver. Exits non-zero
on the first failing day."""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_days import Solver, logic_solve, part_type, DIRS, DELTA, DIAG, SHIP, WATER  # noqa: E402


def load_days():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(os.path.join(here, "..", "app", "src", "lib", "game", "data", "days.js"))
    txt = open(path).read()
    body = txt.split("export const DAYS = ", 1)[1]
    body = body.split("\n};", 1)[0] + "\n}"
    body = re.sub(r"([{,])(\w+):", r'\1"\2":', body)  # quote bare keys
    body = re.sub(r",(\s*[}\]])", r"\1", body)  # drop trailing commas
    return json.loads(body)


def main():
    days = load_days()
    bad = 0
    for key in sorted(days, key=lambda k: int(k)):
        d = days[key]
        R, C = d["rows"], d["cols"]
        fleet = d["fleet"]
        givens = [(r, c, t) for (r, c, t) in d["givens"]]
        ships = {(r, c) for (r, c) in d["solution"]}

        grid = [[WATER] * C for _ in range(R)]
        for (r, c) in ships:
            grid[r][c] = SHIP

        # clues recomputed from the solution
        rc = [sum(grid[r][c] == SHIP for c in range(C)) for r in range(R)]
        cc = [sum(grid[r][c] == SHIP for r in range(R)) for c in range(C)]
        clue_ok = rc == d["rowClues"] and cc == d["colClues"]

        # no diagonal touching + component lengths match the fleet
        touch_ok = True
        for (r, c) in ships:
            for dr, dc in DIAG:
                if (r + dr, c + dc) in ships:
                    touch_ok = False
        seen = set()
        lengths = []
        for (r, c) in ships:
            if (r, c) in seen:
                continue
            stack = [(r, c)]
            seen.add((r, c))
            size = 0
            while stack:
                cr, cc2 = stack.pop()
                size += 1
                for dd in DIRS:
                    dr, dc = DELTA[dd]
                    if (cr + dr, cc2 + dc) in ships and (cr + dr, cc2 + dc) not in seen:
                        seen.add((cr + dr, cc2 + dc))
                        stack.append((cr + dr, cc2 + dc))
            lengths.append(size)
        fleet_ok = sorted(lengths) == sorted(fleet)

        # givens consistent with the solution
        given_ok = True
        for (r, c, t) in givens:
            if t == "water":
                if (r, c) in ships:
                    given_ok = False
            else:
                if (r, c) not in ships or part_type(grid, r, c) != t:
                    given_ok = False

        # uniqueness via independent backtracking search
        solver = Solver(R, C, d["rowClues"], d["colClues"], fleet, givens)
        sols = solver.solve(limit=3)
        n = len(sols)
        match = n == 1 and {(r, c) for r in range(R) for c in range(C) if sols[0][r][c] == SHIP} == ships

        # NO-GUESS: logic propagation alone fully solves from the givens
        lstatus, ls = logic_solve(R, C, d["rowClues"], d["colClues"], fleet, givens)
        noguess = lstatus == "solved" and ls.ship_set() == ships

        good = clue_ok and touch_ok and fleet_ok and given_ok and n == 1 and match and noguess
        if not good:
            bad += 1
        print(
            f"day {int(key):>3} {d['tier']:<8} {R}x{C} fleet={fleet}  sols={n} "
            f"match={match} clue={clue_ok} touch={touch_ok} fleet_ok={fleet_ok} "
            f"givens={given_ok} noguess={noguess}  -> {'OK' if good else 'FAIL'}"
        )
    print(f"\n{'ALL OK' if bad == 0 else str(bad) + ' FAILED'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
