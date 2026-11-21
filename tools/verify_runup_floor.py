"""Check the production jump run-up floor guard at dm4 node 111."""
import argparse
from pathlib import Path
import re
import shutil
import sys

from argus_fixture_harness import frame_ms, new_output, private_game, read_tape, run_match, stage_fixture
from argus_source import source_identity
from argus_validation import require
from argus_lab_client import Lab, finish_lab, lab_executable
from run_map_intelligence import ROOT, digest, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--source", type=Path, default=ROOT / "src")
    parser.add_argument("--port", type=int, default=26227)
    parser.add_argument("--expect-control", action="store_true",
                        help="require the old guard to accept both run-up drops")
    args = parser.parse_args()
    require(re.fullmatch(r"[a-z0-9_]{1,48}", args.prefix), "invalid fixture prefix")
    require(1024 <= args.port <= 65535, "invalid fixture port")
    require(not any(p.exists() for p in (ROOT / "qconsole.log", ROOT / "engine/qconsole.log")),
            "harvest human logs first")
    require(not list((ROOT / "engine/argus").glob("*.dem")), "harvest human demos first")
    executable = lab_executable()
    out = new_output(args.output, root=ROOT, create=False)
    fixture = ROOT / "tools/fixtures/runup_floor.qc"
    src = stage_fixture(ROOT, out, args.source, fixtures={fixture.name: fixture.read_text(encoding="utf-8")},
                        frame_wrap="Argus_FrameAll ();\n    RunupFloorFixture ();")
    program = out / "lq1/progs.dat"
    with private_game(ROOT, args.prefix, "runupcheck", autoexec="sv_protocol 15\nmax_edicts 600\n") as game:
        env = {"ARGUS_SRC": str(src), "ARGUS_RUNS": str(out / "runs"), "ARGUS_GAME": game.name,
               "ARGUS_PROGS": str(program), "ARGUS_TICRATE": ".0139", "ARGUS_PYTHON": sys.executable}
        with (out / "lab.stderr").open("w", encoding="utf-8") as stderr:
            lab = Lab(stderr, environment=env, exe=executable, timeout=40)
            try:
                lab.call("see", what="project")
                result = lab.call("compile_qc", install=False)
                write(out / "compile.json", result)
                require(result["ok"] and not result["installed_to"], result)
                shutil.copyfile(program, game / "progs.dat")
                run_match(lab, "dm4", 10, args.prefix, port=args.port, environment=env,
                          timeout=30, stderr_path=out / "record.stderr")
            finally:
                finish_lab(lab, active=False)
    raw, text = read_tape(out, args.prefix, "dm4")
    require(text.count("BHVRPL begin runup_floor") == 1, "missing fixture quarantine")
    require(text.count("RFCHECK end") == 1, "missing fixture termination")
    observed = re.findall(r"^RFCHECK (\w+) ([01])$", text, re.M)
    drop = "0" if args.expect_control else "1"
    expected = [("backstep", drop), ("lineup", drop), ("charge", "0"),
                ("other_move", "0"), ("in_air", "0"), ("level_floor", "0")]
    receipt = dict(build=result["build"], frame_ms=frame_ms(text, "RFCHECK", .0139),
                   observed=observed, expected=expected, control=args.expect_control,
                   source_sha256=source_identity(src), program_sha256=digest(program),
                   raw_sha256=digest(raw), raw=raw.relative_to(ROOT).as_posix())
    write(out / "receipt.json", receipt)
    print(receipt)
    require(observed == expected, "run-up floor guard returned unexpected verdicts")


if __name__ == "__main__":
    main()
