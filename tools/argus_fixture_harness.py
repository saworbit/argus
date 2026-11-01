"""Private source, game and tape ownership for native fixture runners."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import shutil
import sys

from argus_names import map_name as canonical_map
from argus_validation import require
from run_behaviour_equivalence import lab_cli


def _must_be_absent(path):
    try: path.lstat()
    except FileNotFoundError: return
    raise FileExistsError(f'retain the previous directory: {path}')


def new_output(path, *, root, create=True):
    requested = Path(path)
    output, backups = requested.resolve(), (Path(root) / 'backups').resolve()
    if output == backups or not output.is_relative_to(backups):
        raise ValueError('output must be a new strict child of backups/')
    _must_be_absent(requested)
    _must_be_absent(output)
    if create:
        output.mkdir(parents=True, exist_ok=False)
    return output


def write_text(path, text):
    Path(path).write_text(text, encoding='utf-8', newline='\n')


def _remove_owned(path, claimed):
    # Every recursive cleanup is confined to the absolute directory this
    # invocation exclusively created, never a computed parent or source tree.
    if path.resolve() != claimed or path.is_symlink():
        raise RuntimeError(f'owned directory changed during cleanup: {path}')
    shutil.rmtree(path)


def stage_fixture(root, output, source=None, *, fixtures=None, frame_wrap=None, edits=None, runs=True):
    """Validate patches first, then create a new private source tree with LF."""
    source, output = Path(source or Path(root) / 'src'), Path(output).resolve()
    fixtures = fixtures or {}
    patches = {}
    for name in fixtures:
        require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.qc', name), 'invalid fixture filename')
    if fixtures:
        text = (source / 'progs.src').read_text(encoding='utf-8')
        require(text.count('\nworld.qc\n') == 1, 'expected one world.qc include')
        included = {line.split('//', 1)[0].strip() for line in text.splitlines()}
        require(all(name not in included for name in fixtures), 'fixture already included')
        patches['progs.src'] = text.replace('\nworld.qc\n', '\n' + '\n'.join(fixtures) + '\nworld.qc\n')
    if frame_wrap is not None:
        text = (source / 'world.qc').read_text(encoding='utf-8')
        require(text.count('Argus_FrameAll ();') == 1, 'expected one FrameAll call')
        patches['world.qc'] = text.replace('Argus_FrameAll ();', frame_wrap)
    for name, edit in (edits or {}).items():
        require(Path(name).name == name, 'source edit must name a file')
        patches[name] = edit((source / name).read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=False)
    claimed = output.resolve()
    try:
        src = output / 'src'
        shutil.copytree(source, src)
        (output / 'lq1').mkdir()
        if runs: (output / 'runs').mkdir()
        for name, text in {**fixtures, **patches}.items():
            write_text(src / name, text)
        return src
    except BaseException:
        try: _remove_owned(output, claimed)
        except Exception as error: print(f'fixture staging cleanup failed: {error!r}', file=sys.stderr)
        raise


def installed_identity(root):
    result = {}
    for name in ('game/argus/progs.dat', 'engine/argus/progs.dat', 'lq1/progs.dat'):
        path = Path(root) / name
        try: result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError: result[name] = None
    return result


@contextmanager
def private_game(root, prefix, family, *, autoexec=None):
    require(re.fullmatch(r'[a-z0-9_]{1,48}', prefix), 'invalid private prefix')
    require(re.fullmatch(r'[a-z0-9_]+', family), 'invalid private game family')
    root = Path(root)
    requested = root / 'engine' / (family + '_' + prefix)
    _must_be_absent(requested)
    folder = requested.resolve()
    require(folder.parent == (root / 'engine').resolve(), 'private game escaped engine/')
    before = installed_identity(root)
    folder.mkdir(exist_ok=False)
    claimed = folder.resolve()
    try:
        for name in ('progs', 'maps', 'sound', 'gfx'):
            source = root / 'engine/argus' / name
            if source.exists(): shutil.copytree(source, folder / name)
        if autoexec is None:
            autoexec = (root / 'game/argus/autoexec.cfg').read_text(encoding='utf-8')
        write_text(folder / 'autoexec.cfg', autoexec)
    except BaseException:
        try: _remove_owned(folder, claimed)
        except Exception as error: print(f'private asset cleanup failed: {error!r}', file=sys.stderr)
        raise
    failed = None
    try:
        yield folder
    except BaseException as error:
        failed = error
        raise
    finally:
        try:
            require(installed_identity(root) == before, 'installed progs.dat changed during private fixture')
        except Exception as error:
            if failed is None: raise
            failed.add_note(str(error))
            print(f'private fixture protection failed: {error!r}', file=sys.stderr)


def check_tape(text, map_name=None):
    require(not any(s in text for s in ('Host_Error', 'Program error', 'runaway loop error')), 'engine error in tape')
    maps = re.findall(r'^ARGUS init on (\S+)\r?$', text, re.M)
    valid = maps == [canonical_map(map_name)] if map_name is not None else len(maps) <= 1
    require(valid, f'wrong or repeated map init: {maps}')


def read_tape(output, name, map_name):
    require(re.fullmatch(r'[a-z0-9_]{1,80}', name), 'invalid fixture run name')
    path = Path(output) / 'runs' / (name + '.log')
    text = path.read_text(encoding='utf-8', errors='replace')
    check_tape(text, map_name)
    return path, text


def frame_ms(text, marker, ticrate):
    require(ticrate in (.0139, .1), 'use played or 100 ms cadence')
    starts = re.findall(r'^' + re.escape(marker) + r' begin dt_ms\s+([\d.]+)(?:\s|$)', text, re.M)
    require(len(starts) == sum(line.startswith(marker + ' begin') for line in text.splitlines()) == 1,
            'missing or repeated measured cadence')
    measured = float(starts[0])
    require((90 <= measured <= 110) if ticrate == .1 else (10 <= measured <= 30), 'wrong measured cadence')
    return measured


def run_match(lab, map_name, seconds, name, *, port=None, timeout=None, environment=None, stderr_path=None, skill=2):
    map_name = canonical_map(map_name)
    require(re.fullmatch(r'[a-z0-9_]{1,80}', name), 'invalid fixture run name')
    require(10 <= seconds <= 600, 'invalid fixture duration')
    if port is None:
        return lab.call('match_run', map=map_name, duration_sec=seconds, skill=skill, run_name=name)
    require(1024 <= port <= 65535, 'invalid fixture port')
    result = lab_cli(lab.executable, 'match', map_name, seconds, name, '--skill', skill, '--port', port,
                     environment=environment, timeout=timeout or seconds + 45)
    if stderr_path is not None: write_text(stderr_path, result.stderr)
    require(result.returncode == 0, result.stderr)
    import json
    return json.loads(result.stdout)
