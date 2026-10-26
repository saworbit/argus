"""Stage only the workspace lab binary; run a frozen cohort; restore on exit."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sys
import traceback

from run_behaviour_equivalence import ROOT, main as run


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('protocol', type=Path)
    args = ap.parse_args()
    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    output = ROOT / protocol['output']
    output.mkdir(parents=True, exist_ok=True)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    lab_binary = ROOT / 'engine/argus/progs.dat'
    candidate = ROOT / protocol['candidate']
    assert digest(candidate) == protocol['identities']['dm2']['binary_sha256']
    assert digest(lab_binary) == protocol['shipped_sha256'], 'unexpected lab binary; preserve and investigate'
    restored = output / 'restore-progs.dat'
    if restored.exists():
        assert digest(restored) == digest(lab_binary), 'restore snapshot differs'
    else:
        shutil.copy2(lab_binary, restored)
    state = dict(protocol_sha256=digest(protocol_path),
                 started_utc=dt.datetime.now(dt.timezone.utc).isoformat(), status='running')
    state_path = output / 'execution.json'
    state_path.write_text(json.dumps(state, indent=2))
    try:
        shutil.copy2(candidate, lab_binary)
        sys.argv = [sys.argv[0], '--cohort', 'confirm', '--maps', ','.join(protocol['maps']),
                    '--repeats', ','.join(map(str, range(1, protocol['pairs_per_map'] + 1))),
                    '--seconds', str(protocol['seconds']), '--prefix', protocol['prefix'],
                    '--output', str(output), '--protocol', str(protocol_path)]
        run()
        state['status'] = 'complete'
    except BaseException:
        state['status'] = 'interrupted'
        state['error'] = traceback.format_exc()
        raise
    finally:
        shutil.copy2(restored, lab_binary)
        state['restored_sha256'] = digest(lab_binary)
        assert state['restored_sha256'] == protocol['shipped_sha256']
        state['stopped_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        state_path.write_text(json.dumps(state, indent=2))


if __name__ == '__main__':
    main()
