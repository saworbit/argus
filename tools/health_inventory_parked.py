"""Recover frozen step1b evidence and verify the declared active bodies.

Run as a script to amend the manifest after any edit to src/argus.qc, a
comment-only one included (#871):

  python tools/health_inventory_parked.py --amend <name> --base <rev> --scope "<what it reverses>"

<rev> is the revision whose src/argus.qc the manifest pins now, usually main.
The helper writes tools/fixtures/<name>-reverse.patch, which takes the working
src/argus.qc back to that text, puts it at the front of production_amendments,
extends amendment_scope, re-pins active_text_sha256 and any active function
hash whose body changed, and replays the whole chain to the frozen parked text
in memory before it writes anything. It refuses when <rev>'s text does not
match the current pin, so the chain stays continuous. It also reports whether
the edit changed only comments and layout, by the build stamp's rule, which
marks a change that cannot affect play. --dry-run checks and reports without
writing.
"""
from argus_validation import require
import argparse
import copy
import difflib
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tools/fixtures'
MANIFEST='health-inventory-step1b.json'

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def apply_patch_text(source,patch):
    lines=source.splitlines(keepends=True);out=[];pos=0
    for line in patch.splitlines(keepends=True)[2:]:
        if line.startswith('@@'):
            hunk=re.match(r'@@ -(\d+)(?:,(\d+))?',line)
            require(hunk is not None, 'malformed reverse patch hunk')
            start=int(hunk[1])-(0 if hunk[2]=='0' else 1)
            out.extend(lines[pos:start]);pos=start
        else:
            require((line[0] in ' +-'))
            if line[0] in ' -':
                require((lines[pos]==line[1:]));pos+=1
            if line[0] in ' +':out.append(line[1:])
    out.extend(lines[pos:]);return ''.join(out)

def function_text(source,name):
    match=re.search(r'^[^\n]*\b'+re.escape(name)+r'\s*=\s*\n\{\n.*?^\};',source,re.M|re.S)
    return match[0] if match else None

def replay(source,manifest,read_patch):
    """Check source against the active pins, then reverse every amendment."""
    require((digest(source)==manifest.get('active_text_sha256',manifest['parked_text_sha256'])), 'active production source changed')
    for name,expected in manifest.get('active_functions',{}).items():
        text=function_text(source,name)
        require((text and digest(text)==expected), 'active function changed: '+name)
    for patch in manifest.get('production_amendments',[]):
        source=apply_patch_text(source,read_patch(patch))
    require((digest(source)==manifest['parked_text_sha256']), 'parked production source changed')
    return source

def read_fixture(name):
    return (FIXTURES/name).read_text()

def parked_source(root=ROOT):
    fixtures = root / 'tools/fixtures'
    manifest = json.loads((fixtures / MANIFEST).read_text(encoding='utf-8'))
    source = (root / 'src/argus.qc').read_text(encoding='utf-8')
    return replay(source, manifest, lambda name: (fixtures / name).read_text(encoding='utf-8')), manifest

def candidate_source(root=ROOT):
    source,manifest=parked_source(root)
    candidate=apply_patch_text(source,(root/'tools/fixtures'/manifest['patch']).read_text(encoding='utf-8'))
    require((digest(candidate)==manifest['candidate_text_sha256']), 'candidate patch changed')
    return candidate,manifest

def reverse_patch(new,base):
    """A diff -u patch, in apply_patch_text's dialect, from new back to base."""
    return ''.join(difflib.unified_diff(new.splitlines(True),base.splitlines(True),
                                        'a/src/argus.qc','b/src/argus.qc'))

def amend(manifest,base,new,name,scope,read_patch=read_fixture):
    """Return the amended manifest, the reverse patch and a report.

    base is the text the manifest pins now and new the edited text. Nothing is
    written: the caller saves the patch and manifest once this returns, and it
    returns only after the amended chain replays to the frozen parked text.
    """
    from argus_build_stamp import normalise
    require(bool(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',name or '')),
            'the name must be lower-case words joined by hyphens, got '+repr(name))
    patch_name=name+'-reverse.patch'
    amendments=list(manifest.get('production_amendments',[]))
    require(patch_name not in amendments, patch_name+' is already in production_amendments')
    pin=manifest.get('active_text_sha256',manifest['parked_text_sha256'])
    require(digest(base)==pin, 'the base text does not hash to the pinned active source '+pin+
            '; pass the revision the manifest pins now')
    require(new!=base, 'src/argus.qc matches the base text, so there is nothing to amend')
    require(base.endswith('\n') and new.endswith('\n'), 'both texts must end with a newline')
    scope=' '.join((scope or '').split())
    require(bool(scope), 'the scope must say what the amendment reverses')
    old_scope=manifest['amendment_scope']
    require(old_scope.startswith('Reverse '), 'amendment_scope does not start with "Reverse "')
    patch=reverse_patch(new,base)
    require(apply_patch_text(new,patch)==base, 'the reverse patch does not recover the base text')
    updated=copy.deepcopy(manifest)
    updated['production_amendments']=[patch_name]+amendments
    updated['amendment_scope']='Reverse '+scope+' in memory, then r'+old_scope[1:]
    updated['active_text_sha256']=digest(new)
    changed=[]
    for function,expected in manifest.get('active_functions',{}).items():
        text=function_text(new,function)
        require(text is not None, 'active function not found in the new text: '+function)
        if digest(text)!=expected:
            updated['active_functions'][function]=digest(text);changed.append(function)
    replay(new,updated,lambda p:patch if p==patch_name else read_patch(p))
    report={'patch':patch_name,'hunks':patch.count('\n@@ '),
            'comment_only':normalise(new)==normalise(base),'functions':changed}
    return updated,patch,report

def git_text(rev,path='src/argus.qc'):
    """A file at a revision, decoded the way Path.read_text decodes the work tree."""
    result=subprocess.run(['git','show',rev+':'+path],cwd=ROOT,capture_output=True)
    require(result.returncode==0, 'git show '+rev+':'+path+' failed: '+
            result.stderr.decode(errors='replace').strip())
    return io.TextIOWrapper(io.BytesIO(result.stdout)).read()

def main(argv=None):
    parser=argparse.ArgumentParser(description='Amend the step1b production source manifest after an edit to src/argus.qc.')
    parser.add_argument('--amend',metavar='NAME',required=True,
                        help='writes tools/fixtures/NAME-reverse.patch')
    parser.add_argument('--base',metavar='REV',required=True,
                        help='the revision whose src/argus.qc the manifest pins now, usually main')
    parser.add_argument('--scope',required=True,
                        help='what the patch reverses, as it reads after "Reverse " in amendment_scope')
    parser.add_argument('--dry-run',action='store_true',help='check and report without writing')
    args=parser.parse_args(argv)
    try:
        path=FIXTURES/(args.amend+'-reverse.patch')
        require(not path.exists(), str(path.relative_to(ROOT))+' already exists')
        manifest=json.loads((FIXTURES/MANIFEST).read_text())
        new=(ROOT/'src/argus.qc').read_text()
        updated,patch,report=amend(manifest,git_text(args.base),new,args.amend,args.scope)
    except AssertionError as error:
        print('refused: '+str(error),file=sys.stderr)
        return 1
    if not args.dry_run:
        path.write_text(patch,newline='\n')
        (FIXTURES/MANIFEST).write_text(json.dumps(updated,indent=2)+'\n',newline='\n')
    verb='would write' if args.dry_run else 'wrote'
    hunks=f"{report['hunks']} hunk"+('' if report['hunks']==1 else 's')
    print(f"{verb} tools/fixtures/{report['patch']} ({hunks}) and {MANIFEST}")
    print('active_text_sha256 '+updated['active_text_sha256'])
    print('active functions re-pinned: '+(', '.join(report['functions']) or 'none'))
    print('comments and layout only: '+('yes, so the build stamp and play are unchanged' if report['comment_only']
                                       else 'no, the edit changes compiled code'))
    print('the amended chain replays to the frozen parked text')
    return 0

if __name__=='__main__':
    sys.exit(main())
