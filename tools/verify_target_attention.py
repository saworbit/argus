"""Exercise production target decisions with private, quarantined inputs."""

from argus_validation import require
from argus_source import source_identity
from argus_fixture_harness import (new_output, stage_fixture, private_game,
    read_tape, check_tape, frame_ms as measured_frame_ms, run_match)

from run_behaviour_equivalence import lab_executable
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

import run_behaviour_equivalence as native
from run_map_intelligence import ROOT, Lab, digest, write

def source_receipt(src):
    """Identity of every QuakeC input in the staged fixture source."""
    return dict(source_sha256=source_identity(src))


LABELS = ('geometry', 'minor_difference_keeps_focus', 'answers_visible_attacker',
    'switch_reaction_delayed', 'goal_retained', 'secondary_is_not_primary', 'avoids_invulnerable_fixation',
    'retreat_intent_retained', 'commitment_held', 'scan_clock_held', 'warmup_keeps_policy', 'tactic_keeps_owner',
    'hidden_attacker_not_seen', 'hidden_changes_preserve_rng',
    'hidden_current_uses_cached_cues', 'ring_still_requires_sight',
    'old_aggression_expires', 'ally_damage_not_hostile', 'world_self_not_hostile',
    'removed_attacker_forgotten', 'respawn_clears_attention')
LEGACY_FAILURES = {'answers_visible_attacker', 'switch_reaction_delayed', 'avoids_invulnerable_fixation'}


def audit_target_value(source):
    from check_perception_fixture import function
    code = function(source, 'Argus_TargetValue')
    require((not re.search(r'\bfoe\s*\.', code)), 'target utility reads live opponent fields')
    require((not re.search(r'\b(random|traceline|makevectors)\s*\(', code)), 'utility changes observation inputs')
    return dict(opponent_fields_private=True, utility_deterministic=True)


def stage(root, output, source=None):
    base = Path(source or root / 'src')
    production = (base / 'argus.qc').read_text(encoding='utf-8')
    candidate = 'Argus_TargetValue =' in production
    if candidate: audit_target_value(production)
    fixture = (root / 'tools/fixtures/target_attention.qc').read_text(encoding='utf-8')
    if candidate: fixture = '#define ATTENTION_CANDIDATE\n' + fixture
    def fixed_rng(text):
        pattern = r'float\s*\(\)\s*random\s*=\s*#7\s*;'
        require(len(re.findall(pattern, text)) == 1, 'expected one random builtin')
        return re.sub(pattern, 'float at_rngcalls;\nfloat() random =\n{\n'
            '    at_rngcalls = at_rngcalls + 1;\n    return 0.5;\n};', text)
    stage_fixture(root, output, source, fixtures={'target_attention_fixture.qc': fixture},
                  frame_wrap='TargetAttentionFixture ();\n    if (!at_done) Argus_FrameAll ();',
                  edits={'defs.qc': fixed_rng})
    return candidate


def inspect_fixture(text, map_name, ticrate, legacy=False):
    check_tape(text, map_name)
    require('ATFIX refused' not in text, 'attention fixture refused')
    require((text.count('BHVRPL begin target_attention') == 1))
    ms = measured_frame_ms(text, 'ATFIX', ticrate)
    checks = re.findall(r'^ATFIX check (\w+)\s+([01])$', text, re.M)
    require((tuple(label for label, _ in checks) == LABELS))
    ends = re.findall(r'^ATFIX end checks\s+(\d+) failures\s+(\d+)$', text, re.M)
    failures = [label for label, ok in checks if ok == '0']
    require((ends == [(str(len(LABELS)), str(len(failures)))]))
    require((set(failures) == (LEGACY_FAILURES if legacy else set())), failures)
    return dict(checks=checks, failures=failures, frame_ms=ms, legacy=legacy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--maps', default='dm6,lqdm2')
    parser.add_argument('--ticrate', type=float, choices=(.0139, .1), default=.0139)
    parser.add_argument('--port', type=int, default=26006)
    parser.add_argument('--legacy-control', action='store_true')
    args = parser.parse_args()
    require((re.fullmatch(r'[a-z0-9_]{1,48}', args.prefix)))
    maps = args.maps.split(','); require((maps and len(set(maps)) == len(maps)))
    require((set(maps) <= {'dm3', 'dm6', 'lqdm2', 'e1m1', 'e1m7'} and 1024 <= args.port <= 65535))
    output = new_output(args.output, root=ROOT, create=False)
    candidate = stage(ROOT, output, args.source)
    require((candidate != args.legacy_control), 'declare the legacy source explicitly')
    with private_game(ROOT, args.prefix, 'attentioncheck') as folder:
        game = folder.name
        executable = lab_executable()
        env = dict(ARGUS_SRC=str(output / 'src'), ARGUS_PROGS=str(output / 'lq1/progs.dat'),
            ARGUS_RUNS=str(output / 'runs'), ARGUS_GAME=game, ARGUS_PYTHON=sys.executable,
            ARGUS_TICRATE=str(args.ticrate))
        rows = []
        with (output / 'lab.stderr').open('w') as err:
            lab = Lab(err, env, exe=executable, timeout=900)
            try:
                lab.call('see', what='project')
                compiled = lab.call('compile_qc', install=False); write(output / 'compile.json', compiled)
                require((compiled['ok']), compiled)
                shutil.copy2(output / 'lq1/progs.dat', folder / 'progs.dat')
                for map_name in maps:
                    name = args.prefix + '_' + map_name
                    result = run_match(lab, map_name, 10, name, port=args.port, timeout=40, environment=env, stderr_path=output / (map_name + '.stderr'))
                    raw, text = read_tape(output, name, map_name)
                    # Keep even a failing oracle result before judging it.
                    row = dict(map=map_name, **source_receipt(output / 'src'),
                        fixture_sha256=digest(output / 'src/target_attention_fixture.qc'),
                        binary_sha256=digest(folder / 'progs.dat'), raw_sha256=digest(raw),
                        raw=str(raw.relative_to(ROOT)))
                    write(output / (map_name + '.identity.json'), row)
                    row.update(inspect_fixture(text, map_name,
                                               args.ticrate, args.legacy_control))
                    rows.append(row); write(output / 'receipt.json', rows)
                    print(json.dumps(row), flush=True)
            finally:
                native.finish_lab(lab)


if __name__ == '__main__':
    main()
