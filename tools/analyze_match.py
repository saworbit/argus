#!/usr/bin/env python3
"""Botlab/Argus match analysis v3: BSP wireframe + telemetry, A/B panels,
nav-graph overlay, combat deaths. Lava deaths classify by hull-0
contents at the death position (z < -300 is the no-BSP fallback only).
usage:
  analyze_match.py map.bsp logA [logB] out.png [nav.json]"""
import re, struct, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

args = sys.argv[1:]
NAV = None
if args[-1].endswith(".json"):
    NAV = args[-1]; args = args[:-1]
BSP, LOGA = args[0], args[1]
LOGB = args[2] if len(args) > 3 else None
OUT = args[-1]

def load_bsp(path):
    data = open(path, "rb").read()
    assert struct.unpack_from("<i", data, 0)[0] == 29
    lumps = [struct.unpack_from("<ii", data, 4 + i * 8) for i in range(15)]
    vo, vl = lumps[3]; eo, el = lumps[12]; mo, _ = lumps[14]
    verts = [struct.unpack_from("<fff", data, vo + i * 12) for i in range(vl // 12)]
    edges = [struct.unpack_from("<HH", data, eo + i * 4) for i in range(el // 4)]
    mins = struct.unpack_from("<fff", data, mo)
    maxs = struct.unpack_from("<fff", data, mo + 12)
    return verts, edges, mins, maxs

CONTENTS_WATER, CONTENTS_SLIME, CONTENTS_LAVA = -3, -4, -5

def bsp_contents_classifier(bsp_path):
    """Hull-0 point contents for death classification. Returns a
    contents(x, y, z) callable, or None if the BSP is unreadable."""
    try:
        data = open(bsp_path, "rb").read()
    except OSError:
        return None
    def lump(i):
        off, ln = struct.unpack_from("<ii", data, 4 + i * 8)
        return data[off:off + ln]
    pl = lump(1)
    planes = [struct.unpack_from("<4f", pl, i * 20) for i in range(len(pl) // 20)]
    nd = lump(5)
    nodes5 = [struct.unpack_from("<i8h2H", nd, i * 24) for i in range(len(nd) // 24)]
    lf = lump(10)
    leaves = [struct.unpack_from("<2i6h2H4B", lf, i * 28) for i in range(len(lf) // 28)]
    hull0 = struct.unpack_from("<9f7i", lump(14), 0)[9]
    def contents(x, y, z):
        n = hull0
        while n >= 0:
            node = nodes5[n]
            nx, ny, nz, d = planes[node[0]][:4]
            n = node[1] if (nx * x + ny * y + nz * z - d) >= 0 else node[2]
        return leaves[-1 - n][0]
    return contents

def death_is_lava(contents, x, y, z):
    # CLASSIFICATION BOUNDARY (2026-08-18): lava deaths were judged by
    # z < -300, a dm4-shaped rule that misses dm2's killing lava at
    # z about -35 and miscounts dm4's solid pit floors at -360. The
    # death position is the victim's origin, above the surface, so
    # probe it and one step below.
    if contents is None:
        return z < -300          # legacy rule, no BSP on hand
    return (contents(x, y, z) in (CONTENTS_LAVA, CONTENTS_SLIME)
            or contents(x, y, z - 24) in (CONTENTS_LAVA, CONTENTS_SLIME))

# bot names may contain spaces (the v3.37 homage roster): anchor on
# the grammar keywords, never on whitespace-splitting
PAT_V1 = re.compile(r"(?:BOTLOG|ARGLOG) (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)' spd\s+(-?[\d.]+) yaw\s+(-?[\d.]+) mode\s+(\d) st\s+(\d+) gl\s+(\d+)(?: hp\s+(-?[\d.]+) frg\s+(-?\d+))?")
PAT_V0 = re.compile(r"(?:BOTLOG|ARGLOG) (\S+) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)' yaw\s+(-?[\d.]+) blk\s+(\d+)")
# killer group optional: pre-2026-08-18 logs can carry an empty killer
# (nameless enemy entities) and those rows must still count
PAT_DEATH = re.compile(r"ARGEVT (.+?) death\s+(?:(.+?)\s+)?pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)'")

def parse(path):
    bots, fmt, deaths = {}, None, []
    for line in open(path, errors="replace"):
        m = PAT_V1.search(line)
        if m:
            fmt = "v1"; g = m.groups()
            rec = dict(t=float(g[1]), x=float(g[2]), y=float(g[3]), z=float(g[4]),
                       spd=float(g[5]), st=int(g[8]), gl=int(g[9]))
            if g[10] is not None:
                rec["hp"] = float(g[10]); rec["frg"] = int(g[11])
            bots.setdefault(g[0], []).append(rec)
            continue
        m = PAT_V0.search(line)
        if m:
            fmt = fmt or "v0"
            n, t, x, y, z, yaw, blk = m.groups()
            bots.setdefault(n, []).append(dict(t=float(t), x=float(x), y=float(y),
                z=float(z), blk=int(blk)))
            continue
        m = PAT_DEATH.search(line)
        if m:
            deaths.append((m.group(1), m.group(2) or "world",
                           float(m.group(3)), float(m.group(4)),
                           float(m.group(5))))
    return bots, fmt, deaths

def stats(bots, fmt, deaths=(), contents=None):
    out = {}
    for n, r in bots.items():
        dur = r[-1]["t"] - r[0]["t"]
        dist = sum(((r[i]["x"]-r[i-1]["x"])**2 + (r[i]["y"]-r[i-1]["y"])**2) ** 0.5
                   for i in range(1, len(r)))
        cells = {(int(p["x"] // 64), int(p["y"] // 64)) for p in r}
        s = dict(dur=dur, dist=dist, avg=dist / dur if dur else 0, cover=len(cells))
        if fmt == "v1":
            s["goals"] = r[-1]["gl"]; s["stalls"] = r[-1]["st"]
            if "frg" in r[-1]:
                s["frags"] = r[-1]["frg"]
                s["deaths"] = sum(1 for d in deaths if d[0] == n)
                s["lava"] = sum(1 for d in deaths if d[0] == n
                                and d[1] == "world"
                                and death_is_lava(contents, d[2], d[3], d[4]))
        else:
            s["blocked"] = r[-1]["blk"]
        out[n] = s
    return out

COLORS = {"Reap": "#d9531e", "Omi": "#1e6bd9", "Zeus": "#2a9d5c"}

def draw_nav(ax, navpath):
    import json
    nav = json.load(open(navpath))
    P = nav["nodes"]
    for i, j, two in nav["links"]:
        ax.plot([P[i][0], P[j][0]], [P[i][1], P[j][1]],
                color="#2a9d5c" if two else "#cc8800", lw=0.4, alpha=0.25, zorder=2)
    for a, b in nav["teles"]:
        ax.plot([P[a][0], P[b][0]], [P[a][1], P[b][1]],
                color="purple", lw=0.7, ls="--", alpha=0.4, zorder=2)
    ax.scatter([p[0] for p in P], [p[1] for p in P], s=4, c="#1e6bd9",
               alpha=0.3, zorder=2)

def panel(ax, verts, edges, mins, maxs, bots, st, fmt, title, deaths=()):
    for a, b in edges[1:]:
        if a < len(verts) and b < len(verts):
            ax.plot([verts[a][0], verts[b][0]], [verts[a][1], verts[b][1]],
                    color="0.85", lw=0.35, zorder=1)
    for n, r in bots.items():
        xs = [p["x"] for p in r]; ys = [p["y"] for p in r]
        c = COLORS.get(n, "black")
        s = st[n]
        if fmt == "v1" and "frags" in s:
            extra = "%dK/%dD, %d goals, %d stalls" % (s["frags"], s["deaths"],
                                                      s["goals"], s["stalls"])
        elif fmt == "v1":
            extra = "%d goals, %d stalls" % (s["goals"], s["stalls"])
        else:
            extra = "%d blocked" % s["blocked"]
        ax.plot(xs, ys, color=c, lw=1.3, alpha=0.8, zorder=3,
                label="%s: %.0f u/s, %d cells, %s" % (n, s["avg"], s["cover"], extra))
        ax.plot(xs[0], ys[0], "o", ms=8, color=c, mec="black", zorder=4)
        ax.plot(xs[-1], ys[-1], "s", ms=7, color=c, mec="black", zorder=4)
    for victim, killer, dx, dy, dz in deaths:
        ax.plot(dx, dy, "x", ms=8, mew=2.2, color=COLORS.get(victim, "black"), zorder=5)
    ax.set_aspect("equal")
    ax.set_xlim(mins[0]-64, maxs[0]+64); ax.set_ylim(mins[1]-64, maxs[1]+64)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, fontsize=11)
    ax.legend(loc="upper right", fontsize=8)

verts, edges, mins, maxs = load_bsp(BSP)
contents = bsp_contents_classifier(BSP)
ba, fa, da = parse(LOGA); sa = stats(ba, fa, da, contents)
print("[%s] fmt=%s" % (LOGA, fa))
for n, s in sa.items(): print(" ", n, s)

if LOGB:
    bb, fb, db = parse(LOGB); sb = stats(bb, fb, db, contents)
    print("[%s] fmt=%s" % (LOGB, fb))
    for n, s in sb.items(): print(" ", n, s)
    # titles come from the actual inputs: the originals were hardcoded
    # to the first-ever A/B ("v2 vs v3 on lqdm2") and every plot since
    # inherited them (Shane's project review)
    import os
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10.5))
    if NAV: draw_nav(ax1, NAV)
    panel(ax1, verts, edges, mins, maxs, ba, sa, fa,
          "A: %s (x = death)" % os.path.basename(LOGA), da)
    if NAV: draw_nav(ax2, NAV)
    panel(ax2, verts, edges, mins, maxs, bb, sb, fb,
          "B: %s (x = death)" % os.path.basename(LOGB), db)
    fig.suptitle("Argus on %s - headless matches, vanilla protocol 15"
                 % os.path.splitext(os.path.basename(BSP))[0], fontsize=13)
else:
    fig, ax = plt.subplots(figsize=(11, 11))
    if NAV: draw_nav(ax, NAV)
    panel(ax, verts, edges, mins, maxs, ba, sa, fa, LOGA, da)
plt.tight_layout()
plt.savefig(OUT, dpi=130)
print("wrote", OUT)
