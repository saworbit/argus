#!/usr/bin/env python3
"""The suspect-moment gallery: the few seconds of a session worth a human look.

A session tape says where trouble happened; the paired demo shows what the
player saw. This tool picks the moments worth a ruling, cuts a short clip of
each from the demo, and serves a local page where the player watches them and
marks each one broken, wrong-looking or fine. Two minutes of attention
instead of a replayed session, and the rulings land in a file the lab reads.

Moments, in the order they are shown:
  1. every session mark (`bind m mark` in game: ARGUS mark lines);
  2. bot freezes while losing health (the worst thing a player can witness);
  3. bot world deaths with no damage before them (unforced lava or slime);
  4. other bot freezes of 6 s or more.
At most --limit moments (default 12). Clips run from 4 s before a moment to
2 s after it, at normal speed, from the player's own view. A moment the
player was not looking at may not show at all: the demo holds only what the
recording client could see, and the page says so.

Clips are rendered from id's licensed game data, so they live with the demo
under runs/demos/ (machine-local, gitignored) and are never committed or
published. The verdicts file is plain text and may be committed.

usage:
  argus_gallery.py build STEM [--limit N] [--dry-run]   pick moments, cut clips, write the page
  argus_gallery.py serve STEM [--port N]                 open the page and record rulings
  argus_gallery.py verdicts STEM [--json]                print the recorded rulings
"""
import argparse
import html
import http.server
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import argus_longi  # noqa: E402
import argus_tape  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BEFORE, AFTER = 4.0, 2.0
VERDICTS = ('broken', 'looks wrong', 'fine')


def gallery_dir(root, stem):
    return Path(root) / 'runs' / 'demos' / 'gallery' / stem


def lab_binary(root):
    env = os.environ.get('ARGUS_LAB')
    if env and Path(env).is_file():
        return env
    for rel in ('tools/argus_mcp/target/release/argus-mcp.exe', 'tools/argus_mcp/target/debug/argus-mcp.exe',
                'tools/argus_mcp/target/release/argus-mcp', 'tools/argus_mcp/target/debug/argus-mcp',
                'tools/argus_mcp/install/bin/argus-mcp.exe', 'tools/argus_mcp/install/bin/argus-mcp'):
        if (Path(root) / rel).is_file():
            return str(Path(root) / rel)
    return shutil.which('argus-mcp')


def moments(text, limit=12, contents=None):
    """The moments of one tape worth a look, most important first.

    `contents` is the map's hull-0 classifier (argus_longi._classifier); with
    it a world death is split into unforced and forced the scorecard's way,
    and without it every world death is shown as one.
    """
    tape = argus_tape.parse_tape(text)
    ident = argus_tape.identity('\n'.join(line for _, line in tape.lines))
    bots, _, _ = argus_tape.track_names(tape.samples, tape.events)
    found = []
    for m in ident['marks']:
        who = m['near'] or 'no bot alive'
        found.append(dict(t=m['t'], kind='mark', rank=0, bot=m['near'],
                          note=f'mark {m["n"]}: you pressed mark near {who}'
                               + (f' ({"in sight" if m["seen"] else "out of sight"}, {m["dist"]:.0f}u)'
                                  if m['seen'] is not None else ''),
                          pos=list(m['pos'])))
    for name in bots:
        track = sorted(tape.samples.get(name, []), key=lambda r: r['line'])
        for f in argus_tape.freeze_windows(track):
            fire = f.hp_drop > 0
            found.append(dict(t=f.start['t'], kind='freeze under fire' if fire else 'freeze', rank=1 if fire else 3,
                              bot=name, note=f'{name} stood still {f.dur:.1f} s'
                                             + (f' losing {f.hp_drop:.0f} health' if fire else ''),
                              pos=[f.start['x'], f.start['y'], f.start['z']]))
        born = 0
        for line, who, verb, rest in tape.events:
            if who != name:
                continue
            if verb in ('spawned', 'respawn'):
                born = line
                continue
            if verb != 'death':
                continue
            d = next(iter(argus_tape.deaths([(line, who, verb, rest)])), None)
            life = [r for r in track if born < r['line'] < line]
            born = line
            if d is None or d[2] != 'world' or not life:
                continue
            pos = dict(x=d[3], y=d[4], z=d[5])
            unforced = argus_longi.world_death_unforced(life, contents, pos) if contents else None
            kind = {True: 'unforced world death', False: 'world death'}.get(unforced, 'world death')
            found.append(dict(t=life[-1]['t'], kind=kind, rank=2 if unforced else 4, bot=name,
                              note=f'{name} died to the world' + (' unhurt' if unforced else ''),
                              pos=[d[3], d[4], d[5]]))
    found.sort(key=lambda m: (m['rank'], m['t']))
    picked = []
    for m in found:
        # one clip covers anything within its own window
        if any(abs(m['t'] - p['t']) < (BEFORE + AFTER) / 2 and m['bot'] == p['bot'] for p in picked):
            continue
        picked.append(m)
        if len(picked) >= limit:
            break
    picked.sort(key=lambda m: m['t'])
    for i, m in enumerate(picked, 1):
        m['id'] = i
    return picked


def classifier(root, mapname):
    """The map's hull-0 contents classifier, or None without its BSP."""
    if not mapname:
        return None
    for base in (Path(root), Path(root) / '..'):
        bsp = base / 'maps_local' / f'{mapname}.bsp'
        if bsp.is_file():
            return argus_longi._classifier(str(bsp))
    return None


def demo_start(root, stem, lab):
    """Server time of the demo's first message, so tape time maps to demo seconds."""
    out = subprocess.run([lab, 'demo', stem], capture_output=True, text=True, cwd=root, timeout=300)
    if out.returncode != 0:
        raise SystemExit(f'argus-mcp demo {stem} failed: {out.stderr.strip() or out.stdout.strip()}')
    brief = json.loads(out.stdout)
    brief = brief.get('brief', brief)
    return float(brief.get('start_time', 0.0)), float(brief['duration_sec'])


def build(root, stem, limit=12, dry_run=False, out=None):
    out = out or sys.stdout
    root = Path(root)
    tape_path = root / 'runs' / f'{stem}.log'
    demo_path = root / 'runs' / 'demos' / f'{stem}.dem'
    if not tape_path.is_file():
        raise SystemExit(f'no tape runs/{stem}.log')
    text = tape_path.read_text(encoding='utf-8', errors='replace')
    picked = moments(text, limit, classifier(root, argus_tape.map_name(text)))
    print(f'{len(picked)} moment(s) in {stem}', file=out)
    for m in picked:
        print(f'  {m["id"]:2d}  t {m["t"]:6.1f}  {m["kind"]:22s} {m["note"]}', file=out)
    if dry_run or not picked:
        return picked
    if not demo_path.is_file():
        raise SystemExit(f'no paired demo runs/demos/{stem}.dem: the gallery needs the session demo')
    lab = lab_binary(root)
    if not lab:
        raise SystemExit('no argus-mcp binary; build it or set ARGUS_LAB')
    start_time, duration = demo_start(root, stem, lab)
    gdir = gallery_dir(root, stem)
    gdir.mkdir(parents=True, exist_ok=True)
    for m in picked:
        rel = m['t'] - start_time
        begin = max(0.5, rel - BEFORE)
        length = min(BEFORE + AFTER, duration - 0.3 - begin)
        m['demo_start'] = round(begin, 2)
        if length < 1.0 or begin > 900.0:
            m['clip'] = None
            m['clip_error'] = 'outside the demo'
            continue
        res = subprocess.run([lab, 'capture-video', stem, f'{begin:.2f}', f'{length:.2f}', '1'],
                             capture_output=True, text=True, cwd=root, timeout=600)
        if res.returncode != 0:
            m['clip'] = None
            m['clip_error'] = (res.stderr.strip() or res.stdout.strip())[-300:]
            print(f'  clip {m["id"]}: failed: {m["clip_error"]}', file=out)
            continue
        video = Path(json.loads(res.stdout)['video_path'])
        dest = gdir / f'clip{m["id"]:02d}.webm'
        shutil.copyfile(video, dest)
        m['clip'] = dest.name
        print(f'  clip {m["id"]}: {dest.name}', file=out)
    (gdir / 'moments.json').write_text(json.dumps(dict(stem=stem, moments=picked), indent=2), encoding='utf-8')
    (gdir / 'index.html').write_text(page(stem, picked), encoding='utf-8')
    print(f'gallery written to {gdir}; open it with: python tools/argus_gallery.py serve {stem}', file=out)
    return picked


def page(stem, picked):
    cards = []
    for m in picked:
        clip = (f'<video src="{html.escape(m["clip"])}" controls loop muted playsinline preload="metadata"></video>'
                if m.get('clip') else f'<p class="missing">No clip: {html.escape(m.get("clip_error") or "")}</p>')
        buttons = ''.join(f'<button type="button" data-v="{v}">{v}</button>' for v in VERDICTS)
        cards.append(f'''<article class="card" data-id="{m['id']}">
  <header><span class="n">{m['id']}</span><span class="kind">{html.escape(m['kind'])}</span>
  <span class="t">t {m['t']:.1f}</span></header>
  {clip}
  <p class="note">{html.escape(m['note'])}</p>
  <p class="where">at {' '.join(str(round(v)) for v in m['pos'])}</p>
  <div class="verdict">{buttons}</div>
  <textarea placeholder="What did you see? (optional)"></textarea>
</article>''')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Session gallery</title>
<style>
:root {{ --bg:#f6f5f2; --panel:#ffffff; --ink:#1d1d1b; --muted:#6b6a66; --line:#d9d6cf; --accent:#b4441f;
        --broken:#b4231f; --wrong:#b7791f; --fine:#2f7d4f; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --panel:#1f1e1c; --ink:#ecebe7; --muted:#a3a19b;
        --line:#3a3935; --accent:#e07a52; }} }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.45 system-ui, sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:24px 16px 64px; }}
h1 {{ font-size:22px; margin:0 0 4px; }}
.sub {{ color:var(--muted); margin:0 0 20px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:16px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; }}
.card header {{ display:flex; gap:10px; align-items:baseline; margin-bottom:8px; }}
.n {{ font-weight:700; color:var(--accent); }} .t {{ margin-left:auto; color:var(--muted); font-variant-numeric:tabular-nums; }}
video {{ width:100%; border-radius:6px; background:#000; aspect-ratio:4/3; }}
.note {{ margin:8px 0 2px; }} .where {{ margin:0 0 8px; color:var(--muted); font-size:13px; }}
.missing {{ color:var(--muted); font-style:italic; }}
.verdict {{ display:flex; gap:8px; margin-bottom:8px; }}
.verdict button {{ flex:1; padding:8px; border:1px solid var(--line); border-radius:6px; background:transparent;
  color:var(--ink); font:inherit; cursor:pointer; }}
.verdict button.on[data-v="broken"] {{ background:var(--broken); color:#fff; border-color:var(--broken); }}
.verdict button.on[data-v="looks wrong"] {{ background:var(--wrong); color:#fff; border-color:var(--wrong); }}
.verdict button.on[data-v="fine"] {{ background:var(--fine); color:#fff; border-color:var(--fine); }}
textarea {{ width:100%; box-sizing:border-box; min-height:48px; border:1px solid var(--line); border-radius:6px;
  background:transparent; color:var(--ink); font:inherit; padding:6px; }}
#status {{ position:sticky; top:0; background:var(--bg); padding:8px 0; color:var(--muted); }}
</style></head>
<body><main>
<h1>Session gallery</h1>
<p class="sub">{html.escape(stem)}: {len(picked)} moment(s). Each clip runs from 4 s before the moment to 2 s
after it, from your own view, so a moment you were not looking at may not show. Mark each one; rulings save
as you click.</p>
<div id="status">Not saved yet.</div>
<section class="grid">
{''.join(cards)}
</section>
</main>
<script>
const status = document.getElementById('status');
const state = {{}};
function collect() {{
  document.querySelectorAll('.card').forEach(c => {{
    const id = c.dataset.id;
    const on = c.querySelector('button.on');
    state[id] = {{ verdict: on ? on.dataset.v : null, note: c.querySelector('textarea').value }};
  }});
  return state;
}}
async function save() {{
  try {{
    const r = await fetch('verdicts', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
                                       body: JSON.stringify(collect()) }});
    status.textContent = r.ok ? 'Saved.' : 'Could not save: ' + r.status;
  }} catch (e) {{ status.textContent = 'Could not save (open this page with argus_gallery.py serve).'; }}
}}
document.querySelectorAll('.card').forEach(c => {{
  c.querySelectorAll('.verdict button').forEach(b => b.addEventListener('click', () => {{
    c.querySelectorAll('.verdict button').forEach(x => x.classList.toggle('on', x === b));
    save();
  }}));
  c.querySelector('textarea').addEventListener('change', save);
}});
fetch('verdicts').then(r => r.ok ? r.json() : {{}}).then(saved => {{
  for (const [id, v] of Object.entries(saved || {{}})) {{
    const c = document.querySelector(`.card[data-id="${{id}}"]`);
    if (!c) continue;
    if (v.verdict) c.querySelectorAll('.verdict button').forEach(x => x.classList.toggle('on', x.dataset.v === v.verdict));
    c.querySelector('textarea').value = v.note || '';
  }}
  status.textContent = Object.keys(saved || {{}}).length ? 'Loaded saved rulings.' : 'Not saved yet.';
}}).catch(() => {{}});
</script>
</body></html>
'''


def make_handler(gdir):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(gdir), **kw)

        def log_message(self, *a):
            pass

        def local_host(self):
            """The Host header names this server, so a rebound DNS name cannot reach it."""
            port = self.server.server_address[1]
            return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

        def do_GET(self):
            if not self.local_host():
                self.send_error(403)
                return
            if self.path.split('?')[0] == '/verdicts':
                path = gdir / 'verdicts.json'
                body = path.read_bytes() if path.is_file() else b'{}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def do_POST(self):
            if self.path.split('?')[0] != '/verdicts':
                self.send_error(404)
                return
            # same-origin only: the page posts back to the server that served
            # it, under a Host this server answers to
            origin = self.headers.get('Origin')
            if not self.local_host() or (origin and origin != f'http://{self.headers.get("Host")}'):
                self.send_error(403)
                return
            if (self.headers.get('Content-Type') or '').split(';')[0].strip() != 'application/json':
                self.send_error(415)
                return
            try:
                length = max(0, int(self.headers.get('Content-Length') or 0))
            except ValueError:
                self.send_error(400)
                return
            if length > 1 << 20:
                self.send_error(413)
                return
            try:
                data = json.loads(self.rfile.read(length) or b'{}')
                clean = {str(int(k)): dict(verdict=v.get('verdict') if v.get('verdict') in VERDICTS else None,
                                           note=str(v.get('note') or '')[:2000])
                         for k, v in data.items()}
            except (ValueError, AttributeError, TypeError):
                self.send_error(400)
                return
            (gdir / 'verdicts.json').write_text(json.dumps(clean, indent=2), encoding='utf-8')
            self.send_response(204)
            self.end_headers()
    return Handler


def serve(root, stem, port=8771, open_browser=True):
    gdir = gallery_dir(root, stem)
    if not (gdir / 'index.html').is_file():
        raise SystemExit(f'no gallery for {stem}; run: python tools/argus_gallery.py build {stem}')
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', port), make_handler(gdir))
    url = f'http://127.0.0.1:{port}/'
    print(f'serving {gdir} at {url} (Ctrl+C to stop)')
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


def verdicts(root, stem):
    gdir = gallery_dir(root, stem)
    moments_ = json.loads((gdir / 'moments.json').read_text(encoding='utf-8'))['moments']
    saved = json.loads((gdir / 'verdicts.json').read_text(encoding='utf-8')) if (gdir / 'verdicts.json').is_file() else {}
    rows = []
    for m in moments_:
        v = saved.get(str(m['id'])) or {}
        rows.append(dict(id=m['id'], t=m['t'], kind=m['kind'], bot=m['bot'], pos=m['pos'], note=m['note'],
                         verdict=v.get('verdict'), comment=v.get('note') or ''))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default=str(ROOT))
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build', help='pick moments, cut clips, write the page')
    b.add_argument('stem')
    b.add_argument('--limit', type=int, default=12)
    b.add_argument('--dry-run', action='store_true', help='list the moments only')
    s = sub.add_parser('serve', help='open the page and record rulings')
    s.add_argument('stem')
    s.add_argument('--port', type=int, default=8771)
    s.add_argument('--no-browser', action='store_true')
    v = sub.add_parser('verdicts', help='print the recorded rulings')
    v.add_argument('stem')
    v.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)
    root = Path(args.root)
    if args.cmd == 'build':
        build(root, args.stem, args.limit, args.dry_run)
    elif args.cmd == 'serve':
        serve(root, args.stem, args.port, not args.no_browser)
    else:
        rows = verdicts(root, args.stem)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for r in rows:
                print(f'{r["id"]:2d} t {r["t"]:6.1f} {r["kind"]:22s} {r["verdict"] or "unruled":12s} {r["note"]}'
                      + (f' | {r["comment"]}' if r['comment'] else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
