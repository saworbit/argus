"""Fatal engine records shared with the native tape and benchmark readers."""

import json
from pathlib import Path

_CONTRACT = Path(__file__).resolve().parent / 'argus_mcp/src/fatal_engine_prefixes.json'
_PREFIXES = tuple(json.loads(_CONTRACT.read_text(encoding='ascii')))
# The Unicode White_Space characters used by Rust's str::trim.
_WHITESPACE = (' \t\n\r\v\f\x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004'
               '\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000')


def fatal_engine_line(text):
    """Return the first fatal console line, if any."""
    for line in text.split('\n'):
        line = line.strip(_WHITESPACE)
        if line.startswith(_PREFIXES):
            return line
    return None
