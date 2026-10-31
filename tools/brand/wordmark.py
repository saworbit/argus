# Argus wordmark - the facet rule, applied programmatically.
#
# Quake has no curves. Every surface in a BSP and every face on an MDL is a
# flat polygon; roundness is faked by using more facets. So the wordmark takes
# IBM Plex Mono Bold - the console voice, because this whole tool is driven
# from the Quake console - and flattens every curve in it to N straight
# segments. Not a filter over the top: the letterforms genuinely have no
# curves left in them, which is the same rule the mark is drawn with.
import os
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "node_modules/@ibm/plex/IBM-Plex-Mono/fonts/"
                          "complete/woff/IBMPlexMono-Bold.woff")

_f = TTFont(FONT)
_upm = _f["head"].unitsPerEm
_cap = _f["OS/2"].sCapHeight
_cmap, _gs, _hmtx = _f.getBestCmap(), _f.getGlyphSet(), _f["hmtx"]


class FacetPen(BasePen):
    """Flattens every curve to `n` straight segments. n=1 is maximum facet."""

    def __init__(self, glyphSet, n=2, scale=1.0, dx=0.0, dy=0.0):
        super().__init__(glyphSet)
        self.n, self.k, self.dx, self.dy = max(1, int(n)), scale, dx, dy
        self.parts = []

    def _pt(self, p):
        return (p[0] * self.k + self.dx, -p[1] * self.k + self.dy)

    def _moveTo(self, p):
        x, y = self._pt(p)
        self.parts.append(f"M{x:.2f} {y:.2f}")

    def _lineTo(self, p):
        x, y = self._pt(p)
        self.parts.append(f"L{x:.2f} {y:.2f}")

    def _closePath(self):
        self.parts.append("Z")

    _endPath = _closePath

    def _curveToOne(self, b1, b2, p):
        a = self._getCurrentPoint()
        for i in range(1, self.n + 1):
            t = i / self.n
            u = 1 - t
            x = (u ** 3 * a[0] + 3 * u * u * t * b1[0]
                 + 3 * u * t * t * b2[0] + t ** 3 * p[0])
            y = (u ** 3 * a[1] + 3 * u * u * t * b1[1]
                 + 3 * u * t * t * b2[1] + t ** 3 * p[1])
            self._lineTo((x, y))

    def _qCurveToOne(self, b, p):
        a = self._getCurrentPoint()
        for i in range(1, self.n + 1):
            t = i / self.n
            u = 1 - t
            x = u * u * a[0] + 2 * u * t * b[0] + t * t * p[0]
            y = u * u * a[1] + 2 * u * t * b[1] + t * t * p[1]
            self._lineTo((x, y))
