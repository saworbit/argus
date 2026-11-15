# The session gallery

[Back to the lab workflow](lab-workflow.md) | [Controls](controls.md#session-marks)

A session tape says where trouble happened; the session demo shows what you
saw. The gallery puts the two together: it picks the few moments of a session
worth a ruling, cuts a six-second clip of each from the demo, and serves a
local page where you mark each one **broken**, **looks wrong** or **fine**.
Two minutes of attention instead of replaying the match, and the rulings land
in a file the lab can read.

## Making one

After harvesting a session (`python tools/harvest_session.py --tag <tag>`):

```text
python tools/argus_gallery.py build <stem> --dry-run
python tools/argus_gallery.py build <stem>
python tools/argus_gallery.py serve <stem>
```

`--dry-run` lists the moments without rendering anything. `build` needs the
paired demo `runs/demos/<stem>.dem`, an `argus-mcp` binary and FFmpeg with
libvpx-vp9 (the same requirement as `argus-mcp capture-video`). `serve` opens
the page at `http://127.0.0.1:8771/`; rulings save as you click. Afterwards:

```text
python tools/argus_gallery.py verdicts <stem>
```

## What it picks

In order of importance, at most twelve (`--limit`):

1. every **mark** you pressed in the session (`bind m mark`);
2. bot **freezes while losing health**, the worst thing a player can witness;
3. bot **world deaths with no damage before them** (unforced lava or slime,
   judged the scorecard's way, which needs the map's BSP);
4. other bot **freezes** of six seconds or more.

Moments of one bot inside one clip's window share the clip. Clips run from
four seconds before a moment to two seconds after it, at normal speed.

## What it cannot show

The demo holds only what your client could see. A moment you were not looking
at may not appear in its clip at all; the page says so on every card. For a
moment the demo cannot reach, use the tape (`argus_lab.py triage`) or a
bot's-eye recording (`argus-mcp watch-pov`).

Clips are rendered from id's licensed game data, so they stay beside the demo
under `runs/demos/gallery/<stem>/`, which git ignores. They are never
committed or published. The rulings file `verdicts.json` is plain text.

The local server listens on 127.0.0.1 only, accepts rulings only from the page
it served, and keeps each note to 2,000 characters.
