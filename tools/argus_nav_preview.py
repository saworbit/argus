"""Publish optional navigation previews with graph-associated freshness receipts."""
import hashlib
import json
from pathlib import Path
import tempfile


def file_md5(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def generate_preview(qc, png, render):
    """Keep graph generation successful when plotting is unavailable or fails."""
    qc, png = Path(qc), Path(png)
    receipt = Path(str(png) + '.json')
    state = dict(schema='nav-preview-v1', generated=False, qc_md5=file_md5(qc),
                 graph_md5=file_md5(Path(str(qc) + '.json')))
    # Invalidate the old preview before importing or invoking the plotter.
    receipt.write_text(json.dumps(state) + '\n', encoding='utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=png.parent, suffix='.png', delete=False) as owned:
            temporary = Path(owned.name)
        render(temporary)
        if not temporary.stat().st_size:
            raise ValueError('plotter produced an empty preview')
        temporary.replace(png)
        state.update(generated=True, png_md5=file_md5(png))
        receipt.write_text(json.dumps(state) + '\n', encoding='utf-8')
        print('wrote', png)
    except Exception as error:
        state['generated'] = False
        print(f'debug plot skipped: {type(error).__name__}: {error} '
              '(nav QC and json are written and valid)')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return state['generated']
