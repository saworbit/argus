"""Copy new Argus evidence into append-only, verified backup batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


FIXTURE_EXTENSIONS = {
    ".log",
    ".dem",
    ".json",
    ".tsv",
    ".csv",
    ".stdout",
    ".stderr",
    ".timing",
    ".webm",
    ".mp4",
}
KNOWLEDGE = (
    "tools/lab_claims.json",
    "tools/lab_objective.json",
    "tools/refuted_claims.json",
    "tools/lab_instruments.json",
    "docs/lab-spine.md",
    "docs/telemetry.md",
    "docs/lab-workflow.md",
    "docs/specs/2026-09-16-lab-measurement-limits.md",
)
CHUNK_SIZE = 1024 * 1024


class FileStillChanging(Exception):
    """An active writer changed the file during a backup attempt."""


def stamp(info):
    return info.st_mtime_ns, info.st_size


def tree(root, prefix, extensions=None):
    directories = [root]
    while directories:
        directory = directories.pop()
        try:
            with os.scandir(directory) as children:
                for entry in children:
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if (
                        getattr(info, "st_file_attributes", 0)
                        & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    ):
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        directories.append(Path(entry.path))
                        continue
                    path = Path(entry.path)
                    if stat.S_ISREG(info.st_mode) and path.suffix.lower() != ".tmp":
                        if extensions is None or path.suffix.lower() in extensions:
                            yield (
                                (prefix / path.relative_to(root)).as_posix(),
                                path,
                                info,
                            )
        except FileNotFoundError:
            if directory == root:
                raise


def evidence(root):
    yield from tree(root / "runs", Path("runs"))
    if (root / "backups").is_dir():
        yield from tree(root / "backups", Path("fixture-evidence"), FIXTURE_EXTENSIONS)
    if (root / "benchmarks").is_dir():
        yield from tree(root / "benchmarks", Path("knowledge/benchmarks"), {".json"})
    for name in KNOWLEDGE:
        path = root / name
        if path.is_file():
            yield "knowledge/" + name, path, path.stat()


def seed_entries(seed):
    with (seed / "sha256-manifest.jsonl").open(encoding="utf-8") as manifest:
        for line in manifest:
            row = json.loads(line)
            if row["source_matches"]:
                yield row["path"], row
    supplement = seed / "supplement-verification.json"
    if supplement.is_file():
        for row in json.loads(supplement.read_text(encoding="utf-8"))["verified"]:
            yield row["path"].removeprefix("supplement/"), row


def load_index(db, root, seed):
    db.execute("CREATE TABLE IF NOT EXISTS settings (root TEXT PRIMARY KEY)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS files ("
        "path TEXT PRIMARY KEY, mtime_ns INTEGER, size INTEGER, sha256 TEXT, stored_at TEXT)"
    )
    saved = db.execute("SELECT root FROM settings").fetchone()
    if saved is not None:
        if saved[0] != str(root):
            raise ValueError(f"Backup index belongs to {saved[0]}")
        return dict((row[0], row[1:]) for row in db.execute("SELECT * FROM files"))
    db.execute("INSERT INTO settings VALUES (?)", (str(root),))
    previous = {}
    if seed is not None:
        summary = json.loads((seed / "backup-summary.json").read_text(encoding="utf-8"))
        if (
            Path(summary["source"]).resolve() != root
            or summary["unresolved_verification_differences"]
        ):
            raise ValueError("Seed must be a verified snapshot of this checkout")
        for logical, row in seed_entries(seed):
            stored = seed / row["path"]
            if not stored.is_relative_to(seed) or ".." in Path(row["path"]).parts:
                raise ValueError(f"Invalid seed path: {row['path']}")
            info = stored.stat()
            if info.st_size != row["bytes"]:
                raise ValueError(f"Seed size differs from its manifest: {stored}")
            previous[logical] = (*stamp(info), row["sha256"], str(stored))
        db.executemany(
            "INSERT INTO files VALUES (?, ?, ?, ?, ?)",
            ((name, *entry) for name, entry in previous.items()),
        )
    return previous


def chunks(stream):
    return iter(lambda: stream.read(CHUNK_SIZE), b"")


def save(source, info, destination, previous):
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    temp = None
    try:
        with source.open("rb") as original:
            if stamp(os.fstat(original.fileno())) != stamp(info):
                raise FileStillChanging
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, delete=False
            ) as copy:
                temp = Path(copy.name)
                for chunk in chunks(original):
                    digest.update(chunk)
                    copy.write(chunk)
                copy.flush()
                os.fsync(copy.fileno())
            if stamp(os.fstat(original.fileno())) != stamp(info) or stamp(
                source.stat()
            ) != stamp(info):
                raise FileStillChanging
        checksum = digest.hexdigest()
        if previous and previous[2] == checksum and Path(previous[3]).is_file():
            return (*stamp(info), checksum, previous[3])
        copied = hashlib.sha256()
        with temp.open("rb") as stream:
            for chunk in chunks(stream):
                copied.update(chunk)
        if copied.hexdigest() != checksum:
            raise OSError(f"Copied bytes failed verification: {destination}")
        os.utime(temp, ns=(info.st_atime_ns, info.st_mtime_ns))
        temp.replace(destination)
        return (*stamp(info), checksum, str(destination))
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def backup(root, destination, seed):
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("Backup destination must be separate from the source tree")
    if not (root / "runs").is_dir():
        raise ValueError(f"Telemetry directory does not exist: {root / 'runs'}")
    destination.mkdir(parents=True, exist_ok=True)
    batch = (
        destination
        / "updates"
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    )
    batch = batch.with_name(f"{batch.name}-{os.getpid()}")
    copies, deferred, errors = [], [], []
    scanned = 0
    with closing(sqlite3.connect(destination / "index.sqlite3", timeout=0)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        previous = load_index(db, root, seed)
        for logical, source, info in evidence(root):
            scanned += 1
            old = previous.get(logical)
            if old and old[:2] == stamp(info):
                continue
            target = batch / logical
            try:
                saved = save(source, info, target, old)
            except (FileStillChanging, FileNotFoundError):
                deferred.append(logical)
                continue
            except OSError as error:
                errors.append({"path": logical, "error": str(error)})
                continue
            db.execute(
                "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?)", (logical, *saved)
            )
            if saved[3] == str(target):
                copies.append({"path": logical, "bytes": saved[1], "sha256": saved[2]})
        summary = {
            "scanned": scanned,
            "copied": len(copies),
            "deferred": deferred,
            "errors": errors,
        }
        if copies or deferred or errors:
            batch.mkdir(parents=True, exist_ok=True)
            (batch / "manifest.json").write_text(
                json.dumps({**summary, "files": copies}, indent=2) + "\n",
                encoding="utf-8",
            )
            summary["batch"] = str(batch)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--seed", type=Path, help="Previously verified Argus snapshot")
    args = parser.parse_args()
    result = backup(
        args.source.resolve(),
        args.destination.resolve(),
        args.seed.resolve() if args.seed else None,
    )
    print(json.dumps(result, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
