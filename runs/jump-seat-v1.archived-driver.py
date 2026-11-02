import json,re,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import verify_water_route as wr
from argus_fixture_harness import private_game,run_match,read_tape
from run_behaviour_equivalence import Lab,finish_lab
from argus_source import source_identity
from run_map_intelligence import digest,write
CANDIDATE=any('candidate'==a for a in sys.argv[1:])
DIAGNOSTIC='diagnostic' in sys.argv
OUT=ROOT/('backups/jump_seat_diagnostic_20261102' if DIAGNOSTIC else 'backups/jump_seat_candidate_20261102' if CANDIDATE else 'backups/jump_seat_probe_20261102')
HULLPROBE='hull' in sys.argv
if HULLPROBE:OUT=ROOT/'backups/jump_seat_hull_diagnostic_20261102'
SPEC={'dm3':(73,86),'e1m5':(19,28),'e1m6':(167,160),'lqdm2':(159,162)}
def env(folder=None,rate=.0139):
 d=dict(ARGUS_SRC=str(OUT/'src'),ARGUS_PROGS=str(OUT/'lq1/progs.dat'),ARGUS_RUNS=str(OUT/'runs'),ARGUS_PYTHON=sys.executable,ARGUS_TICRATE=str(rate))
 if folder:d['ARGUS_GAME']=folder.name
 return d
def lab(err,environment):
 l=Lab(err,environment,exe=ROOT/'tools/argus_mcp/target/debug/argus-mcp.exe',timeout=45)
 p=l.call('see',what='project')
 if not p['lab_identity']['authoritative']:raise ValueError('stale lab')
 return l
if sys.argv[1]=='prepare':
 wr.stage(ROOT,OUT)
 p=OUT/'src/water_route_fixture.qc';text=p.read_text()
 start=text.index('    if (mapname == "e1m5")')
 end=text.index('    b = argus_bots;',start)
 branches=[]
 for m,(a,b) in SPEC.items():
  nodes=json.loads((ROOT/f'src/argus_nav_{m}.qc.json').read_text())['nodes']
  vec=lambda n:' '.join(f'{v:.0f}' for v in n)
  branches.append(('    if' if not branches else '    else if')+f' (mapname == "{m}")\n    {{ wr_seed = \'{vec(nodes[a])}\'; wr_target = \'{vec(nodes[b])}\'; }}\n')
 text=text[:start]+''.join(branches)+'    else { error ("JSEAT wrong map"); return; }\n'+text[end:]
 text=text.replace('if (wr_case >= 3 && wr_case <= 9)','if (wr_case == 1 || (wr_case >= 3 && wr_case <= 9))')
 text=text.replace('if (wr_bot.ar_feettype == CONTENT_WATER) completed = 0;', 'if (wr_bot.ar_feettype == CONTENT_WATER || wr_bot.ar_feettype == CONTENT_LAVA || wr_bot.ar_feettype == CONTENT_SLIME || wr_bot.groundentity != world) completed = 0;')
 if CANDIDATE:
  text=text.replace('    dprint ("BHVRPL begin water_route', '''    b = find (world, classname, "argus_node");
    while (b != world)
    {
        if (mapname == "e1m5" && vlen (b.origin - '-1303 2185 24') < 1) setorigin (b, '-1271 2185 24');
        b = find (b, classname, "argus_node");
    }
    dprint ("BHVRPL begin water_route''')
 if DIAGNOSTIC:
  text=text.replace('    dprint ("BHVRPL begin water_route', '''    dprint ("JSEAT target_contents "); dprint (ftos (pointcontents (wr_target)));
    traceline (wr_target, wr_target, TRUE, self);
    dprint (" startsolid "); dprint (ftos (trace_startsolid));
    dprint (" allsolid "); dprint (ftos (trace_allsolid)); dprint ("\\n");
    dprint ("BHVRPL begin water_route''')
 if HULLPROBE:
  text=text.replace('local entity b, saved;', 'local entity b, saved, probe;\n    local float fit;')
  text=text.replace('    dprint ("JSEAT target_contents', '''    probe = spawn (); probe.classname = "jump_seat_hull_probe";
    probe.solid = SOLID_SLIDEBOX; probe.movetype = MOVETYPE_STEP;
    probe.flags = FL_ONGROUND; setsize (probe, wr_bot.mins, wr_bot.maxs);
    setorigin (probe, wr_target); self = probe; fit = walkmove (0, 0);
    dprint ("JSEAT target_body_fit "); dprint (ftos (fit)); dprint ("\\n");
    remove (probe); self = wr_bot;
    dprint ("JSEAT target_contents''')
 wr.audit_fixture(text);p.write_text(text,encoding='utf-8',newline='\n')
 with (OUT/'compile.stderr').open('w') as err:
  l=lab(err,env())
  try:
   result=l.call('compile_qc',install=False);write(OUT/'compile.json',result)
   if not result['ok']:raise RuntimeError(result)
   print(json.dumps(dict(source_sha256=source_identity(OUT/'src'),fixture_sha256=digest(p),program_sha256=digest(OUT/'lq1/progs.dat'))))
  finally:finish_lab(l)
else:
 m=sys.argv[1];rate=float(sys.argv[2]);name=('jseat_diagnostic_' if DIAGNOSTIC else 'jseat_candidate_' if CANDIDATE else 'jseat_control_')+m+('_slow' if rate==.1 else '_played')
 if HULLPROBE:name='jseat_hull_'+m+('_slow' if rate==.1 else '_played')
 with private_game(ROOT,name,'jseat',autoexec='sv_protocol 15\nmax_edicts 600\nscratch2 1\n') as folder:
  shutil.copyfile(OUT/'lq1/progs.dat',folder/'progs.dat')
  with (OUT/(name+'.stderr')).open('w') as err:
   l=lab(err,env(folder,rate))
   try:
    run_match(l,m,24,name,port=26005,timeout=45,environment=env(folder,rate),stderr_path=OUT/(name+'.match.stderr'))
    raw,text=read_tape(OUT,name,m)
    brief=l.call('brief_run',log=str(raw),map=m,detail='full');write(OUT/(name+'.brief.json'),brief)
    markers=[s for s in text.splitlines() if s.startswith('WRFIX')]
    write(OUT/(name+'.receipt.json'),dict(map=m,ticrate=rate,raw=str(raw.relative_to(ROOT)),raw_sha256=digest(raw),source_sha256=source_identity(OUT/'src'),fixture_sha256=digest(OUT/'src/water_route_fixture.qc'),program_sha256=digest(OUT/'lq1/progs.dat'),markers=markers))
    print('\n'.join(markers),flush=True)
   finally:finish_lab(l)
