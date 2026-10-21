"""Assert real-engine outcomes from the opt-in TACFIX observer."""
import argparse
import json
import math
import re
from pathlib import Path

SAMPLE = re.compile(r"TACFIX sample\s+([\d.]+) pos '([^']+)' hidden\s+(\d+) rockets\s+([\d.-]+) targethp\s+([\d.-]+) hp\s+([\d.-]+)")

def check(text):
    assert "Host_Error" not in text and "runaway loop error" not in text, "engine error in fixture tape"
    results = []
    for block in text.split("TACFIX begin ")[1:]:
        name, _, case = block.splitlines()[0].split()
        rows = [dict(t=float(m[1]), p=list(map(float, m[2].split())), hidden=int(m[3]), rockets=float(m[4]), hp=float(m[5]), bot_hp=float(m[6])) for m in SAMPLE.finditer(block)]
        assert rows and "TACFIX end" in block, "incomplete fixture"
        origin, enemy = ((465, -279, -104), (337, -247, -296)) if name == "dm4" else ((2209, -279, 24), (2433, -183, 24))
        if case == "6":
            # A moving approach may safely abort; it must stay on this floor
            # while the tactic owns steering, including its opening brake.
            active = [r for r, line in zip(rows, SAMPLE.finditer(block)) if " state 0 " not in block[line.end():].splitlines()[0]]
            assert "tactic prepare" in block and active
            assert all(abs(r["p"][2] - origin[2]) < 8 and r["bot_hp"] > 0 for r in active)
            assert "tactic returnshot" in block or "tactic abort" in block
            results.append(dict(map=name, case=case, moving_entry_safe=True))
        elif case == "0":
            events = re.findall(r"ARGEVT \S+ tactic ([^\r\n]+)", block)
            assert events[:5] == ["prepare", "opening", "covered", "reappear", "returnshot"], f"{name}: incomplete manoeuvre: {events}"
            opening = next((r for prev, r in zip(rows, rows[1:]) if r["rockets"] < prev["rockets"]), None)
            assert opening, f"{name}: no actual opening rocket"
            hidden = next((r for r in rows if r["hidden"] and r["t"] >= opening["t"]), None)
            assert hidden, f"{name}: no full-body concealment after opening shot"
            returned = next((r for r in rows if r["t"] > hidden["t"] and not r["hidden"]), None)
            assert returned, f"{name}: never reappeared"
            a = math.atan2(origin[1] - enemy[1], origin[0] - enemy[0])
            b = math.atan2(returned["p"][1] - enemy[1], returned["p"][0] - enemy[0])
            angle = abs((math.degrees(b-a)+180)%360-180)
            assert angle >= 30, f"{name}: first reappearance changed angle only {angle:.1f} degrees"
            damage = next((r for r in rows if returned["t"] < r["t"] < returned["t"] + 1.5 and r["rockets"] < returned["rockets"] and r["hp"] < returned["hp"]), None)
            shot = next((r for prev, r in zip(rows, rows[1:]) if r["t"] > returned["t"] and r["rockets"] < prev["rockets"]), None)
            assert shot, f"{name}: no actual return rocket"
            assert all(r["bot_hp"] == 100 for r in rows if shot["t"] <= r["t"] <= shot["t"] + 0.4), f"{name}: return shot caused self damage"
            assert all(abs(r["p"][2] - origin[2]) < 8 and r["bot_hp"] > 0 for r in rows if r["t"] <= returned["t"]), f"{name}: left walking surface"
            results.append(dict(map=name, case=case, concealed_at=hidden["t"], return_at=returned["t"], first_angle=round(angle, 1), return_damage=bool(damage)))
        else:
            assert "tactic returnshot" not in block, f"{name}: claimed success in interrupted encounter"
            if case == "3":
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
                    memories = re.findall(r"memory '([^']+)'", block.split("TACFIX target_moved", 1)[1])
                    assert memories and all(math.dist(list(map(float, p.split())), enemy) < 1 for p in memories[:3]), f"{name}: tracked a hidden departure"
            results.append(dict(map=name, case=case, interrupted=True))
    assert results, "no fixture results"
    return results

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("log", type=Path)
    ap.add_argument("--suite", action="store_true", help="require three stationary plus all seven interruption/motion trials")
    args = ap.parse_args()
    results = check(args.log.read_text(errors="replace"))
    if args.suite:
        assert sorted(r["case"] for r in results) == ["0", "0", "0", "1", "2", "3", "4", "5", "6", "7"], "incomplete acceptance suite"
        # Preserve ordinary skill-1 aim error: a useful shot need not hit
        # every trial, but this suite must demonstrate repeatable damage.
        assert sum(r.get("return_damage", False) for r in results) >= 2, "fewer than two damaging return shots"
    print(json.dumps(results, indent=2))
