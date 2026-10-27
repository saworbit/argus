"""Repeat focused muzzle, actual combat-trigger or health checks in a private lab.

Examples:
  python tools/verify_private_fixtures.py muzzle --output backups/muzzle-new --prefix muzzle_new
  python tools/verify_private_fixtures.py health --output backups/health-new --prefix health_new
  python tools/verify_private_fixtures.py combat --output backups/combat-new --prefix combat_new

Uses the matching source-built native lab, install=false and private assets.
No historical snapshots, cohorts or deployment. Health checks do not resolve
the outstanding dm4 gameplay warning in #583.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from check_health_fixture import audit as audit_health, check as check_health
from check_muzzle_fixture import audit as audit_muzzle, check as check_muzzle
from check_muzzle_combat import check as check_combat
from check_perception_fixture import check as check_perception
from run_behaviour_equivalence import EXE, Lab, ROOT
from run_health_fixture import prepare as prepare_health, audit_private
from verify_plan_progress import copy_assets, save, sha


def tree_identity(folder):
    files = {p.relative_to(folder).as_posix(): sha(p)
             for p in sorted(folder.rglob('*')) if p.is_file()}
    return dict(files=files, sha256=hashlib.sha256(
        json.dumps(files, sort_keys=True).encode()).hexdigest())


def identities(paths):
    return {str(p): sha(p) if p.is_file() else None for p in paths}


def preflight(root, output, prefix):
    output = output.resolve()
    if not output.is_relative_to((root/'backups').resolve()) or output.exists():
        raise ValueError('output must be a new directory beneath backups/')
    if not re.fullmatch(r'[a-z0-9_]{1,48}', prefix):
        raise ValueError('prefix must contain 1..48 lowercase letters, digits or underscores')
    if not (root/'src/progs.src').is_file() or not EXE.is_file():
        raise ValueError('current sources and a source-built native lab are required')
    return output


def stage_muzzle(root, folder, variant):
    shutil.copytree(root/'src', folder/'src')
    (folder/'lq1').mkdir()
    src = folder/'src'
    if variant == 'production':
        return
    path = src/'argus.qc'
    source = path.read_text()
    replacements = {
        'legacy': ('if (!self.ar_tactic && self.weapon != IT_ROCKET_LAUNCHER)', 'if (!self.ar_tactic)'),
        'uncapped': ('if (targetdist < reach) reach = targetdist;', 'reach = 240;'),
    }
    if variant in replacements:
        old, new = replacements[variant]
        if source.count(old) != 1:
            raise ValueError('muzzle control anchor changed: '+variant)
        source = source.replace(old, new)
    path.write_text(source, encoding='utf-8')
    shutil.copy2(root/'tools/fixtures/muzzle_clearance.qc', src/'muzzle_clearance.qc')
    path = src/'progs.src'
    source = path.read_text()
    if source.count('\nworld.qc\n') != 1:
        raise ValueError('world compilation anchor changed')
    path.write_text(source.replace('\nworld.qc\n', '\nmuzzle_clearance.qc\nworld.qc\n'))
    path = src/'world.qc'
    source = path.read_text()
    if source.count('Argus_CountSlots ();') != 1 or source.count('Argus_FrameAll ();') != 1:
        raise ValueError('world fixture anchors changed')
    source = source.replace('Argus_CountSlots ();',
        'Argus_CountSlots ();\n    dprint ("BHVRPL begin muzzle_fixture\\n");')
    path.write_text(source.replace('Argus_FrameAll ();',
        'if (time > 1) MuzzleFixture ();\n    Argus_FrameAll ();'))
    for original in (root/'src').rglob('*'):
        if original.is_file() and original.name not in {'argus.qc', 'world.qc', 'progs.src'}:
            if original.read_bytes() != (src/original.relative_to(root/'src')).read_bytes():
                raise ValueError('unexpected private source change: '+str(original))


def stage_combat(root, folder, variant):
    stage_muzzle(root, folder, 'production')
    src=folder/'src';path=src/'argus.qc';source=path.read_text()
    if variant=='legacy':
        old='if (!self.ar_tactic && self.weapon != IT_ROCKET_LAUNCHER)'
        assert source.count(old)==1
        source=source.replace(old,'if (!self.ar_tactic)')
    anchor='        if (!Argus_MuzzleClear (aimpt))'
    assert source.count(anchor)==1
    source=source.replace(anchor,'        if (self == mc_actor) { mc_gates = mc_gates + 1; mc_motor = self.ar_moveyaw; }\n'+anchor)
    path.write_text('entity mc_actor; float mc_gates, mc_motor;\n'+source)
    shutil.copy2(root/'tools/fixtures/muzzle_combat.qc',src/'muzzle_combat.qc')
    path=src/'progs.src';source=path.read_text()
    assert source.count('\nworld.qc\n')==1
    path.write_text(source.replace('\nworld.qc\n','\nmuzzle_combat.qc\nworld.qc\n'))
    path=src/'world.qc';source=path.read_text()
    assert source.count('Argus_FrameAll ();')==source.count('Argus_CountSlots ();')==1
    source=source.replace('Argus_CountSlots ();','Argus_CountSlots ();\n    dprint ("BHVRPL begin muzzle_combat\\n");')
    path.write_text(source.replace('Argus_FrameAll ();','if (time > 1) MuzzleCombatFixture ();\n    Argus_FrameAll ();'))


def native_config(lab_factory, output):
    with (output/'config.stderr').open('w') as err:
        lab = lab_factory(err, {'TOKIO_WORKER_THREADS': '2'})
        try:
            project = lab.call('see', what='project')
            if not project.get('lab_identity', {}).get('authoritative'):
                raise ValueError('matching source-built native lab required')
            config = lab.call('config_check')
            if not config['complete']:
                raise ValueError('native lab configuration is incomplete')
            if lab.call('match_status').get('running'):
                raise ValueError('stop the existing lab match first')
            save(output/'native-config.json', config)
            return {r['key']: r['value'] for r in config['entries']}
        finally:
            lab.close()


def private_assets(base, game, output):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', game):
        raise ValueError('ARGUS_GAME must be a game directory name')
    if not (base/'id1').is_dir() or not any((base/'id1').glob('pak*.pak')):
        raise ValueError('configured id1 PAK assets are missing')
    copy_assets(base/'id1', output/'base/id1')
    private_game = output/'base'/game
    private_game.mkdir()
    for name in ('maps', 'progs', 'gfx', 'sound'):
        if (base/game/name).is_dir():
            copy_assets(base/game/name, private_game/name)
    for pak in (base/game).glob('*.pak'):
        if pak.is_symlink():
            raise ValueError('symlinked game PAK refused')
        shutil.copy2(pak, private_game/pak.name)
    return private_game


def health_trial(lab, stem, map_name, env, client_run):
    """Run one declared ring-0 trial; always stop the owned native engine."""
    try:
        lab.call('match_start', map=map_name, duration_sec=20, skill=1,
                 run_name=stem, dedicated_slots=8)
        deadline = time.monotonic()+8
        while True:
            status = lab.call('match_status')
            if 'ARGLOG ' in json.dumps(status):
                break
            if not status.get('running') or time.monotonic() >= deadline:
                raise RuntimeError('private engine did not become healthy')
            time.sleep(.05)
        lab.call('match_command', command='sys_ticrate 0.0139; developer 1; scratch1 593; scratch2 0; scratch3 1; scratch4 594')
        result = client_run([str(EXE), 'client', 'impulse', '219', '0.6'], cwd=ROOT,
            env=dict(os.environ, **env), capture_output=True, text=True,
            encoding='utf-8', timeout=20)
        if result.returncode:
            raise RuntimeError('fixture client failed: '+result.stderr)
    finally:
        lab.call('match_stop')


def run(fixture, output, prefix, *, root=ROOT, lab_factory=Lab, client_run=subprocess.run):
    if fixture not in {'muzzle', 'health', 'combat'}:
        raise ValueError('unknown fixture')
    output = preflight(root, output, prefix)
    # Exclusive creation also refuses a racing invocation or a reused output.
    output.mkdir(parents=True, exist_ok=False)
    source_before = tree_identity(root/'src')
    protected = [root/'game/argus/progs.dat', root/'engine/argus/progs.dat',
                 root/'lq1/progs.dat', EXE]
    before = identities(protected)
    save(output/'before.json', dict(binaries=before, source=source_before))
    results = []
    lock = root/'backups/.private-fixture.lock'
    acquired = False
    error = None
    try:
        with lock.open('x') as handle:
            acquired = True
            handle.write(str(output))
        values = native_config(lab_factory, output)
        base = Path(values['ARGUS_BASEDIR']); game = values['ARGUS_GAME']
        protected += [base/game/'progs.dat', Path(values['ARGUS_PROGS'])]
        before = identities(protected)
        save(output/'before.json', dict(binaries=before, source=source_before))
        for path in (root/'qconsole.log', base/'qconsole.log'):
            if path.exists():
                raise ValueError('harvest the pending human session before launching: '+str(path))
        # Retain exact current inputs, without installing or restoring over them.
        shutil.copytree(root/'src', output/'production-src')
        for index, path in enumerate(protected):
            if path.is_file():
                target = output/'saved-binaries'/str(index)/path.name
                target.parent.mkdir(parents=True)
                shutil.copy2(path, target)
        source = (root/'src/argus.qc').read_text()
        if fixture in {'muzzle','combat'}:
            audit_muzzle(source)
            schedule = [(v, 'dm4') for v in (('candidate','legacy') if fixture=='combat' else ('production', 'candidate', 'legacy', 'uncapped'))]
        else:
            audit_health(source)
            audit_muzzle(source)
            schedule = [('current', m) for m in ('dm2', 'dm4')]
        expected = {'candidate': [], 'legacy': ['ordinary_wall', 'ordinary_overhang'],
                    'uncapped': ['wall_behind_target']}
        save(output/'plan.json', dict(fixture=fixture, prefix=prefix, schedule=schedule,
            expected_muzzle_failures=expected, health_ids=[1], health_ring=0,
            expected_combat_failures={'candidate': [], 'legacy': ['combat_blocked']},
            source=source_before['sha256'], lab_sha256=sha(EXE), verifier_sha256=sha(Path(__file__)),
            limits='Controlled fixture evidence only. No cohorts, installation or gameplay equivalence; #583 remains unresolved.'))
        private_game = private_assets(base, game, output)
        save(output/'assets.json', tree_identity(output/'base'))
        for variant in dict.fromkeys(v for v, _ in schedule):
            folder = output/variant
            if fixture == 'health':
                prepare_health(folder, False)
                audit_private(folder, False)
            elif fixture == 'combat':
                stage_combat(root, folder, variant)
            else:
                stage_muzzle(root, folder, variant)
            (folder/'runs').mkdir()
            save(folder/'source.json', tree_identity(folder/'src'))
            env = dict(ARGUS_SRC=str(folder/'src'), ARGUS_PROGS=str(folder/'lq1/progs.dat'),
                ARGUS_RUNS=str(folder/'runs'), ARGUS_BASEDIR=str(output/'base'),
                ARGUS_GAME=game, TOKIO_WORKER_THREADS='2')
            with (folder/'lab.stderr').open('w') as err:
                lab = lab_factory(err, env)
                try:
                    compiled = lab.call('compile_qc', install=False)
                    save(folder/'compile.json', compiled)
                    if not compiled['ok'] or compiled['installed_to'] or compiled['new_errors'] or compiled['new_warnings']:
                        raise RuntimeError('private compilation failed; see compile.json')
                    binary = folder/'lq1/progs.dat'
                    shutil.copy2(binary, private_game/'progs.dat')
                    for _, map_name in (s for s in schedule if s[0] == variant):
                        stem = f'{prefix}_{variant}_{map_name}'
                        tape = folder/'runs'/f'{stem}.log'
                        if tape.exists():
                            raise ValueError('retain the colliding tape: '+str(tape))
                        (private_game/'autoexec.cfg').write_text('sv_protocol 15\nmax_edicts 600\n')
                        row = dict(variant=variant, map=map_name, name=stem,
                            source_sha256=tree_identity(folder/'src')['sha256'], binary_sha256=sha(binary))
                        try:
                            if fixture == 'health':
                                health_trial(lab, stem, map_name, env, client_run)
                            else:
                                native = lab.call('experiment', map=map_name, duration_sec=10, skill=1,
                                    compile=False, repeats=1, primary='stall_parity', run_name=stem)
                                save(folder/(stem+'.native.json'), native)
                                if not native['ok']:
                                    raise RuntimeError('private engine experiment failed')
                            text = tape.read_text(errors='replace')
                            row['tape_sha256'] = sha(tape)
                            if any(s in text for s in ('Host_Error', 'Program error', 'runaway loop', "Couldn't spawn server")):
                                raise RuntimeError('engine failure in retained tape')
                            if fixture == 'health':
                                row['perception'] = check_perception(text, map_name, 0, [1])
                                row['health'] = check_health(text, map_name, [1])
                                if not all(10 <= r['dt_ms'] <= 30 for r in row['perception']):
                                    raise RuntimeError('wrong measured fixture cadence')
                            elif fixture == 'combat':
                                row['combat']=check_combat(text)
                                if row['combat']['failures'] != ([] if variant=='candidate' else ['combat_blocked']):
                                    raise RuntimeError('unexpected combat current/control outcome')
                            elif variant != 'production':
                                row['failures'] = check_muzzle(text)
                                if row['failures'] != expected[variant]:
                                    raise RuntimeError('unexpected muzzle current/control outcome')
                            row['accepted'] = True
                        except Exception as failure:
                            row.update(accepted=False, rejection=str(failure))
                            raise
                        finally:
                            results.append(row)
                            save(output/'results.json', results)
                            print(json.dumps(dict(name=stem, accepted=row['accepted'])), flush=True)
                finally:
                    lab.close()
    except Exception as failure:
        error = str(failure)
        raise
    finally:
        after = identities(protected)
        unchanged = before == after and source_before == tree_identity(root/'src')
        save(output/'after.json', dict(binaries=after, unchanged=unchanged, error=error))
        if acquired:
            lock.unlink()
        if not unchanged:
            raise RuntimeError('protected production inputs changed; inspect before.json and after.json')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', choices=('muzzle', 'health', 'combat'))
    parser.add_argument('--output', required=True, type=Path, help='new directory beneath backups/')
    parser.add_argument('--prefix', required=True, help='private run-name prefix')
    args = parser.parse_args()
    try:
        run(args.fixture, args.output, args.prefix)
    except (OSError, ValueError, RuntimeError, AssertionError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
