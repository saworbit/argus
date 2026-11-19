"""Find machine-local lab inputs consistently across checkouts and worktrees."""
import os
from pathlib import Path
import shutil
import subprocess


def common_checkout(root):
    """Return the main checkout behind a linked worktree, when available."""
    if not (root / '.git').is_file():
        return None
    try:
        result = subprocess.run(
            ['git', '-C', str(root), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    common = Path(result.stdout.strip())
    if common.name == '.git' and common.parent != root.resolve():
        return common.parent
    return None


def local_roots(root):
    root = Path(root)
    return [path for path in (root, common_checkout(root)) if path is not None]


class LabMissing(FileNotFoundError):
    """The selected native lab binary does not exist."""

    def __init__(self, searched):
        super().__init__(
            f'no lab binary at {searched}. Build one with '
            '`cargo build --manifest-path tools/argus_mcp/Cargo.toml --bin argus-mcp` '
            'or set ARGUS_LAB to a lab you have already built.'
        )


def lab_binary(root, override=None):
    """Return an absolute executable path, or None if default discovery finds none."""
    selected = override or os.environ.get('ARGUS_LAB')
    if selected:
        path = Path(selected).expanduser().resolve()
        if not path.is_file():
            raise LabMissing(path)
        return str(path)
    name = 'argus-mcp.exe' if os.name == 'nt' else 'argus-mcp'
    for base in local_roots(root):
        for directory in ('target-stage/release', 'install/bin', 'target/release', 'target/debug'):
            path = base / 'tools/argus_mcp' / directory / name
            if path.is_file():
                return str(path.resolve())
    which = shutil.which('argus-mcp')
    return str(Path(which).resolve()) if which else None


def bsp_path(root, mapname):
    """Return the first existing named BSP from the configured and checkout paths."""
    if not mapname:
        return None
    folders = [os.environ.get('ARGUS_MAPS')]
    for base in local_roots(root):
        folders.extend((base / 'maps_local', base / 'engine' / 'argus' / 'maps'))
    for folder in folders:
        if folder:
            path = Path(folder) / f'{mapname}.bsp'
            if path.is_file():
                return path
    return None
