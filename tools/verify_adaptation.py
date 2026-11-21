"""Repeat the combat, hearing and portal witnesses on stock dm2 and dm6."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

from argus_fixture_harness import new_output, private_game, read_tape, run_match, stage_fixture, write_text
from argus_source import source_identity
from argus_validation import require
from argus_lab_client import ROOT, Lab, finish_lab, lab_executable

COMMON = {'real_pickup_is_audible', 'pickup_has_no_weapon_class',
          'one_shell_sounds_like_single_shotgun', 'one_nail_sounds_like_single_nailgun',
          'near_fresh_shot_can_round_corner', 'old_shot_does_not_draw_corner_detour',
          'loaded_nailgun_fires_below_splash_band', 'splash_crossing_cancels_outgoing_nail_chain',
          'loaded_switches_follow_repeated_splash_crossings', 'nail_depletion_selects_a_firing_shotgun',
          'grenade_launcher_fires_when_rockets_are_unavailable', 'expired_beam_releases_to_loaded_rockets',
          'water_entry_cancels_lightning_and_fires_safe_fallback', 'receding_target_lead',
          'closing_target_lead', 'crossing_target_lead', 'extreme_speed_retains_legacy_lead'}
REQUIRED = {
    'dm2': COMMON | {'keeps_pickup_commitment', 'expired_pickup_cools_and_replans',
                     'unseen_opponent_leaves_pickup_ranking_alone', 'denial_uses_last_sighting',
                     'denial_can_use_fresh_gunfire', 'denial_expires_stale_evidence'},
    'dm6': COMMON | {'two_live_portals_and_graph_search', 'both_warps_leave_active_search_unchanged',
                     'both_portals_learned_when_idle', 'warp_waits_for_audible_playback',
                     'warp_exit_is_a_neutral_audible_cue', 'warp_respects_recent_shot_priority'},
}


def stage(root, output, source=None):
    names = ('adaptation_audio.qc', 'adaptation_pickups.qc')
    fixtures = {name: (root / 'tools/fixtures' / name).read_text(encoding='utf-8') for name in names}
    return stage_fixture(root, output, source, fixtures=fixtures,
                         frame_wrap='AfFixture ();\n    AdaptationPickupFixture ();\n    Argus_FrameAll ();')


def inspect_fixture(raw, map_name, build):
    require(raw.splitlines().count('BHVRPL begin adaptation') == 1, 'missing or duplicate fixture marker')
    require([line for line in raw.splitlines() if line.startswith('ARGUS build ')] ==
            ['ARGUS build ' + build], 'mismatched fixture build')
    rows = re.findall(r'^AUDIOFIX (\w+) ([01])$', raw, re.M)
    checks = dict(rows)
    require(len(checks) == len(rows) and REQUIRED[map_name] <= checks.keys(), 'missing or duplicate checks')
    require(all(value == '1' for value in checks.values()), checks)
    return checks


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--lab', type=Path)
    parser.add_argument('--port', type=int, default=26007)
    args = parser.parse_args()
    executable = lab_executable(args.lab)
    output = new_output(args.output, root=ROOT, create=False)
    src = stage(ROOT, output)
    with private_game(ROOT, args.prefix, 'adaptcheck') as game:
        binary = output / 'lq1/progs.dat'
        env = dict(ARGUS_SRC=str(src), ARGUS_PROGS=str(binary), ARGUS_GAME=game.name,
                   ARGUS_RUNS=str(output / 'runs'), ARGUS_PYTHON=sys.executable)
        results = {}
        with (output / 'lab.stderr').open('w', encoding='utf-8') as err:
            lab = Lab(err, env, exe=executable, timeout=35)
            try:
                lab.call('see', what='project')
                compiled = lab.call('compile_qc', install=False)
                write_text(output / 'compile.json', json.dumps(compiled, indent=2))
                require(compiled['ok'] and not compiled['installed_to'], compiled)
                shutil.copy2(binary, game / 'progs.dat')
                control = args.prefix + '_ordinary'
                run_match(lab, 'dm6', 10, control, port=args.port, timeout=25,
                          environment=env, stderr_path=output / 'ordinary.stderr')
                _, normal = read_tape(output, control, 'dm6')
                require('BHVRPL begin adaptation' not in normal, 'ordinary arm ran the fixture')

                cfg = game / 'autoexec.cfg'
                write_text(cfg, cfg.read_text(encoding='utf-8') + '\nscratch2 2517\n')
                for map_name in REQUIRED:
                    name = f'{args.prefix}_{map_name}'
                    run_match(lab, map_name, 10, name, port=args.port, timeout=25,
                              environment=env, stderr_path=output / f'{map_name}.stderr')
                    tape, raw = read_tape(output, name, map_name)
                    results[map_name] = dict(checks=inspect_fixture(raw, map_name, compiled['build']),
                                             tape_sha256=digest(tape))
                comparison = lab.call('compare_runs', log_a=control, log_b=args.prefix + '_dm6', map='dm6')
                write_text(output / 'comparison.json', json.dumps(comparison, indent=2))
                require('CONTROLLED FIXTURE' in comparison['gate_card'], comparison)
                require(not comparison.get('gates'), 'fixture received gameplay gate results')
            finally:
                finish_lab(lab)
        receipt = dict(maps=results, source_sha256=source_identity(src), binary_sha256=digest(binary))
        write_text(output / 'receipt.json', json.dumps(receipt, indent=2))
        print(json.dumps({name: len(result['checks']) for name, result in results.items()}))


if __name__ == '__main__':
    main()
