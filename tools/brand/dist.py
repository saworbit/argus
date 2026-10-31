# Argus brand - build every shipped SVG from the parametric master.
# Nothing here is hand-drawn: change MASTER in build.py and rerun, then run
# raster.js for the PNGs that platforms insist on.
#
#   python tools/brand/dist.py      writes docs/brand/*.svg
#   node tools/brand/raster.js      writes docs/brand/*.png
import os
import random
import build
import wordmark as wm

OUT = os.path.join(build.ROOT, "docs", "brand")

P = build.PALETTE
INK, ROCK, ACCENT = P["ink"], P["bg"], P["accent"]
MUTED, LINE = P["muted"], P["line"]
CAP, ADV, TRACK = 100.0, 85.96, 5.0
TAG = "VANILLA QUAKEC DEATHMATCH BOT · TELEMETRY LABORATORY"


def write(name, svg):
    with open(os.path.join(OUT, name), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(svg + "\n")
    return name


# --- the A -----------------------------------------------------------------
def a_path(params=None):
    return build.argus_A(**(params or build.MASTER))


def a_left(p):
    """x of the A's ink left edge inside its own 100-unit drawing box."""
    ap = p["ink"] - 2 * p["k"] * p["H"]
    return (50.0 - ap / 2.0) - p["k"] * p["H"]


def mark_svg(fill=INK, params=None, pad=8.0):
    d, _ = a_path(params)
    p = params or build.MASTER
    x0, w, h = a_left(p), p["ink"], p["H"]
    vb = f"{x0 - pad:.2f} {-pad:.2f} {w + 2 * pad:.2f} {h + 2 * pad:.2f}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">'
            f'<path d="{d}" fill="{fill}" fill-rule="evenodd"/></svg>')


def mark_square(fill=INK, params=None, box=100.0, inset=6.0, style=""):
    """A favicon MUST be square. The mark's own box is 84.5 x 100, so centre
    it in a square viewBox rather than letting a rasteriser produce 16x18."""
    d, _ = a_path(params)
    p = params or build.MASTER
    k = (box - 2 * inset) / p["H"]
    tx = (box - p["ink"] * k) / 2.0 - a_left(p) * k
    ty = (box - p["H"] * k) / 2.0
    fill_attr = f' fill="{fill}"' if fill else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {box:g} {box:g}">{style}'
            f'<g transform="translate({tx:.3f} {ty:.3f}) scale({k:.5f})">'
            f'<path d="{d}"{fill_attr} fill-rule="evenodd"/></g></svg>')


def favicon_svg():
    """The heavy small-size cut, rock on a light tab strip and bone on a dark
    one. A single bone favicon disappears against a light browser chrome."""
    style = (f"<style>path{{fill:{ROCK}}}@media (prefers-color-scheme:dark)"
             f"{{path{{fill:{INK}}}}}</style>")
    return mark_square(None, params=build.FAVICON, inset=5.0, style=style)


# --- the wordmark: the mark's own A, then RGUS faceted to one segment ------
def word_body(fill=INK, cap=CAP, x0=0.0, y0=0.0, track=TRACK):
    s = cap / CAP
    d, dx = a_path()
    parts = [f'<g transform="translate({x0 + dx * s:.2f} {y0 - cap:.2f}) '
             f'scale({s:.5f})"><path d="{d}" fill="{fill}" '
             f'fill-rule="evenodd"/></g>']
    x = x0 + (ADV + track) * s
    for ch in "RGUS":
        pen = wm.FacetPen(wm._gs, n=1, scale=cap / wm._cap, dx=x, dy=y0)
        wm._gs[wm._cmap[ord(ch)]].draw(pen)
        parts.append(f'<path d="{"".join(pen.parts)}" fill="{fill}"/>')
        x += (ADV + track) * s
    return "".join(parts), x - track * s - x0


def text_body(txt, fill, size, x0, y0, track=0.0, facets=6):
    s = size / wm._cap
    parts, x = [], x0
    for ch in txt:
        g = wm._cmap.get(ord(ch))
        if g is None:
            x += size * 0.6 + track
            continue
        pen = wm.FacetPen(wm._gs, n=facets, scale=s, dx=x, dy=y0)
        wm._gs[g].draw(pen)
        parts.append(f'<path d="{"".join(pen.parts)}" fill="{fill}"/>')
        x += wm._hmtx[g][0] * s + track
    return "".join(parts), x - track - x0


def wordmark_svg(fill=INK, pad=10.0):
    body, w = word_body(fill)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{-pad} {-CAP - pad} {w + 2 * pad:.2f} '
            f'{CAP + 2 * pad:.2f}">{body}</svg>')


# --- the chamfered brush: the mark's own 45-degree cut, as a container ------
def brush(x, y, w, h, c, fill, extra=""):
    """A Quake brush: a rectangle with every corner knocked off at 45 deg."""
    return (f'<path d="M{x + c} {y} L{x + w - c} {y} L{x + w} {y + c} '
            f'L{x + w} {y + h - c} L{x + w - c} {y + h} L{x + c} {y + h} '
            f'L{x} {y + h - c} L{x} {y + c} Z" fill="{fill}" {extra}/>')


def icon_tile(bg=ROCK, fg=INK, box=100.0, c=6.0):
    d, _ = a_path()
    p = build.MASTER
    s = 0.54 * box / p["H"]
    tx = (box - p["ink"] * s) / 2.0 - a_left(p) * s
    ty = (box - p["H"] * s) / 2.0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {box:g} {box:g}">'
            + brush(0, 0, box, box, c, bg)
            + f'<g transform="translate({tx:.2f} {ty:.2f}) scale({s:.5f})">'
              f'<path d="{d}" fill="{fg}" fill-rule="evenodd"/></g></svg>')


# --- the nav graph, as texture only ---------------------------------------
# Not the mark - node-link diagrams are the link icon and the share icon and
# cannot carry a logo - but it is the shape of the product's output and the
# right wallpaper for a banner. `keep_out` rectangles (texture coordinates,
# x0 y0 x1 y1) hold the type clear: no node lands in one and no link crosses
# one, so the wordmark and tagline never sit on a stray line or dot.
def _inside(x, y, r):
    return r[0] <= x <= r[2] and r[1] <= y <= r[3]


def _crosses(a, b, r, steps=48):
    return any(_inside(a[0] + (b[0] - a[0]) * i / steps,
                       a[1] + (b[1] - a[1]) * i / steps, r)
               for i in range(steps + 1))


def graph_texture(w, h, n=26, seed=7, op=0.5, keep_out=()):
    rnd = random.Random(seed)
    pts = []
    while len(pts) < n:
        x, y = rnd.uniform(0.04 * w, 0.96 * w), rnd.uniform(0.08 * h, 0.92 * h)
        if not any(_inside(x, y, r) for r in keep_out):
            pts.append((x, y))
    out = [f'<g opacity="{op}">']
    for i, (x, y) in enumerate(pts):
        near = sorted(range(n), key=lambda j: (pts[j][0] - x) ** 2
                      + (pts[j][1] - y) ** 2)[1:3]
        for j in near:
            if j <= i:
                continue
            typ = rnd.random()
            if any(_crosses(pts[i], pts[j], r) for r in keep_out):
                continue
            col, dash = (LINE, "") if typ < .55 else \
                ((MUTED, ' stroke-dasharray="1 7"') if typ < .8
                 else (ACCENT, ' stroke-dasharray="7 6"'))
            out.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{pts[j][0]:.1f}" '
                       f'y2="{pts[j][1]:.1f}" stroke="{col}" '
                       f'stroke-width="1.6"{dash}/>')
    for x, y in pts:
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{MUTED}"/>')
    out.append('</g>')
    return "".join(out)


# --- lockups ---------------------------------------------------------------
# Wordmark over tagline only. The mark IS the wordmark's A, so setting the
# two side by side reads "A ARGUS": there is no combined lockup.
def header(bg, fg, sub=MUTED, W=760.0):
    body, ww = word_body(fg, cap=96.0, x0=0, y0=0)
    tb, tw = text_body(TAG, sub, 13.0, 0, 0, track=2.6)
    H = 230.0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:g} {H:g}">'
            + (f'<rect width="{W:g}" height="{H:g}" fill="{bg}"/>' if bg else "")
            + f'<g transform="translate({(W - ww) / 2:.2f} 130)">{body}</g>'
            + f'<path d="M{(W - ww) / 2:.0f} 158 L{(W + ww) / 2:.0f} 158" '
              f'stroke="{fg}" stroke-opacity="0.25" stroke-width="2"/>'
            + f'<g transform="translate({(W - tw) / 2:.2f} 186)">{tb}</g>'
            + '</svg>')


def banner(w=1280.0, h=400.0, bg=ROCK, fg=INK, sub=MUTED, rule=LINE):
    body, ww = word_body(fg, cap=118.0, x0=0, y0=0)
    tb, tw = text_body(TAG, sub, 15.0, 0, 0, track=3.4)
    gx = w * 0.58
    keep_out = [(84 - 14 - gx, 300 - 15 - 14, 84 + tw + 14 - gx, 300 + 14)]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}">'
            f'<rect width="{w:g}" height="{h:g}" fill="{bg}"/>'
            f'<g transform="translate({gx:.0f} 0)">'
            f'{graph_texture(w - gx, h, n=24, seed=11, op=0.62, keep_out=keep_out)}'
            f'</g>'
            f'<g transform="translate(84 232)">{body}</g>'
            f'<path d="M84 268 L{84 + ww:.0f} 268" stroke="{rule}" '
            f'stroke-width="2"/>'
            f'<g transform="translate(84 300)">{tb}</g>'
            + brush(84, 58, 58, 12, 5, ACCENT) +
            f'</svg>')


def social(w=1280.0, h=640.0):
    """1280 x 640, the size GitHub asks for in a repository social preview."""
    wcap = 132.0
    body, ww = word_body(INK, cap=wcap, x0=0, y0=0)
    tb, tw = text_body(TAG, MUTED, 17.0, 0, 0, track=3.8)
    wy, ry, ty = h / 2 + 44, h / 2 + 78, h / 2 + 116
    by = h / 2 - 150
    keep_out = [
        ((w - ww) / 2 - 28, wy - wcap - 28, (w + ww) / 2 + 28, ry + 14),
        ((w - tw) / 2 - 18, ry - 14, (w + tw) / 2 + 18, ty + 18),
        (w / 2 - 29 - 22, by - 22, w / 2 + 29 + 22, by + 12 + 22),
    ]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}">'
            f'<rect width="{w:g}" height="{h:g}" fill="{ROCK}"/>'
            f'{graph_texture(w, h, n=44, seed=3, op=0.30, keep_out=keep_out)}'
            f'<g transform="translate({(w - ww) / 2:.2f} {wy:.0f})">'
            f'{body}</g>'
            f'<path d="M{(w - ww) / 2:.0f} {ry:.0f} '
            f'L{(w + ww) / 2:.0f} {ry:.0f}" stroke="{LINE}" '
            f'stroke-width="2"/>'
            f'<g transform="translate({(w - tw) / 2:.2f} {ty:.0f})">'
            f'{tb}</g>'
            + brush(w / 2 - 29, by, 58, 12, 5, ACCENT) +
            f'</svg>')


# the motif: the same 45-degree cut, as a container rule
def motif(w=1200.0, h=120.0):
    out = [f'<rect width="{w:g}" height="{h:g}" fill="none"/>']
    x, i = 20.0, 0
    while x < w - 60:
        bw = (150, 92, 210, 120)[i % 4]
        col = ACCENT if i % 5 == 2 else LINE
        out.append(brush(x, 34, bw, 52, 11, col))
        x += bw + 18
        i += 1
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}">'
            + "".join(out) + '</svg>')


def main():
    os.makedirs(OUT, exist_ok=True)
    built = []
    for nm, col in (("ink", INK), ("accent", ACCENT), ("rock", ROCK)):
        built.append(write(f"argus-mark-{nm}.svg", mark_svg(col)))
        built.append(write(f"argus-wordmark-{nm}.svg", wordmark_svg(col)))
    built.append(write("favicon.svg", favicon_svg()))
    built.append(write("argus-icon-tile.svg", icon_tile(ROCK, INK)))
    built.append(write("argus-icon-tile-accent.svg",
                       icon_tile(ACCENT, "#ffffff")))
    built.append(write("argus-icon-tile-light.svg", icon_tile(INK, ROCK)))
    built.append(write("argus-header-dark.svg", header(ROCK, INK)))
    built.append(write("argus-header-light.svg", header(INK, ROCK, "#6f6555")))
    built.append(write("readme-banner.svg", banner()))
    built.append(write("readme-banner-light.svg",
                       banner(bg=INK, fg=ROCK, sub="#6f6555", rule="#cabfae")))
    built.append(write("social-preview.svg", social()))
    built.append(write("argus-motif.svg", motif()))
    print("wrote", len(built), "svgs to", OUT)


if __name__ == "__main__":
    main()
