# Argus brand - the parametric master. Every shipped mark derives from
# argus_A() below, so any asset can be rebuilt from its parameters alone.
#
# THE RULE: nothing in Quake is round and nothing comes to a point. Every
# surface in a BSP is a flat plane and every MDL face is a polygon, so the A
# has a flat cut apex, 45-degree chamfered terminals, and a counter cut by the
# same rule as the outline.
#
# Locked constraint: the crossbar is never broken. A chamfered A without its
# crossbar is the Half-Life lambda - wrong franchise, and a trademark.
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

PALETTE = {                     # lifted from tools/argus_mcp/src/gui.html
    "bg":     "#141210",
    "panel":  "#1e1b18",
    "ink":    "#e8dfd0",
    "muted":  "#9a8f7e",
    "line":   "#3a342c",
    "accent": "#d4531e",
}

# Locked 2026-09-14. ink/lsb match IBM Plex Mono Bold at cap height 100, so
# this A drops into the wordmark as its own first letter rather than merely
# resembling it.
MASTER = dict(k=0.34, wh=24.0, f=0.28, cyt=74.0, cyb=88.0, foot=13.0,
              ink=84.5, lsb=0.7, H=100.0)

# A heavier cut for 24px and below, where the counter closes up and the
# chamfers muddy.
FAVICON = dict(k=0.34, wh=25.0, f=0.20, cyt=72.0, cyb=90.0, foot=8.0,
               ink=88.0, lsb=0.0, H=100.0)


def mark_a_splay(W=100.0, H=100.0, k=0.42, wh=26.0, ap=16.0,
                 cyt=70.0, cyb=84.0, cap=None, foot=0.0):
    """Splayed A with a chamfered apex and optional chamfered feet.

    k    horizontal run per unit of height (the splay; strokes stay parallel)
    wh   horizontal stroke width           ap  width of the flat, cut apex
    cyt  crossbar top   cyb  crossbar bottom
    cap  counter apex cut height (None = auto, matching the outer apex)
    foot 45-degree chamfer on the outer terminals
    Returns an SVG path 'd' with fill-rule evenodd (outline + counter).
    """
    mid = W / 2.0
    ax0, ax1 = mid - ap / 2.0, mid + ap / 2.0
    xoL = lambda y: ax0 - k * y
    xoR = lambda y: ax1 + k * y
    xiL = lambda y: ax0 + wh - k * y
    xiR = lambda y: ax1 - wh + k * y
    # where the inner edges cross is the natural counter apex
    ycross = (2 * wh - ap) / (2 * k) if k else 0.0
    if cap is None:
        cap = ycross + ap / (2 * k)     # cut the counter apex by the same rule

    o = [(ax0, 0), (ax1, 0)]
    if foot:
        o += [(xoR(H - foot), H - foot), (xoR(H) - foot, H)]
    else:
        o += [(xoR(H), H)]
    o += [(xiR(H), H), (xiR(cyb), cyb), (xiL(cyb), cyb), (xiL(H), H)]
    if foot:
        o += [(xoL(H) + foot, H), (xoL(H - foot), H - foot)]
    else:
        o += [(xoL(H), H)]
    d = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in o) + " Z"

    c = [(xiL(cyt), cyt), (xiL(cap), cap), (xiR(cap), cap), (xiR(cyt), cyt)]
    d += " M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in c) + " Z"
    return d


def counter_apex(wh, ap, k, f):
    """Counter apex height such that its flat is `f` of the outer apex flat."""
    return (2 * wh - ap + ap * f) / (2 * k)


def argus_A(k, wh, f, cyt, cyb, foot, ink, lsb, H=100.0):
    """The master A. Returns (path_d, dx) - dx places ink's left edge at lsb."""
    ap = ink - 2 * k * H
    d = mark_a_splay(W=100.0, H=H, k=k, wh=wh, ap=ap, cyt=cyt, cyb=cyb,
                     cap=counter_apex(wh, ap, k, f), foot=foot)
    return d, lsb - ((50.0 - ap / 2.0) - k * H)
