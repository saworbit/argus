"""Assert real-engine outcomes from the opt-in TACFIX observer."""
import argparse
import json
import math
import re
from pathlib import Path

SAMPLE = re.compile(r"TACFIX sample\s+([\d.]+) pos '([^']+)' hidden\s+(\d+) rockets\s+([\d.-]+) targethp\s+([\d.-]+) hp\s+([\d.-]+) state\s+(\d+)")

def check(text):
    assert "Host_Error" not in text and "runaway loop error" not in text, "engine error in fixture tape"
    results = []
    blocks = text.split("TACFIX begin ")
    for index, block in enumerate(blocks[1:]):
        name, _, case = block.splitlines()[0].split()
        if case == "13":
            # The factory proves the hull immediately before its begin line.
            # Bind that proof to this trial's preamble, not a previous trial.
            assert re.findall(r'^TACFIX hull (ok|FAILED)$', blocks[index], re.M) == ['ok'], "missing or failed asymmetric hull proof"
        rows = [dict(t=float(m[1]), p=list(map(float, m[2].split())), hidden=int(m[3]), rockets=float(m[4]), hp=float(m[5]), bot_hp=float(m[6]), state=int(m[7])) for m in SAMPLE.finditer(block)]
        launch_counts = re.findall(r"state\s+\d+ launches\s+(\d+)", block)
        shot_field = "launches" if launch_counts else "rockets"
        if launch_counts:
            assert len(launch_counts) == len(rows), "incomplete projectile observer"
            for row, count in zip(rows, launch_counts):
                row["launches"] = int(count)
        def fired(prev, row):
            return row[shot_field] > prev[shot_field] if shot_field == "launches" else row[shot_field] < prev[shot_field]
        assert rows and "TACFIX end" in block, "incomplete fixture"
        velocities = re.findall(r"targetvel '([^']+)'", block)
        if velocities:
            assert len(velocities) == len(rows) and all(math.dist(list(map(float, v.split())), (0, 0, 0)) < 0.01 for v in velocities), "fixed target retained knockback velocity"
        origin, enemy = ((465, -279, -104), (337, -247, -296)) if name == "dm4" else ((2209, -279, 24), (2433, -183, 24))
        if case == "14":
            assert "TACFIX lifeaccepted 1" in block, "failed-life GOAP or route cancellation regression"
            results.append(dict(map=name, case=case, lifeveto_checks=True))
        elif case == "6":
            # Include the settling window AFTER ownership ends. Rejecting an
            # unsafe entry leaves ordinary combat in control of legal drops.
            active = [r for r in rows if r["state"]]
            if active:
                end = next((r["t"] for r in rows if r["t"] > active[-1]["t"]), None)
                assert end is not None and rows[-1]["t"] >= end + 0.5, "missing post-tactic observation"
                assert all(abs(r["p"][2] - origin[2]) < 8 and r["bot_hp"] > 0 for r in rows if r["t"] <= end + 0.5), f"{name}: moving entry fell during or after ownership"
                assert "tactic returnshot" in block or "tactic abort" in block
                results.append(dict(map=name, case=case, moving_entry_safe=True, entry_rejected=False))
            else:
                # Even a prepare+abort between observer samples is ownership;
                # it must never be reclassified as a clean refusal.
                assert "tactic prepare" not in block, "unobserved tactical ownership"
                results.append(dict(map=name, case=case, entry_rejected=True, ordinary_drop_after_rejection=any(r["p"][2] < origin[2] - 8 for r in rows if r["t"] <= 0.5)))
        elif case in ("0", "8", "10", "12", "13"):
            setup = re.search(r"TACFIX route_setup mode\s+(\d+) node '([^']+)' velocity '([^']+)'", block)
            if case == "8" and setup:
                assert setup[1] == "2" and math.dist(list(map(float, setup[3].split())), (0, 0, 0)) > 1, "routed fixture did not exercise incoming momentum"
                if name == "dm4":
                    assert list(map(float, setup[2].split()))[2] < origin[2] - 120, "routed fixture did not preserve a pit-floor node"
            events = re.findall(r"ARGEVT \S+ tactic ([^\r\n]+)", block)
            assert events[:5] == ["prepare", "opening", "covered", "reappear", "returnshot"], f"{name}: incomplete manoeuvre: {events}"
            opening = next((r for prev, r in zip(rows, rows[1:]) if fired(prev, r)), None)
            assert opening, f"{name}: no actual opening rocket"
            hidden = next((r for r in rows if r["hidden"] and r["t"] >= opening["t"]), None)
            assert hidden, f"{name}: no full-body concealment after opening shot"
            returned = next((r for r in rows if r["t"] > hidden["t"] and not r["hidden"]), None)
            assert returned, f"{name}: never reappeared"
            a = math.atan2(origin[1] - enemy[1], origin[0] - enemy[0])
            b = math.atan2(returned["p"][1] - enemy[1], returned["p"][0] - enemy[0])
            angle = abs((math.degrees(b-a)+180)%360-180)
            assert angle >= 30, f"{name}: first reappearance changed angle only {angle:.1f} degrees"
            shots = [(prev, r) for prev, r in zip(rows, rows[1:]) if r["t"] >= returned["t"] and fired(prev, r)]
            shot = shots[0][1] if shots else None
            assert shot, f"{name}: no actual return rocket"
            next_shot = shots[1][1]["t"] if len(shots) > 1 else math.inf
            damage = next((r for r in rows if shot["t"] <= r["t"] <= shot["t"] + 0.6 and r["t"] < next_shot and r["hp"] < shots[0][0]["hp"]), None)
            assert all(r["bot_hp"] == 100 for r in rows if shot["t"] <= r["t"] <= shot["t"] + 0.4), f"{name}: return shot caused self damage"
            assert rows[-1]["t"] >= shot["t"] + 0.5, "missing post-return observation"
            assert all(abs(r["p"][2] - origin[2]) < 8 and r["bot_hp"] > 0 for r in rows if r["t"] <= shot["t"] + 0.5), f"{name}: left walking surface"
            results.append(dict(map=name, case=case, concealed_at=hidden["t"], return_at=returned["t"], first_angle=round(angle, 1), return_damage=bool(damage)))
            if case == "10":
                assert "TACFIX ammo_added" in block, "missing ammo pickup"
        else:
            assert "tactic returnshot" not in block, f"{name}: claimed success in interrupted encounter"
            if case in ("3", "9"):
                assert "tactic prepare" not in block, f"{name}: began offensive move at low health"
            else:
                assert "TACFIX target_moved" in block and "tactic abort" in block, f"{name}: missing interruption/abort"
                if case == "4":
                    assert "tactic abort survival" in block
                if case == "5":
                    assert "tactic abort weapon" in block
                if case == "7":
                    assert "tactic abort crossfire" in block
                if case == "2":
                    # Moving a hidden target must not update remembered coords.
                    memories = re.findall(r"^TACFIX sample [^\r\n]* memory '([^']+)'", block.split("TACFIX target_moved", 1)[1], re.M)
                    assert memories and all(math.dist(list(map(float, p.split())), enemy) < 1 for p in memories[:3]), f"{name}: tracked a hidden departure"
                if case == "11":
                    assert "tactic abort sight" in block
            results.append(dict(map=name, case=case, interrupted=True))
        cadence = re.search(r"TACFIX end frames\s+(\d+) seconds\s+([\d.]+)", block)
        if cadence:
            frames, seconds = int(cadence[1]), float(cadence[2])
            assert frames > 0 and seconds > 0, "invalid fixture cadence"
            results[-1].update(frames=frames, seconds=seconds, fps=round(frames / seconds, 1))
    assert results, "no fixture results"
    return results

def require_sequence(results, expected):
    actual = [int(r["case"]) for r in results]
    assert actual == expected, f"case sequence mismatch: expected {expected}, got {actual} (missing, duplicate or out-of-order trial)"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("log", type=Path)
    ap.add_argument("--suite", action="store_true", help="require three stationary plus all seven interruption/motion trials")
    ap.add_argument("--review-suite", action="store_true", help="also require routed, lightning, ammo, exit sight-loss and shop lifecycle cases")
    ap.add_argument("--slow-suite", action="store_true", help="require slow stationary/motion/routed cases and one refused overlapping trial")
    ap.add_argument("--hz", type=float, help="require measured fixture cadence within ten percent of this rate")
    args = ap.parse_args()
    results = check(args.log.read_text(errors="replace"))
    if args.suite or args.review_suite or args.slow_suite:
        expected = [0, 0, 0, 6, 8, 9, 12] if args.slow_suite else [0, 0, 0, *range(1, 13 if args.review_suite else 8)]
        if args.slow_suite:
            assert sorted(int(r["case"]) for r in results) == expected, "incomplete acceptance suite"
        else:
            require_sequence(results, expected)
        # Preserve ordinary skill-1 aim error: a useful shot need not hit
        # every trial, but this suite must demonstrate repeatable damage.
        assert sum(r.get("return_damage", False) for r in results if r["case"] == "0") >= 2, "fewer than two damaging return shots"
        if args.review_suite or args.slow_suite:
            assert "TACFIX shopchecks 1" in args.log.read_text(errors="replace"), "shop lifecycle checks failed"
        if args.slow_suite:
            assert all(9 <= r.get("fps", 0) <= 11 for r in results), "fixture did not run at the requested 10 Hz cadence"
            assert "TACFIX busy" in args.log.read_text(errors="replace"), "overlapping fixture was not refused"
            assert "TACFIX route_setup" in args.log.read_text(errors="replace"), "missing moving routed regression setup"
    if args.hz is not None:
        assert math.isfinite(args.hz) and args.hz > 0, "invalid requested cadence"
        assert all(0.9 * args.hz <= r.get("fps", 0) <= 1.1 * args.hz for r in results), "measured fixture cadence differs from requested rate"
    print(json.dumps(results, indent=2))
