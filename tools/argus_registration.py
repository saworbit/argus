"""Build registration uses the same two entries as nav_sync.rs."""
import re

COMMENTS = re.compile(r"/\*.*?\*/|//[^\r\n]*", re.S)


def registration(dispatch, progs, mapname):
    dispatch = COMMENTS.sub(" ", dispatch)
    progs = COMMENTS.sub(" ", progs)
    return (
        f'mapname == "{mapname}"' in dispatch,
        f"argus_nav_{mapname}.qc" in {line.strip() for line in progs.splitlines()},
    )
