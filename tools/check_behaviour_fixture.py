"""Independent behaviour-fixture acceptance and passive-observer source audit.

Does not parse or redefine ARGLOG/ARGEVT metrics. TACFIX remains the separate
movement/damage oracle; BHVFIX adds identity, cleanup and noninterference.
"""
import argparse
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD_FIELDS = """origin velocity angles v_angle health armorvalue armortype items
weapon ammo_shells ammo_nails ammo_rockets ammo_cells flags solid movetype
takedamage button0 button1 button2 attack_finished nextthink think touch th_pain
ar_enemy ar_seen ar_lastseen ar_lastfoe ar_goal ar_node ar_pending ar_shopping
ar_routegen ar_mode ar_moveyaw ar_nextai ar_nextlog ar_nextstall ar_react ar_track
ar_plan_goal ar_plan_leg ar_plan_best ar_plan_stamp ar_fetchfailed ar_fetchcool
ar_plan_visit0 ar_plan_visit1 ar_plan_visit2 ar_plan_visit3
ar_aimvel ar_aimoff ar_aimprev ar_errtime ar_aimblend ar_mottarget ar_motpos
ar_mottime ar_motoff ar_motprev ar_motblend ar_retreating ar_dodgetime
ar_tactic ar_tactic_until ar_tactic_check ar_tactic_cool ar_tactic_hop
ar_tactic_cover ar_tactic_exit ar_tactic_speed ar_hopjump ar_hoprj ar_hoplift
ar_hopswim ar_hoptrain ar_hopdoor ar_sprintstate ar_jump ar_fireready
ar_fireburst ar_fireweapon ar_sndpos ar_sndtime ar_huntitem ar_hunttime
ar_obsenemy ar_obsvelocity ar_obspower ar_obsground ar_obsair ar_secondarypos
ar_threatclass ar_threatlog ar_secondary ar_secondaryscan""".split()


def guard_source():
    definitions = {}
    for path in (ROOT / 'src').glob('*.qc'):
        for kind, names in re.findall(r'^\.(float|vector|entity|string|void\s*\([^;\n]*\))\s+([^;\n]+);', path.read_text(errors='replace'), re.M):
            for name in names.split(','):
                definitions[name.strip()] = kind
    lines = ["void() Argus_BehaviourFixtureGuard =", "{"]
    lines += [f'    local {definitions[field]} ar_bgs_{field};' for field in GUARD_FIELDS]
    lines += [
             "    local entity b, oldother, oldtrace;",
             "    local vector f, r, u, endpoint, normal;",
             "    local float fraction, allsolid, startsolid, plane, next;",
             "    b = self; oldother = other; oldtrace = trace_ent;",
             "    f = v_forward; r = v_right; u = v_up;",
             "    endpoint = trace_endpos; normal = trace_plane_normal;",
             "    fraction = trace_fraction; allsolid = trace_allsolid;",
             "    startsolid = trace_startsolid; plane = trace_plane_dist;",
             "    next = self.ar_bd_next;"]
    lines += [f"    ar_bgs_{field} = self.{field};" for field in GUARD_FIELDS]
    lines += ["    Argus_BehaviourObserve ();",
              "    ar_bf_checks = ar_bf_checks + 1;",
              "    if (self.ar_bd_next != next) ar_bf_emits = ar_bf_emits + 1;",
              "    if (self != b || other != oldother || trace_ent != oldtrace",
              "        || v_forward != f || v_right != r || v_up != u",
              "        || trace_endpos != endpoint || trace_plane_normal != normal",
              "        || trace_fraction != fraction || trace_allsolid != allsolid",
              "        || trace_startsolid != startsolid || trace_plane_dist != plane)",
              "        ar_bf_guardok = 0;"]
    lines += [f"    if (b.{field} != ar_bgs_{field}) ar_bf_guardok = 0;" for field in GUARD_FIELDS]
    lines += ["};"]
    return "\n".join(lines) + "\n"


def audit_observer(source):
    declaration = 'void(string a, string b, string c) Argus_BehaviourPrint = #25;'
    assert source.count(declaration) == 1, 'observer print must remain vanilla builtin 25'
    code = re.sub(r"//[^\n]*|/\*.*?\*/", "", source, flags=re.S)
    code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
    allowed = {"void", "if", "ftos", "vtos", "dprint", "vlen", "cvar",
               "Argus_BehaviourObserve", "Argus_BehaviourReset", "Argus_BehaviourEvent",
               "Argus_BehaviourPrint"}
    calls = set(re.findall(r"\b(\w+)\s*\(", code))
    assert not calls - allowed, f"observer has impure/unknown calls: {sorted(calls - allowed)}"
    for lhs in re.findall(r"\b(\w+\.\w+)\s*=(?!=)", code):
        assert lhs.startswith("self.ar_bd_"), f"observer writes gameplay field {lhs}"
    locals_ = {"source", "intent", "reason", "dist", "gain", "moved", "mode"}
    for lhs in re.findall(r"(?<![.\w])([A-Za-z_]\w*)\s*=(?!=)", code):
        assert lhs in locals_ or lhs in allowed, f"observer writes global {lhs}"
    assert "ARGEVT" not in source and "ARGLOG" not in source, "observer changes established telemetry"


def audit_timing(source):
    match = re.search(r'void\(\) Argus_BehaviourTiming =\s*\{(.*?)\n\};', source, re.S)
    assert match, 'missing ordinary cadence probe'
    code = re.sub(r'//[^\n]*|"(?:\\.|[^"\\])*"', '', match[1])
    calls = set(re.findall(r'\b(\w+)\s*\(', code))
    assert calls <= {'if', 'cvar', 'ftos', 'Argus_BehaviourPrint'}, 'cadence probe has impure calls'
    assert not re.search(r'\b\w+\.\w+\s*=(?!=)', code), 'cadence probe writes an entity field'
    for lhs in re.findall(r'(?<![.\w])([A-Za-z_]\w*)\s*=(?!=)', code):
        assert lhs.startswith('ar_bt_'), 'cadence probe writes gameplay global'


def audit_diagnostic_ownership(sources):
    for name, source in sources.items():
        if name in {'argus_behaviour.qc', 'argus_behaviour_fixture.qc'}:
            continue
        code = re.sub(r'"(?:\\.|[^"\\])*"', '', source)
        code = re.sub(r'//[^\n]*|/\*.*?\*/', '', code, flags=re.S)
        assert not re.search(r'\bar_b[dt]_\w+', code), f'gameplay depends on diagnostic state: {name}'


def check(text, *, diagnostics, expected=None, hz=None):
    assert not any(s in text for s in ("Host_Error", "runaway loop error", "BHVFIX refused")), "engine/fixture error"
    lines = text.splitlines()
    results = []
    active = None
    for index, line in enumerate(lines):
        if not line.startswith("BHVFIX "):
            continue
        words = line.split()
        kind = words[1]
        if kind in {"ready", "server_ready"}:
            continue
        if kind == "begin":
            assert active is None and len(words) == 5 and words[3] == "case", "overlapping/malformed begin"
            assert words[2] in {"dm2", "dm4"}, "wrong map"
            active = dict(map=words[2], case=int(words[4]), samples=[], guards=[], busy=0, start=index)
        elif kind == "trial":
            assert active and "id" not in active and words[3:] == ["case", str(active["case"])], "wrong/duplicate trial"
            active["id"] = int(words[2])
            assert active["id"] == len(results) + 1, "wrong trial ID"
        elif kind == "busy":
            assert active and "id" in active and words[2:] == ["id", str(active["id"]), "requested", str(active["id"])], "wrong overlap"
            active["busy"] += 1
        elif kind == "sample":
            assert active and "id" in active and "frames" not in active, "sample outside live trial"
            assert len(active['guards']) == len(active['samples']), 'missing sample guard'
            m = re.fullmatch(r"BHVFIX sample\s+([\d.]+) pos '([^']+)' visible\s+([01]) launches\s+(\d+) targethp\s+([\d.-]+) hp\s+([\d.-]+) invariant\s+([01])", line)
            assert m, "malformed independent sample"
            t, position, visible, launches, hp, bot_hp, invariant = m.groups()
            row = dict(t=float(t), pos=list(map(float, position.split())), visible=int(visible), launches=int(launches), hp=float(hp), bot_hp=float(bot_hp))
            assert len(row["pos"]) == 3 and all(math.isfinite(v) for v in [row["t"], row["hp"], row["bot_hp"], *row["pos"]]), "nonfinite sample"
            assert invariant == "1", "observer changed gameplay/engine state"
            if active["samples"]:
                prev = active["samples"][-1]
                # Vanilla ftos rounds to tenths: adjacent real frames may tie.
                # The exact increasing guard-check serial below proves order.
                assert row["t"] >= prev["t"] and row["launches"] >= prev["launches"], "reordered sample/projectile count"
            active["samples"].append(row)
        elif kind == "end":
            assert active and "frames" not in active and words[2] == "frames" and words[4] == "seconds", "missing/duplicate end"
            assert len(active['guards']) == len(active['samples']), 'missing final sample guard'
            active["frames"], active["seconds"] = int(words[3]), float(words[5])
            assert active["frames"] > 0 and 5.9 <= active["seconds"] <= 6.2, "fixture deadline/cadence invalid"
        elif kind == "guard":
            assert active and "frames" not in active and words[2] == "checks" and words[4] == "emits", "misplaced guard record"
            assert len(active['samples']) == len(active['guards']) + 1, 'duplicate/unpaired guard'
            active['checks'], active['emits'] = int(words[3]), int(words[5])
            assert active['checks'] > (active['guards'][-1][0] if active['guards'] else 0), 'reordered/duplicate frame guard'
            assert 0 <= active['emits'] <= active['checks'], 'invalid emission counter'
            assert not active['guards'] or active['emits'] >= active['guards'][-1][1], 'reordered emission counter'
            active['guards'].append((active['checks'], active['emits']))
        elif kind == "cleanup":
            assert active and "frames" in active and not active.get("clean"), "premature/duplicate cleanup"
            assert words[2:] == [str(active["id"]), "restored", "1", "invariant", "1"], "cleanup or state guard failed"
            active["clean"] = True
        elif kind == "done":
            assert active and active.get("clean") and words[2:] == [str(active["id"])], "missing/wrong cleanup acknowledgement"
            assert active["samples"] and active["samples"][-1]["t"] >= 5.5, "truncated observer"
            assert active.get('checks', 0) > 0, "no guarded observer calls"
            assert (active.get('emits', 0) > 0) == diagnostics, "guard never exercised enabled observer"
            assert active["busy"] == (1 if active["case"] == 9 else 0), "overlap refusal mismatch"
            block = "\n".join(lines[active["start"]:index + 1])
            assert ("BHVDBG " in block) == diagnostics, "diagnostics arm mismatch"
            fps = active["frames"] / active["seconds"]
            if hz is not None:
                assert abs(fps - hz) <= hz * 0.1, "measured cadence differs from requested class"
            active["fps"] = round(fps, 2)
            results.append(active)
            active = None
        else:
            raise AssertionError(f"unknown fixture record: {line}")
    assert active is None and results, "missing end/done acknowledgement"
    if expected is not None:
        assert [r["case"] for r in results] == expected, "missing, duplicate or reordered cases"
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log", type=Path, nargs="?")
    ap.add_argument("--diagnostics", choices=["on", "off"], default="on")
    ap.add_argument("--cases", default="0,0,0,1,2,3,4,5,6,7,8,9,10,11,12")
    ap.add_argument("--hz", type=float)
    ap.add_argument("--write-guard", action="store_true")
    args = ap.parse_args()
    audit_observer((ROOT / "src/argus_behaviour.qc").read_text())
    audit_diagnostic_ownership({p.relative_to(ROOT / 'src').as_posix(): p.read_text()
                                for p in (ROOT / 'src').rglob('*.qc')})
    guard = ROOT / "src/argus_behaviour_fixture.qc"
    current = guard.read_text()
    audit_timing(current)
    generated = re.sub(r"(?<=// BEGIN observer guard\n).*?(?=// END observer guard)", guard_source(), current, flags=re.S)
    if args.write_guard:
        guard.write_text(generated, newline="\r\n")
    else:
        assert current == generated, "observer guard is stale"
    if args.log:
        data = check(args.log.read_text(errors="replace"), diagnostics=args.diagnostics == "on", expected=list(map(int, args.cases.split(','))), hz=args.hz)
        print(json.dumps([{k: v for k, v in r.items() if k not in {"samples", "start"}} for r in data], indent=2))
