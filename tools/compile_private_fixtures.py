"""Compile maintained private fixture sources without a lab, engine or map assets.

Use the same pinned FTEQCC build as compile.yml. Every invocation needs a new
output directory. Sources, logs and receipts are retained there, including on
failure. This checks compilation only, not native fixture outcomes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = {
    'muzzle': ('candidate', 'legacy', 'uncapped'),
    'combat': ('candidate', 'legacy'),
    'health': ('current',),
    'button': ('candidate', 'disabled'),
    'door': ('candidate', 'direct_only', 'overlap_only'),
    'plan': ('current', 'legacy_reset', 'deadline_control', 'opening_control'),
    'offset': ('current', 'old_handoff'),
    'freeze': ('current',),
    'mover': ('current',),
    'forecast': ('current',),
    'camera': ('current',),
    'attention': ('current',),
    'water': ('current',),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def inputs(root):
    paths = list((root/'src').rglob('*')) + [root/p for p in
        ('game/argus/progs.dat', 'engine/argus/progs.dat', 'lq1/progs.dat')]
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(paths)
            if p.is_file() or p.name == 'progs.dat'}


def stage(folder, family, variant):
    """Reuse native verifier staging, without configuration or engine startup."""
    # Import lazily: --help needs only Python's standard library.
    from verify_private_fixtures import stage_muzzle, stage_combat, stage_button, stage_door
    if family == 'camera':
        from verify_camera_chase import stage as stage_camera
        stage_camera(ROOT, folder)
    elif family == 'forecast':
        from verify_mover_forecast import stage as stage_forecast
        stage_forecast(ROOT, folder)
    elif family == 'water':
        from verify_water_route import stage as stage_water
        stage_water(ROOT, folder)
    elif family == 'attention':
        from verify_target_attention import stage as stage_attention
        stage_attention(ROOT, folder)
    elif family == 'mover':
        from verify_mover_transfer import stage as stage_mover
        stage_mover(ROOT, folder)
    elif family == 'freeze':
        from verify_freeze_recovery import stage as stage_freeze
        stage_freeze(ROOT, folder)
    elif family == 'health':
        from run_health_fixture import prepare, audit_private
        prepare(folder, False)
        audit_private(folder, False)
    elif family == 'plan':
        from verify_plan_progress import prepare
        prepare(folder, legacy=variant == 'legacy_reset',
                deadline_control=variant == 'deadline_control',
                opening_control=variant == 'opening_control')
    elif family == 'offset':
        from verify_offset_entry import stage_offset
        stage_offset(folder, variant)
    else:
        {'muzzle': stage_muzzle, 'combat': stage_combat,
         'button': stage_button, 'door': stage_door}[family](ROOT, folder, variant)


def compile_one(compiler, folder, run=subprocess.run):
    """Require a fresh id-format binary and finish line, even for exit code zero."""
    binary = folder/'lq1/progs.dat'
    if binary.exists():
        raise ValueError('staged output already exists: '+str(binary))
    source_hashes = {p.relative_to(folder/'src').as_posix(): digest(p)
                     for p in sorted((folder/'src').rglob('*')) if p.is_file()}
    receipt = dict(compiler_sha256=digest(compiler), source_sha256=source_hashes, ok=False)
    try:
        result = run([str(compiler)], cwd=folder/'src', capture_output=True,
                     text=True, encoding='utf-8', errors='replace', timeout=90)
        text = result.stdout + result.stderr
        (folder/'compile.log').write_text(text, encoding='utf-8')
        receipt.update(returncode=result.returncode, binary_sha256=digest(binary))
        if result.returncode or not re.search(r'Compile finished[^\r\n]*id format', text):
            raise RuntimeError('compiler failed or no id-format finish line; see '+str(folder/'compile.log'))
        if not binary.is_file() or binary.stat().st_size < 60:
            raise RuntimeError('compiler did not write a fresh progs.dat')
        if int.from_bytes(binary.read_bytes()[:4], 'little') != 6:
            raise RuntimeError('output is not an id-format progs.dat')
        receipt['ok'] = True
    except Exception as error:
        if isinstance(error, subprocess.TimeoutExpired):
            partial = (error.stdout or b'')
            if isinstance(partial, bytes):
                partial = partial.decode('utf-8', errors='replace')
            (folder/'compile.log').write_text(partial+'\nCompiler timed out after 90 seconds.\n', encoding='utf-8')
        receipt['error'] = str(error)
        raise
    finally:
        (folder/'compile.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    return receipt


def compile_families(compiler, output, families, root=ROOT):
    """Compile serially in a new owned output; never install or delete evidence."""
    root, compiler, output = root.resolve(), compiler.resolve(), output.resolve()
    if not compiler.is_file():
        raise ValueError('compiler executable is missing')
    if not families or any(f not in VARIANTS for f in families) or len(set(families)) != len(families):
        raise ValueError('choose distinct maintained fixture families')
    if output == root or root.is_relative_to(output) or any(
            output.is_relative_to(root/p) for p in ('src', 'game', 'engine', 'lq1', '.git', 'tools')):
        raise ValueError('output must be outside protected source, tools and game directories')
    if output.exists():
        raise ValueError('output must be a new directory; retain previous evidence')
    before = inputs(root)
    lock = root/'backups/.private-fixture.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    # Shared with the native private verifier, so their compilers cannot overlap.
    lock.open('x').close()
    try:
        output.mkdir(parents=True)
        rows = []
        try:
            for family in families:
                for variant in VARIANTS[family]:
                    folder = output/family/variant
                    stage(folder, family, variant)
                    row = compile_one(compiler, folder)
                    rows.append(dict(family=family, variant=variant, **row))
                    print(f'{family}/{variant}: id-format compile passed', flush=True)
        finally:
            after = inputs(root)
            (output/'results.json').write_text(json.dumps(dict(
                compiler_sha256=digest(compiler), families=families,
                results=rows, protected_before=before, protected_after=after,
                unchanged=before == after), indent=2)+'\n', encoding='utf-8')
            if before != after:
                raise RuntimeError('protected source or game binaries changed')
    finally:
        lock.unlink()
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True, help='pinned FTEQCC executable')
    parser.add_argument('--output', type=Path, required=True, help='new private directory; outputs are retained')
    parser.add_argument('--family', choices=['all', *VARIANTS], default='all',
                        help='one bounded family, or all families serially (default: all)')
    args = parser.parse_args()
    compile_families(args.compiler, args.output,
                     list(VARIANTS) if args.family == 'all' else [args.family])


if __name__ == '__main__':
    main()
