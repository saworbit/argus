#!/usr/bin/env python3
"""Move an Argus MCP client entry from Cargo target to the stable install."""

import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parent.parent
OLD_COMMAND = "tools/argus_mcp/target/release/argus-mcp"
NEW_COMMAND = "tools/argus_mcp/install/bin/argus-mcp"


def stable_command(command):
    if not isinstance(command, str):
        return None
    normalized = command.replace("\\", "/")
    lowered = normalized.lower()
    for extension in (".exe", ""):
        old = OLD_COMMAND + extension
        if not lowered.endswith(old):
            continue
        start = len(normalized) - len(old)
        if start and normalized[start - 1] != "/":
            continue
        return normalized[:start] + NEW_COMMAND + extension
    return None


def has_command_suffix(command, suffix):
    if not isinstance(command, str):
        return False
    normalized = command.replace("\\", "/").lower()
    for extension in (".exe", ""):
        expected = suffix + extension
        if normalized.endswith(expected):
            start = len(normalized) - len(expected)
            if not start or normalized[start - 1] == "/":
                return True
    return False


def read_text(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def atomic_write(path, text):
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        shutil.copymode(path, temporary)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def verify_installed_binary(command):
    binary = Path(command)
    if not binary.is_absolute():
        binary = ROOT / binary
    if not binary.is_file():
        raise ValueError(
            f"stable installed binary not found at {binary}; run the documented cargo install first"
        )


def argus_json(data):
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    entry = servers.get("argus") if isinstance(servers, dict) else None
    return entry if isinstance(entry, dict) else None


def migrate_json(path, text):
    before = json.loads(text)
    entry = argus_json(before)
    if entry is None:
        return "skip", "no argus MCP entry"
    command = entry.get("command")
    replacement = stable_command(command)
    if replacement is None:
        if has_command_suffix(command, NEW_COMMAND):
            verify_installed_binary(command)
            return "ok", "already uses the stable installed binary"
        return "unchanged", "argus command does not match the retired release path"

    verify_installed_binary(replacement)
    expected = copy.deepcopy(before)
    argus_json(expected)["command"] = replacement
    rendered = json.dumps(expected, indent=2, ensure_ascii=False) + "\n"
    verified = json.loads(rendered)
    if verified != expected:
        raise ValueError("verification changed fields outside the argus command")
    atomic_write(path, rendered)
    if json.loads(read_text(path)) != expected:
        raise ValueError("saved JSON did not verify")
    return "migrated", f"{command} -> {replacement}"


def argus_toml(data):
    servers = data.get("mcp_servers") if isinstance(data, dict) else None
    entry = servers.get("argus") if isinstance(servers, dict) else None
    return entry if isinstance(entry, dict) else None


def migrate_toml(path, text):
    before = tomllib.loads(text)
    entry = argus_toml(before)
    if entry is None:
        return "skip", "no argus MCP entry"
    command = entry.get("command")
    replacement = stable_command(command)
    if replacement is None:
        if has_command_suffix(command, NEW_COMMAND):
            verify_installed_binary(command)
            return "ok", "already uses the stable installed binary"
        return "unchanged", "argus command does not match the retired release path"

    verify_installed_binary(replacement)
    header = re.search(r"(?m)^[ \t]*\[mcp_servers\.argus\][^\r\n]*(?:\r?\n|$)", text)
    if header is None:
        raise ValueError("parsed argus entry has no editable [mcp_servers.argus] table")
    next_header = re.search(r"(?m)^[ \t]*\[", text[header.end() :])
    end = header.end() + next_header.start() if next_header else len(text)
    block = text[header.end() : end]
    command_line = re.search(
        r"(?m)^(?P<prefix>[ \t]*command[ \t]*=[ \t]*)"
        r"(?P<value>\"(?:\\.|[^\"\\])*\"|'[^']*')"
        r"(?P<suffix>[ \t]*(?:#[^\r\n]*)?)(?P<eol>\r?\n|$)",
        block,
    )
    if command_line is None:
        raise ValueError("parsed argus command has no editable command line")
    new_line = (
        command_line.group("prefix")
        + json.dumps(replacement)
        + command_line.group("suffix")
        + command_line.group("eol")
    )
    rewritten_block = block[: command_line.start()] + new_line + block[command_line.end() :]
    rendered = text[: header.end()] + rewritten_block + text[end:]

    expected = copy.deepcopy(before)
    argus_toml(expected)["command"] = replacement
    if tomllib.loads(rendered) != expected:
        raise ValueError("verification changed fields outside the argus command")
    atomic_write(path, rendered)
    if tomllib.loads(read_text(path)) != expected:
        raise ValueError("saved TOML did not verify")
    return "migrated", f"{command} -> {replacement}"


def migrate(path):
    text = read_text(path)
    if path.suffix.lower() == ".toml":
        return migrate_toml(path, text)
    if path.suffix.lower() == ".json":
        return migrate_json(path, text)
    raise ValueError("supported config suffixes are .toml and .json")


def default_paths():
    home = Path.home()
    candidates = [
        home / ".codex" / "config.toml",
        ROOT / ".codex" / "config.toml",
        home / ".grok" / "config.toml",
        ROOT / ".mcp.json",
        Path.cwd() / ".mcp.json",
    ]
    found = []
    seen = set()
    for path in candidates:
        absolute = path.resolve()
        if absolute in seen or not path.is_file():
            continue
        seen.add(absolute)
        found.append(path)
    return found


def main():
    parser = argparse.ArgumentParser(
        description="Migrate the Argus MCP command from Cargo target to install/bin."
    )
    parser.add_argument(
        "configs",
        nargs="*",
        type=Path,
        help="TOML or JSON config. With none, check the known Codex, Grok and project paths.",
    )
    args = parser.parse_args()
    paths = args.configs or default_paths()
    if not paths:
        print("error: no supported MCP config found; pass a TOML or JSON config path", file=sys.stderr)
        return 1

    failed = False
    migrated = False
    for path in paths:
        if not path.is_file():
            print(f"error: {path}: file not found", file=sys.stderr)
            failed = True
            continue
        try:
            status, detail = migrate(path)
            print(f"{status}: {path}: {detail}")
            migrated = migrated or status == "migrated"
        except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
            print(f"error: {path}: {error}", file=sys.stderr)
            failed = True

    if migrated:
        print("restart the MCP client; a client that already attempted startup keeps the failed state")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
