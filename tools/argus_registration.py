"""Build registration uses the same two entries as nav_sync.rs."""
import re

COMMENTS = re.compile(r'"(?:\\.|[^"\\])*"|(/\*.*?\*/|//[^\r\n]*)', re.S)


def registration(dispatch, progs, mapname):
    """Return (dispatcher branch, exact progs entry), ignoring comments."""
    def strip(text):
        return COMMENTS.sub(lambda match: ' ' if match.group(1) else match[0], text)
    dispatch = strip(dispatch)
    progs = strip(progs)
    return (
        f'mapname == "{mapname}"' in dispatch,
        f"argus_nav_{mapname}.qc" in {line.strip() for line in progs.splitlines()},
    )
