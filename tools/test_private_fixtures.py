"""Bounded private-runner failure, ownership and current/control contracts."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import verify_private_fixtures as runner
from check_muzzle_fixture import LABELS


def muzzle_tape(failures=()):
    return ('BHVRPL begin muzzle_fixture\nMFIX begin dm4 dt_ms 14\n'+
        ''.join(f'MFIX check {label} {int(label not in failures)}\n' for label in LABELS)+
        f'MFIX end checks 14 ok {int(not failures)}\n')


class PrivateTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.base=self.root/'engine'
        for folder in ('backups','src','game/argus','engine/argus','engine/id1','lq1','tools/fixtures'):
            (self.root/folder).mkdir(parents=True,exist_ok=True)
        (self.root/'src/progs.src').write_text('defs.qc\nargus.qc\nworld.qc\n')
        (self.root/'src/argus.qc').write_text('if (!self.ar_tactic && self.weapon != IT_ROCKET_LAUNCHER)\nif (targetdist < reach) reach = targetdist;\n')
        (self.root/'src/world.qc').write_text('Argus_CountSlots ();\nArgus_FrameAll ();\n')
        (self.root/'tools/fixtures/muzzle_clearance.qc').write_text('// retained fixture\n')
        (self.base/'id1/pak0.pak').write_bytes(b'private assets')
        self.exe=self.root/'lab.exe';self.exe.write_bytes(b'lab')
        for p in ('game/argus/progs.dat','engine/argus/progs.dat','lq1/progs.dat'):
            (self.root/p).write_bytes(b'original '+p.encode())
        self.patches=[patch.object(runner,'EXE',self.exe),patch.object(runner,'audit_muzzle'),
                      patch.object(runner,'audit_health')]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.output=self.root/'backups/fresh'
        self.calls=[];self.closed=[];self.failure=None
        self.before=runner.tree_identity(self.root/'src')
        self.binaries=runner.identities([self.root/p for p in ('game/argus/progs.dat','engine/argus/progs.dat','lq1/progs.dat')])

    def factory(self,err,env):
        outer=self
        class FakeLab:
            def call(self,name,**args):
                outer.calls.append((name,args))
                if name=='see':return {'lab_identity':{'authoritative':outer.failure!='stale'}}
                if name=='config_check':
                    values={'ARGUS_BASEDIR':str(outer.base),'ARGUS_GAME':'argus','ARGUS_PROGS':str(outer.root/'lq1/progs.dat')}
                    return dict(complete=True,entries=[dict(key=k,value=v) for k,v in values.items()])
                if name=='match_status':return dict(running=False)
                if name=='compile_qc':
                    if outer.failure=='compile':return dict(ok=False,installed_to=[],new_errors=1,new_warnings=0)
                    Path(env['ARGUS_PROGS']).write_bytes(b'candidate')
                    return dict(ok=True,installed_to=[],new_errors=0,new_warnings=0)
                if name=='experiment':
                    if outer.failure=='engine':raise RuntimeError('engine failed')
                    variant=Path(env['ARGUS_SRC']).parent.name
                    expected={'legacy':['ordinary_wall','ordinary_overhang'],'uncapped':['wall_behind_target']}.get(variant,[])
                    if outer.failure=='control':expected=[]
                    (Path(env['ARGUS_RUNS'])/(args['run_name']+'.log')).write_text(muzzle_tape(expected))
                    return dict(ok=True)
                raise AssertionError(name)
            def close(self):outer.closed.append(env)
        return FakeLab()

    def run_fixture(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.run('muzzle',self.output,'fresh',root=self.root,lab_factory=self.factory)

    def assert_preserved(self):
        self.assertEqual(runner.tree_identity(self.root/'src'),self.before)
        self.assertEqual(runner.identities([Path(p) for p in self.binaries]),self.binaries)
        self.assertTrue(json.loads((self.output/'after.json').read_text())['unchanged'])
        self.assertFalse((self.root/'backups/.private-fixture.lock').exists())

    def test_success_keeps_current_sources_binaries_and_control_receipts(self):
        rows=self.run_fixture()
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[2]['failures'],['ordinary_wall','ordinary_overhang'])
        self.assertEqual(rows[3]['failures'],['wall_behind_target'])
        self.assertTrue(all(a=={'install':False} for n,a in self.calls if n=='compile_qc'))
        self.assertEqual(len(self.closed),5)
        self.assertTrue((self.output/'production-src/argus.qc').exists())
        self.assertEqual(len(list((self.output/'saved-binaries').rglob('progs.dat'))),5)
        self.assert_preserved()

    def test_output_collision_and_invalid_prefix_do_not_start_the_lab(self):
        self.output.mkdir()
        with self.assertRaises(ValueError):self.run_fixture()
        with self.assertRaises(ValueError):runner.preflight(self.root,self.output.parent/'new','../bad')
        self.assertEqual(self.calls,[])

    def test_missing_assets_and_pending_human_tape_fail_before_compile(self):
        for mode in ('assets','human'):
            with self.subTest(mode=mode):
                self.output=self.root/'backups'/mode
                if mode=='assets':(self.base/'id1/pak0.pak').unlink()
                else:
                    (self.base/'id1/pak0.pak').write_bytes(b'assets')
                    (self.base/'qconsole.log').write_text('unharvested')
                with self.assertRaises(ValueError):self.run_fixture()
                self.assertFalse(any(n=='compile_qc' for n,_ in self.calls))
                self.assert_preserved()

    def test_compile_engine_and_control_failure_keep_receipts_and_cleanup(self):
        for failure in ('compile','engine','control','stale'):
            with self.subTest(failure=failure):
                self.failure=failure;self.output=self.root/'backups'/failure
                with self.assertRaises((RuntimeError,ValueError)):self.run_fixture()
                self.assert_preserved()
                if failure in ('engine','control'):
                    row=json.loads((self.output/'results.json').read_text())[-1]
                    self.assertFalse(row['accepted'])
                    self.assertIn('rejection',row)

    def test_an_existing_lock_is_never_deleted(self):
        lock=self.root/'backups/.private-fixture.lock';lock.write_text('other owner')
        with self.assertRaises(FileExistsError):self.run_fixture()
        self.assertEqual(lock.read_text(),'other owner')
        self.assertEqual(self.calls,[])

    def test_changed_protected_input_is_reported_without_overwriting_it(self):
        factory=self.factory
        def changed_input(err,env):
            lab=factory(err,env)
            if 'ARGUS_SRC' in env:
                (self.root/'engine/argus/progs.dat').write_bytes(b'external edit')
            return lab
        self.failure='compile'
        with self.assertRaisesRegex(RuntimeError,'protected production inputs changed'):
            runner.run('muzzle',self.output,'fresh',root=self.root,lab_factory=changed_input)
        self.assertEqual((self.root/'engine/argus/progs.dat').read_bytes(),b'external edit')
        self.assertFalse(json.loads((self.output/'after.json').read_text())['unchanged'])
        self.assertFalse((self.root/'backups/.private-fixture.lock').exists())

    def test_health_client_failure_always_stops_its_owned_engine(self):
        calls=[]
        class Lab:
            def call(self,name,**args):
                calls.append(name)
                return dict(running=True,tail=['ARGLOG ready'])
        def failed_client(*args,**kwargs):return SimpleNamespace(returncode=1,stderr='failed client')
        with self.assertRaisesRegex(RuntimeError,'failed client'):
            runner.health_trial(Lab(),'fixture','dm2',{},failed_client)
        self.assertEqual(calls[-1],'match_stop')
        calls.clear()
        class BrokenLab:
            def call(self,name,**args):
                calls.append(name)
                if name=='match_start':raise RuntimeError('start failed')
        with self.assertRaises(RuntimeError):runner.health_trial(BrokenLab(),'fixture','dm2',{},failed_client)
        self.assertEqual(calls,['match_start','match_stop'])

    def test_help_is_side_effect_free(self):
        before=set(self.root.iterdir())
        script=Path(runner.__file__).resolve()
        result=subprocess.run([sys.executable,str(script),'--help'],cwd=self.root,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('--output',result.stdout)
        self.assertEqual(set(self.root.iterdir()),before)

    def test_button_player_failure_stops_engine_and_keeps_client_receipt(self):
        calls=[];folder=self.root/'player-test';folder.mkdir()
        class Lab:
            def call(self,name,**args):
                calls.append(name)
                return dict(running=True,tail=['ARGLOG ready'])
        def failed_client(*args,**kwargs):
            return SimpleNamespace(returncode=1,stdout='',stderr='control failed')
        with self.assertRaisesRegex(RuntimeError,'control failed'):
            runner.button_player_trial(Lab(),'test',{},failed_client,folder)
        self.assertEqual(calls[-1],'match_stop')
        self.assertEqual(json.loads((folder/'test.client.json').read_text())['returncode'],1)


if __name__=='__main__':unittest.main()
