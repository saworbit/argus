"""The compiled-source identity shared by Python study receipts."""
import hashlib
from pathlib import Path


def source_identity(src_dir):
    """Hash sorted QC/SRC paths as src/<relative>, NUL, then file bytes.

    The source directory's absolute location and graph sidecars are excluded.
    Whole-tree source.json manifests are a separate, broader audit identity.
    """
    src_dir = Path(src_dir)
    if not src_dir.is_dir():
        raise FileNotFoundError(f'source directory missing: {src_dir}')
    files = sorted((p for p in src_dir.rglob('*') if p.is_file()
                    and p.suffix.lower() in ('.qc', '.src')),
                   key=lambda p: p.relative_to(src_dir).parts)
    if not files:
        raise ValueError(f'no QC/SRC inputs in {src_dir}')
    digest = hashlib.sha256()
    for path in files:
        digest.update(('src/' + path.relative_to(src_dir).as_posix()).encode('utf-8'))
        digest.update(b'\0')
        digest.update(path.read_bytes())
    return digest.hexdigest()
