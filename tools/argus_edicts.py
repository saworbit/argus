#!/usr/bin/env python3
"""Read an `edicts` dump out of a tape.

The engine has always been able to dump its whole world. ED_PrintEdicts
walks the progs field definitions, so the dump carries OUR fields too:
ar_node, ar_goal, ar_mode, ar_door, ar_liftwait, ar_failstreak. Every
forensics session in this project has instead added a dprint and
recompiled to read one of those.

Inject `edicts` into a live match (it is on the tune whitelist) and the
dump lands in qconsole.log next to the telemetry. With no injection
channel, --make-cfg writes a config that waits and then dumps, for
`+exec`. Either way this turns the result back into something a person
can read.

The dump is lossy under load: a 236 edict dm4 dump lost four headers
to the console. Counts are approximate, field values are not.

  argus_edicts.py --make-cfg 25          arm a dump 25s into a match
  argus_edicts.py <log>                  edict pressure plus every bot
  argus_edicts.py <log> --edict 231      one edict in full
  argus_edicts.py <log> --field ar_node  one field across all bots
  argus_edicts.py <log> --all            every edict in use

A field missing from a block means it holds its default. The engine
only prints what differs from zero, so "no ar_liftwait" reads as 0.
"""
import argparse, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HEAD = re.compile(r"^EDICT (\d+):")
FIELD = re.compile(r"^([a-z_][a-z0-9_]*)\s+(\S.*)$")

# what a stuck bot is usually explained by, in the order you want to
# read them: where am I going, what am I riding, why am I not moving
STUCK = ["netname", "classname", "origin", "velocity", "health",
         "ar_isbot", "ar_mode", "ar_node", "ar_goal", "ar_pending",
         "ar_enemy", "ar_teammate", "ar_liftwait", "ar_door", "ar_doorbtn",
         "ar_hoplift", "ar_hoptrain", "ar_hopdoor", "ar_hopswim",
         "ar_hopjump", "ar_hoprj", "ar_failstreak", "ar_fetchcool",
         "ar_padcooltime", "ar_goal_count", "ar_swim", "waterlevel"]


def parse(text, which=None):
    """last dump in the file -> {index: {field: value}}

    The server keeps printing while it dumps, so ARGLOG and ARGEVT
    lines interleave with the blocks. Key on what a QC field name
    actually looks like instead of trying to detect where the dump
    ends: lowercase, underscores, digits. That excludes every
    telemetry line we emit, which are all upper case.
    """
    starts = [m.start() for m in re.finditer(r"^EDICT 0:", text, re.M)]
    if not starts:
        starts = [m.start() for m in re.finditer(r"^EDICT \d+:", text, re.M)]
        if not starts:
            return {}
    if which is None or which >= len(starts):
        which = len(starts) - 1
    end = starts[which + 1] if which + 1 < len(starts) else len(text)
    body = text[starts[which]:end]
    out, cur = {}, None
    for line in body.splitlines():
        h = HEAD.match(line)
        if h:
            cur = int(h.group(1))
            out.setdefault(cur, {})
            continue
        if cur is None or not line.strip():
            continue
        if line.strip() == "FREE":
            # A genuinely free edict prints FREE and nothing else. If
            # the current block already has fields, this FREE belongs
            # to an edict whose header never made it into the log:
            # a big dump outruns the console and headers get dropped
            # (a 236 edict dm4 dump lost EDICT 233 entirely). Claiming
            # it here marked a live bot as free.
            if not out[cur]:
                out[cur]["FREE"] = "1"
            else:
                out.setdefault("lost", 0)
                out["lost"] += 1
            continue
        m = FIELD.match(line)
        if m:
            out[cur][m.group(1)] = m.group(2).strip()
    return out


def show(idx, fields, keys=None):
    print(f"EDICT {idx}")
    for k in (keys or sorted(fields)):
        if k in fields:
            print(f"    {k:<16} {fields[k]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", nargs="?")
    ap.add_argument("--edict", type=int)
    ap.add_argument("--field")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dump", type=int, metavar="N",
                    help="which dump to read when a log holds several, "
                         "0 based. Default is the last.")
    ap.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="with --make-cfg, take N dumps that far apart. A "
                         "stochastic freeze needs several throws to be caught "
                         "in one.")
    ap.add_argument("--make-cfg", type=float, metavar="SECS",
                    help="write engine/argus/edump.cfg: wait this long, then "
                         "dump. Run the engine with +exec edump.cfg when you "
                         "have no live injection channel.")
    a = ap.parse_args()

    if a.make_cfg:
        # `wait` costs exactly one frame, and the dedicated server runs
        # at the 0.1 host_frametime clamp, so ten waits is about a
        # second. Approximate on purpose: the point is to land the dump
        # somewhere in the middle of a match rather than at spawn,
        # where every ar_ field still holds its default.
        n = max(1, int(a.make_cfg * 10))
        f = ROOT / "engine" / "argus" / "edump.cfg"
        body = ("wait\n" * n + "edicts\n") * max(1, a.repeat)
        f.write_text(body)
        at = ", ".join(f"{(i+1)*n/10:.0f}s" for i in range(max(1, a.repeat)))
        print(f"wrote {f}  ({max(1, a.repeat)} dump(s) at about {at})")
        print("then: quakespasm ... +map <map> +exec edump.cfg   (needs -condebug)")
        return

    if not a.log:
        sys.exit("give a log to read, or --make-cfg SECS to arm a dump")
    text = Path(a.log).read_text(errors="replace")
    ndumps = len(re.findall(r"^EDICT 0:", text, re.M)) or 1
    eds = parse(text, a.dump)
    lost = eds.pop("lost", 0)
    if not eds:
        sys.exit("no edicts dump in that log. Inject `edicts` during a match "
                 "(tune, or +edicts on the command line) with -condebug on.")

    used = {i: f for i, f in eds.items() if "FREE" not in f}
    print(f"{len(eds)} edicts dumped, {len(used)} in use, {len(eds)-len(used)} free "
          f"(the lab ceiling is max_edicts 600)")
    if ndumps > 1:
        print(f"log holds {ndumps} dumps; reading "
              f"{'the last' if a.dump is None else f'#{a.dump}'}")
    if lost:
        print(f"note: {lost} edict header(s) missing from the log. A dump this "
              f"size outruns the console, so counts are approximate.")

    if a.edict is not None:
        if a.edict not in eds:
            sys.exit(f"edict {a.edict} is not in this dump")
        show(a.edict, eds[a.edict])
        return

    bots = {i: f for i, f in used.items() if f.get("ar_isbot", "0").startswith("1")}
    if a.field:
        print(f"\n{a.field} across {len(bots)} bot(s):")
        for i, f in sorted(bots.items()):
            print(f"    n{i:<5} {f.get('netname','?'):<12} {f.get(a.field,'(default)')}")
        return

    if a.all:
        for i, f in sorted(used.items()):
            show(i, f)
        return

    if not bots:
        print("\nno bots in this dump (ar_isbot never set)")
        return
    print(f"\n{len(bots)} bot(s):")
    for i, f in sorted(bots.items()):
        print()
        show(i, f, STUCK)


if __name__ == "__main__":
    main()
