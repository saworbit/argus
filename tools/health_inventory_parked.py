"""Recover the parked step1b candidate for static boundary tests, without edits."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def apply_patch_text(source,patch):
    lines=source.splitlines(keepends=True);out=[];pos=0
    for line in patch.splitlines(keepends=True)[2:]:
        if line.startswith('@@'):
            hunk=re.match(r'@@ -(\d+)(?:,(\d+))?',line)
            start=int(hunk[1])-(0 if hunk[2]=='0' else 1)
            out.extend(lines[pos:start]);pos=start
        else:
            assert line[0] in ' +-'
            if line[0] in ' -':
                assert lines[pos]==line[1:];pos+=1
            if line[0] in ' +':out.append(line[1:])
    out.extend(lines[pos:]);return ''.join(out)

def parked_source():
    folder=ROOT/'tools/fixtures'
    manifest=json.loads((folder/'health-inventory-step1b.json').read_text())
    source=(ROOT/'src/argus.qc').read_text()
    digest=lambda s:hashlib.sha256(s.encode()).hexdigest()
    assert digest(source)==manifest.get('active_text_sha256',manifest['parked_text_sha256']), 'active production source changed'
    for patch in manifest.get('production_amendments',[]):
        source=apply_patch_text(source,(folder/patch).read_text())
    assert digest(source)==manifest['parked_text_sha256'], 'parked production source changed'
    return source,manifest

def candidate_source():
    source,manifest=parked_source()
    candidate=apply_patch_text(source,(ROOT/'tools/fixtures'/manifest['patch']).read_text())
    digest=lambda s:hashlib.sha256(s.encode()).hexdigest()
    assert digest(candidate)==manifest['candidate_text_sha256'], 'candidate patch changed'
    return candidate,manifest
