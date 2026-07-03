#!/usr/bin/env python3
"""Render a Battleships day to PNG (rough mirror of GameComponent) for visual QA.

Usage: preview_day.py <dayIdx> [--empty]   (--empty = givens only, no solution)
Writes /tmp/bs_preview_<idx>.png
"""
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont


def load_days():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(os.path.join(here, "..", "app", "src", "lib", "game", "data", "days.js"))
    txt = open(path).read()
    body = txt.split("export const DAYS = ", 1)[1].split("\n};", 1)[0] + "\n}"
    body = re.sub(r"([{,])(\w+):", r'\1"\2":', body)
    body = re.sub(r",(\s*[}\]])", r"\1", body)
    return json.loads(body)


def font(sz):
    for p in ["/System/Library/Fonts/SFNSMono.ttf", "/System/Library/Fonts/Menlo.ttc",
              "/Library/Fonts/Arial.ttf"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def render(d, show_solution=True):
    R, C = d["rows"], d["cols"]
    cell = 56
    ox, oy = int(cell * 0.2), int(cell * 0.95)
    W = ox + C * cell + int(cell * 1.4)
    H = oy + R * cell + int(cell * 0.2)
    S = 2
    img = Image.new("RGB", (W * S, H * S), "#fdf6e3")
    dr = ImageDraw.Draw(img)

    ink = "#111111"
    given = "#a855f7"
    border = "#cccccc"

    def rect(x0, y0, x1, y1, **kw):
        dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], **kw)

    def rrect(x0, y0, x1, y1, rad, fill):
        dr.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=rad * S, fill=fill)

    rect(ox, oy, ox + C * cell, oy + R * cell, fill="#ffffff")
    for c in range(C + 1):
        dr.line([(ox + c * cell) * S, oy * S, (ox + c * cell) * S, (oy + R * cell) * S], fill=border, width=S)
    for r in range(R + 1):
        dr.line([ox * S, (oy + r * cell) * S, (ox + C * cell) * S, (oy + r * cell) * S], fill=border, width=S)
    rect(ox, oy, ox + C * cell, oy + R * cell, outline=ink, width=2 * S)

    f = font(int(cell * 0.42 * S))
    for c in range(C):
        t = str(d["colClues"][c])
        w = dr.textlength(t, font=f)
        dr.text(((ox + c * cell + cell / 2) * S - w / 2, (oy - cell * 0.68) * S), t, fill=ink, font=f)
    for r in range(R):
        t = str(d["rowClues"][r])
        w = dr.textlength(t, font=f)
        dr.text(((ox + C * cell + cell * 0.7) * S - w / 2, (oy + r * cell + cell * 0.28) * S), t, fill=ink, font=f)

    ships = {(r, c) for (r, c) in d["solution"]}
    given_ship = {(r, c) for (r, c, t) in d["givens"] if t != "water"}
    given_water = {(r, c) for (r, c, t) in d["givens"] if t == "water"}

    show = ships if show_solution else given_ship
    for (r, c) in show:
        m = cell * 0.16
        x, y = ox + c * cell, oy + r * cell
        n = (r - 1, c) in show
        s = (r + 1, c) in show
        e = (r, c + 1) in show
        wst = (r, c - 1) in show
        x0 = x + (0 if wst else m)
        y0 = y + (0 if n else m)
        x1 = x + cell - (0 if e else m)
        y1 = y + cell - (0 if s else m)
        col = given if (r, c) in given_ship else ink
        rrect(x0, y0, x1, y1, cell * 0.28, col)

    waters = given_water if not show_solution else given_water
    for (r, c) in waters:
        x, y = ox + c * cell, oy + r * cell
        rad = cell * 0.1
        cx, cy = x + cell / 2, y + cell / 2
        dr.ellipse([(cx - rad) * S, (cy - rad) * S, (cx + rad) * S, (cy + rad) * S], fill=given)

    img = img.resize((W, H), Image.LANCZOS)
    return img


def main():
    idx = sys.argv[1] if len(sys.argv) > 1 else "0"
    show = "--empty" not in sys.argv
    days = load_days()
    img = render(days[idx], show_solution=show)
    out = f"/tmp/bs_preview_{idx}{'' if show else '_empty'}.png"
    img.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
