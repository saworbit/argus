"""Publish optional navigation previews with graph-associated freshness receipts."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import tempfile


def draw_nav_graph(ax, nav, *, alpha=0.8, linewidth=1.2, legend=False):
    """Draw the final sidecar once per family, with typed links over plain ones."""
    from argus_linkstyle import REFUSAL, WAYPOINT, mpl, walk_kind
    from argus_navjson import FAMILIES, pairs
    nodes = nav['nodes']
    families = {'jlinks': 'jump', 'teles': 'tele', 'rjlinks': 'rocket',
                'liftlinks': 'lift', 'swimlinks': 'swim', 'doorlinks': 'door',
                'trainlinks': 'train', 'sprintlinks': 'sprint'}
    typed = set(pairs(nav, tuple(families)))
    counts = Counter()
    for family in FAMILIES:
        for source, target in pairs(nav, (family,)):
            if family == 'links' and (source, target) in typed:
                continue
            a, b = nodes[source], nodes[target]
            kind = families.get(family) or walk_kind(a, b)
            label = kind if legend and not counts[kind] else None
            ax.plot([a[0], b[0]], [a[1], b[1]], lw=linewidth, alpha=alpha,
                    zorder=2, label=label, **mpl(kind))
            counts[kind] += 1
    for rejected in nav.get('probe_rejected', []):
        a, b = rejected['from'], rejected['to']
        ax.plot([a[0], b[0]], [a[1], b[1]], color=REFUSAL[0], lw=2,
                ls=(0, REFUSAL[2]), zorder=4)
        ax.scatter([b[0]], [b[1]], s=34, marker='x', c=REFUSAL[0], zorder=5)
    ax.scatter([p[0] for p in nodes], [p[1] for p in nodes], s=16,
               c=WAYPOINT[0], alpha=alpha, zorder=3)
    return counts


def render_graph(bsp, mapname, qc, png):
    """Render the shipped/final JSON without sampling or rewriting navigation."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from analyze_match import load_bsp
    from argus_navjson import load_nav
    from argus_linkstyle import LINK_STYLES
    nav = load_nav(str(qc) + '.json')
    verts, edges, _, _ = load_bsp(bsp)
    fig, ax = plt.subplots(figsize=(12, 12))
    try:
        for a, b in edges[1:]:
            if a < len(verts) and b < len(verts):
                ax.plot([verts[a][0], verts[b][0]], [verts[a][1], verts[b][1]],
                        color='0.88', lw=0.3, zorder=1)
        counts = draw_nav_graph(ax, nav, legend=True)
        ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"Argus nav graph - {mapname}: {len(nav['nodes'])} nodes, "
                     f"{sum(counts.values())} links\n" +
                     ', '.join(f'{counts[k]} {k}' for k in LINK_STYLES), fontsize=10)
        if counts:
            ax.legend(loc='upper right', fontsize=8)
        fig.tight_layout()
        fig.savefig(png, dpi=130)
    finally:
        plt.close(fig)


def render_only(bsp, mapname, qc, png):
    """Write only a PNG and its freshness receipt; refuse input aliases."""
    qc, png = Path(qc), Path(png)
    inputs = {Path(bsp).resolve(), qc.resolve(), Path(str(qc) + '.json').resolve()}
    if png.suffix.lower() != '.png' or inputs & {png.resolve(), Path(str(png) + '.json').resolve()}:
        raise ValueError('render-only needs a .png output distinct from every input')
    png.parent.mkdir(parents=True, exist_ok=True)
    return generate_preview(qc, png, lambda out: render_graph(bsp, mapname, qc, out))


def file_md5(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def generate_preview(qc, png, render):
    """Keep graph generation successful when plotting is unavailable or fails."""
    qc, png = Path(qc), Path(png)
    receipt = Path(str(png) + '.json')
    state = dict(schema='nav-preview-v1', generated=False, qc_md5=file_md5(qc),
                 graph_md5=file_md5(Path(str(qc) + '.json')))
    # Invalidate the old preview before importing or invoking the plotter.
    receipt.write_text(json.dumps(state) + '\n', encoding='utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=png.parent, suffix='.png', delete=False) as owned:
            temporary = Path(owned.name)
        render(temporary)
        if not temporary.stat().st_size:
            raise ValueError('plotter produced an empty preview')
        temporary.replace(png)
        state.update(generated=True, png_md5=file_md5(png))
        receipt.write_text(json.dumps(state) + '\n', encoding='utf-8')
        print('wrote', png)
    except Exception as error:
        state['generated'] = False
        print(f'debug plot skipped: {type(error).__name__}: {error} '
              '(nav QC and json are written and valid)')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return state['generated']
