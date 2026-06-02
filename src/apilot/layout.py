"""apilot.layout — a small convenience layer for programmatic layout editing.

It turns common layout operations (place instances, draw metal rectangles and
paths, drop vias, add labels) into Python calls that generate SKILL and run it
through a SkillClient. It is NOT an auto-router: it draws exactly the geometry
you specify; DRC/LVS then verify it.

Calls are accumulated and sent in ONE batch via the client's file-load path
(`run_il_text`), which is both efficient (a single round trip) and robust for
large, multi-line SKILL. Coordinates are in microns (layout user units).

Example
-------
    from apilot import SkillClient, LayoutEditor

    c = SkillClient.from_env()
    with LayoutEditor(c, "MyLib", "my_cell") as ed:   # commits on exit
        ed.clear()
        # placement (CSMC: pass fw too, in SI meters)
        ed.place("st02", "mn", "M1", 0, 0,
                 params={"w": 5e-6, "fw": 5e-6, "l": 1e-6, "fingers": 1})
        # routing
        ed.rect("A1", 20, 0, 25, 1)
        ed.rect("A2", 22, 0, 23, 6)
        # via (standard via def from the techfile, e.g. M1_M2 = A1<->A2)
        ed.via("M1_M2", 22.5, 0.5)
        # label (for LVS port naming; *_text layers, e.g. A1_text)
        ed.label("A1_text", "VOUT", 22.5, 0.5)
    print(ed.last_summary)   # {'shapes': 4, 'vias': 1, 'instances': 1}
"""
from __future__ import annotations

from .skill import SkillClient


def _num(v) -> str:
    """Format a Python number as a SKILL-friendly literal."""
    if isinstance(v, bool):
        return "t" if v else "nil"
    if isinstance(v, int):
        return str(v)
    return repr(float(v))


def _layer(layer, purpose: str = "drawing") -> str:
    """A SKILL layer-purpose pair: 'A1' -> list("A1" "drawing")."""
    if isinstance(layer, (tuple, list)):
        layer, purpose = layer[0], (layer[1] if len(layer) > 1 else purpose)
    return 'list("%s" "%s")' % (layer, purpose)


def _params_to_skill(params) -> str:
    """Build the SKILL paramList for dbCreateParamInstByMasterName.

    Accepts a dict (types inferred: str->string, int->int, float->float) or a
    list of explicit (name, type, value) tuples.
    """
    items = []
    seq = params.items() if isinstance(params, dict) else (params or [])
    for entry in seq:
        if isinstance(entry, (tuple, list)) and len(entry) == 3:
            name, typ, val = entry
        else:
            name, val = entry
            # NB: check bool before int (bool is a subclass of int in Python).
            if isinstance(val, str):
                typ = "string"
            elif isinstance(val, bool):
                typ = "boolean"
            elif isinstance(val, int):
                typ = "int"
            else:
                typ = "float"
        if typ == "string":
            sval = '"%s"' % val
        elif typ == "boolean":
            truthy = val.lower() in ("t", "true", "yes", "1") if isinstance(val, str) else bool(val)
            sval = "t" if truthy else "nil"
        else:  # int / float
            sval = _num(val)
        items.append('list("%s" "%s" %s)' % (name, typ, sval))
    return "list(%s)" % " ".join(items) if items else "nil"


class LayoutEditor:
    """Accumulate layout ops and commit them to a layout cellview in one batch."""

    def __init__(self, client: SkillClient, lib: str, cell: str, view: str = "layout"):
        self.client = client
        self.lib, self.cell, self.view = lib, cell, view
        self._ops: list[str] = []
        self._clear = False
        self.last_summary: dict | None = None

    # -- ops (chainable) --------------------------------------------------
    def clear(self) -> "LayoutEditor":
        """Delete existing shapes + instances before adding new ones."""
        self._clear = True
        return self

    def place(self, lib: str, cell: str, inst_name: str, x: float, y: float,
              orient: str = "R0", params=None, view: str = "layout") -> "LayoutEditor":
        """Place a (PCell) instance. params: dict or [(name,type,value), ...].

        For CSMC MOS remember to pass `fw` too (in SI meters), e.g.
        params={"w": 92e-6, "fw": 92e-6, "l": 1e-6, "fingers": 1}.
        """
        self._ops.append(
            'dbCreateParamInstByMasterName(cv "%s" "%s" "%s" "%s" %s:%s "%s" 1 %s)'
            % (lib, cell, view, inst_name, _num(x), _num(y), orient, _params_to_skill(params)))
        return self

    def rect(self, layer, x0: float, y0: float, x1: float, y1: float,
             purpose: str = "drawing") -> "LayoutEditor":
        """Draw a rectangle (a metal wire segment, fill, etc.)."""
        self._ops.append(
            'dbCreateRect(cv %s list(%s:%s %s:%s))'
            % (_layer(layer, purpose), _num(x0), _num(y0), _num(x1), _num(y1)))
        return self

    def path(self, layer, points, width: float, purpose: str = "drawing") -> "LayoutEditor":
        """Draw a path/wire of the given width through points [(x,y), ...]."""
        pts = " ".join("%s:%s" % (_num(p[0]), _num(p[1])) for p in points)
        self._ops.append(
            'dbCreatePath(cv %s list(%s) %s)'
            % (_layer(layer, purpose), pts, _num(width)))
        return self

    def via(self, via_def: str, x: float, y: float, orient: str = "R0") -> "LayoutEditor":
        """Drop a standard via from the techfile (e.g. M1_M2, M2_T3, NDIFF_M1)."""
        self._ops.append(
            'dbCreateVia(cv techFindViaDefByName(techGetTechFile(cv) "%s") %s:%s "%s")'
            % (via_def, _num(x), _num(y), orient))
        return self

    def label(self, layer, text: str, x: float, y: float, height: float = 0.1,
              justify: str = "centerCenter", orient: str = "R0", purpose: str = "drawing") -> "LayoutEditor":
        """Add a text label (e.g. on an *_text layer to name a net for LVS)."""
        self._ops.append(
            'dbCreateLabel(cv %s %s:%s "%s" "%s" "%s" "roman" %s)'
            % (_layer(layer, purpose), _num(x), _num(y),
               text.replace('"', '\\"'), justify, orient, _num(height)))
        return self

    def skill(self, raw: str) -> "LayoutEditor":
        """Append a raw SKILL statement operating on `cv` (escape hatch)."""
        self._ops.append(raw)
        return self

    # -- commit -----------------------------------------------------------
    def build_script(self, create: bool = True) -> str:
        mode = "w" if create else "a"
        body = ["let((cv)",
                '  cv = dbOpenCellViewByType("%s" "%s" "%s" "maskLayout" "%s")'
                % (self.lib, self.cell, self.view, mode)]
        if self._clear:
            body.append("  foreach(s cv~>shapes dbDeleteObject(s))")
            body.append("  foreach(i cv~>instances dbDeleteObject(i))")
        body += ["  " + op for op in self._ops]
        body.append("  dbSave(cv))")
        return "\n".join(body) + "\n"

    def commit(self, create: bool = True) -> dict:
        """Send all accumulated ops, save, and return a summary dict."""
        r = self.client.run_il_text(self.build_script(create=create))
        if not r.ok:
            self.last_summary = {"ok": False, "error": r.output}
            return self.last_summary
        q = self.client.execute(
            'let((cv) cv=dbOpenCellViewByType("%s" "%s" "%s") '
            'sprintf(nil "%%d %%d %%d" length(cv~>shapes) length(cv~>vias) length(cv~>instances)))'
            % (self.lib, self.cell, self.view))
        try:
            sh, vi, ins = (int(x) for x in q.output.strip().strip('"').split())
            self.last_summary = {"ok": True, "shapes": sh, "vias": vi, "instances": ins}
        except Exception:
            self.last_summary = {"ok": True, "raw": q.output}
        return self.last_summary

    def __enter__(self) -> "LayoutEditor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.commit()
        return False
