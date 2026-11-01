"""Exercise production target decisions with private, quarantined inputs."""

from run_behaviour_equivalence import lab_executable, lab_cli
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import run_behaviour_equivalence as native
from run_map_intelligence import ROOT, Lab, digest, write

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
    assert not re.search(r'\bfoe\s*\.', code), 'target utility reads live opponent fields'
    assert not re.search(r'\b(random|traceline|makevectors)\s*\(', code), 'utility changes observation inputs'
    return dict(opponent_fields_private=True, utility_deterministic=True)


def stage(root, output, source=None):
    shutil.copytree(source or root / 'src', output / 'src')
    (output / 'lq1').mkdir(); (output / 'runs').mkdir()
    src = output / 'src'
    production = (src / 'argus.qc').read_text()
    candidate = 'Argus_TargetValue =' in production
    if candidate: audit_target_value(production)
    fixture = (root / 'tools/fixtures/target_attention.qc').read_text()
    if candidate: fixture = '#define ATTENTION_CANDIDATE\n' + fixture
    (src / 'target_attention_fixture.qc').write_text(fixture)
    path = src / 'progs.src'; text = path.read_text()
    assert text.count('\nworld.qc\n') == 1
    path.write_text(text.replace('\nworld.qc\n', '\ntarget_attention_fixture.qc\nworld.qc\n'))
    path = src / 'world.qc'; text = path.read_text()
    assert text.count('Argus_FrameAll ();') == 1
    path.write_text(text.replace('Argus_FrameAll ();',
        'TargetAttentionFixture ();\n    if (!at_done) Argus_FrameAll ();'))
    path = src / 'defs.qc'; text = path.read_text()
    pattern = r'float\s*\(\)\s*random\s*=\s*#7\s*;'
    assert len(re.findall(pattern, text)) == 1
    path.write_text(re.sub(pattern, 'float at_rngcalls;\nfloat() random =\n{\n'
        '    at_rngcalls = at_rngcalls + 1;\n    return 0.5;\n};', text))
    return candidate


def inspect_fixture(text, map_name, ticrate, legacy=False):
    assert not any(s in text for s in ('Host_Error', 'Program error', 'runaway loop error', 'ATFIX refused'))
    assert re.findall(r'^ARGUS init on (\S+)$', text, re.M) == [map_name]
    assert text.count('BHVRPL begin target_attention') == 1
    starts = re.findall(r'^ATFIX begin dt_ms\s+([\d.]+)$', text, re.M)
    assert len(starts) == 1
    ms = float(starts[0]); assert (90 <= ms <= 110) if ticrate == .1 else (10 <= ms <= 30)
    checks = re.findall(r'^ATFIX check (\w+)\s+([01])$', text, re.M)
    assert tuple(label for label, _ in checks) == LABELS
    ends = re.findall(r'^ATFIX end checks\s+(\d+) failures\s+(\d+)$', text, re.M)
    failures = [label for label, ok in checks if ok == '0']
    assert ends == [(str(len(LABELS)), str(len(failures)))]
    assert set(failures) == (LEGACY_FAILURES if legacy else set()), failures
    return dict(checks=checks, failures=failures, frame_ms=ms, legacy=legacy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--maps', default='dm6,lqdm2')
    parser.add_argument('--ticrate', type=float, choices=(.0139, .1), default=.0139)
    parser.add_argument('--port', type=int, default=26003)
    parser.add_argument('--legacy-control', action='store_true')
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9_]+', args.prefix)
    maps = args.maps.split(','); assert maps and len(set(maps)) == len(maps)
    assert set(maps) <= {'dm3', 'dm6', 'lqdm2', 'e1m1', 'e1m7'} and 1024 <= args.port <= 65535
    output = args.output.resolve(); assert not output.exists()
    assert output.is_relative_to((ROOT / 'backups').resolve())
    candidate = stage(ROOT, output, args.source)
    assert candidate != args.legacy_control, 'declare the legacy source explicitly'
    game = 'attentioncheck_' + args.prefix; folder = ROOT / 'engine' / game
    assert not folder.exists(); folder.mkdir()
    for name in ('progs', 'maps', 'sound', 'gfx'):
        original = ROOT / 'engine/argus' / name
        if original.exists(): shutil.copytree(original, folder / name)
    shutil.copy2(ROOT / 'game/argus/autoexec.cfg', folder / 'autoexec.cfg')
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
            assert compiled['ok'], compiled
            shutil.copy2(output / 'lq1/progs.dat', folder / 'progs.dat')
            for map_name in maps:
                name = args.prefix + '_' + map_name
                result = lab_cli(executable, 'match', map_name, '10', name, '--skill', '2', '--port', str(args.port), cwd=ROOT, environment=dict(os.environ, ARGUS_ROOT=str(ROOT), **env), timeout=40)
                (output / (map_name + '.stderr')).write_text(result.stderr)
                assert result.returncode == 0, result.stderr
                raw = output / 'runs' / (name + '.log')
                # Keep even a failing oracle result before judging it.
                row = dict(map=map_name, source_sha256=digest(output / 'src/argus.qc'),
                    fixture_sha256=digest(output / 'src/target_attention_fixture.qc'),
                    binary_sha256=digest(folder / 'progs.dat'), raw_sha256=digest(raw),
                    raw=str(raw.relative_to(ROOT)))
                write(output / (map_name + '.identity.json'), row)
                row.update(inspect_fixture(raw.read_text(errors='replace'), map_name,
                                           args.ticrate, args.legacy_control))
                rows.append(row); write(output / 'receipt.json', rows)
                print(json.dumps(row), flush=True)
        finally:
            native.finish_lab(lab)


if __name__ == '__main__':
    main()
