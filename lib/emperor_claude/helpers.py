# -*- coding: utf-8 -*-
"""Emperor Claude Connector - helper library preloaded into every script.

Everything public here is injected into the script namespace (also reachable as H.<name>),
so scripts no longer re-declare unit conversion, name lookup, link transforms, connector
walking, sub-transactions and so on.  Units: the Revit API is in feet, the helpers talk
meters (M = feet to meters, F = meters to feet).
IronPython 2.7 and CPython 3 compatible (no f-strings).
"""
import math
import collections

import System
from pyrevit import DB

try:
    from emperor_claude import jobs as _jobs
    Cancelled = _jobs.Cancelled
except ImportError:                     # used outside the extension (tests)
    _jobs = None

    class Cancelled(Exception):
        pass

FT = 1.0 / 0.3048
_state = {"job": None}


def bind(job):
    """Called by the script runner: lets progress() / checkpoint() talk to the running job."""
    _state["job"] = job


# ------------------------------------------------------------------ units, names, ids
def M(v):
    """feet -> meters"""
    return v / FT


def F(v):
    """meters -> feet"""
    return v * FT


def nm(e):
    """Name of any element (works for types in IronPython)."""
    return DB.Element.Name.GetValue(e)


def eid(n):
    try:
        return DB.ElementId(n)
    except Exception:
        return DB.ElementId(System.Int64(n))


def eint(i):
    try:
        return int(i.Value)
    except AttributeError:
        return int(i.IntegerValue)


def one(doc, cls, name):
    """The single element of a class with an exact name (error if 0 or several)."""
    found = [x for x in DB.FilteredElementCollector(doc).OfClass(cls) if nm(x) == name]
    if len(found) != 1:
        raise Exception("%s '%s': found %d, expected 1" % (cls.__name__, name, len(found)))
    return found[0]


def levels(doc):
    """{level name: Level}"""
    return dict((nm(l), l) for l in DB.FilteredElementCollector(doc).OfClass(DB.Level))


def cat_elements(doc, bic, types=False):
    col = DB.FilteredElementCollector(doc).OfCategory(bic)
    return col.WhereElementIsElementType() if types else col.WhereElementIsNotElementType()


def family_name(e):
    try:
        return e.Symbol.FamilyName
    except Exception:
        return None


def pstr(e, bip):
    """Parameter as text (None if missing)."""
    p = e.get_Parameter(bip)
    if p is None:
        return None
    s = p.AsString()
    return s if s is not None else p.AsValueString()


# ------------------------------------------------------------------ links
def link(doc, key):
    """(link document, transform to host) of the first loaded link whose name contains key, e.g. '_AR_'."""
    for li in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance):
        if li.GetLinkDocument() is not None and key.lower() in li.Name.lower():
            return li.GetLinkDocument(), li.GetTotalTransform()
    raise Exception("no loaded link containing '%s'" % key)


def rname(r):
    return r.get_Parameter(DB.BuiltInParameter.ROOM_NAME).AsString() or ""


def link_rooms(link_doc, level_name=None):
    """Placed rooms (area > 0) of a link, optionally for one level, sorted by id."""
    out = []
    for r in DB.FilteredElementCollector(link_doc).OfCategory(DB.BuiltInCategory.OST_Rooms).WhereElementIsNotElementType():
        if r.Area <= 0 or r.Level is None:
            continue
        if level_name and r.Level.Name != level_name:
            continue
        out.append(r)
    out.sort(key=lambda r: eint(r.Id))
    return out


def host_bbox(e, tr=None):
    """(x0, x1, y0, y1, z0, z1) in host meters (applies the link transform if given)."""
    bb = e.get_BoundingBox(None)
    if bb is None:
        return None
    pts = [(x, y, z) for x in (bb.Min.X, bb.Max.X) for y in (bb.Min.Y, bb.Max.Y) for z in (bb.Min.Z, bb.Max.Z)]
    if tr is not None:
        pts = [(p.X, p.Y, p.Z) for p in [tr.OfPoint(DB.XYZ(*q)) for q in pts]]
    return (M(min(p[0] for p in pts)), M(max(p[0] for p in pts)), M(min(p[1] for p in pts)),
            M(max(p[1] for p in pts)), M(min(p[2] for p in pts)), M(max(p[2] for p in pts)))


def wall_faces_index(link_doc, tr):
    """Straight walls of a link as ([vertical (x, y0, y1, width)], [horizontal (y, x0, x1, width)]) in host meters."""
    vw, hw = [], []
    for w in DB.FilteredElementCollector(link_doc).OfClass(DB.Wall):
        lc = w.Location
        if not isinstance(lc, DB.LocationCurve):
            continue
        a, b = tr.OfPoint(lc.Curve.GetEndPoint(0)), tr.OfPoint(lc.Curve.GetEndPoint(1))
        ax, ay, bx, by, wd = M(a.X), M(a.Y), M(b.X), M(b.Y), M(w.Width)
        if abs(ax - bx) < 0.01:
            vw.append((ax, min(ay, by), max(ay, by), wd))
        elif abs(ay - by) < 0.01:
            hw.append((ay, min(ax, bx), max(ax, bx), wd))
    return vw, hw


def wall_distance(hw, x0, x1, y_face, direction):
    """Distance (m) from a y-face to the nearest horizontal wall in +y (direction=1) or -y (-1); None if none."""
    best = None
    for y, xa, xb, wd in hw:
        if xb < x0 + 0.02 or xa > x1 - 0.02:
            continue
        if direction > 0 and y - wd / 2 >= y_face - 0.02:
            d = (y - wd / 2) - y_face
        elif direction < 0 and y + wd / 2 <= y_face + 0.02:
            d = y_face - (y + wd / 2)
        else:
            continue
        if best is None or d < best:
            best = d
    return best


def ceiling_boxes(link_doc, tr):
    """[(x0, x1, y0, y1, z)] bounding boxes of ceilings of a link (z = underside), host meters."""
    out = []
    for c in DB.FilteredElementCollector(link_doc).OfCategory(DB.BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType():
        b = host_bbox(c, tr)
        if b is not None:
            out.append((b[0], b[1], b[2], b[3], b[4]))
    return out


def ceiling_z(boxes, x, y, floor_z, typical, lo=2.4, hi=4.3):
    """Highest ceiling underside above (x, y) between floor_z+lo and floor_z+hi, else `typical`."""
    best = None
    for x0, x1, y0, y1, z in boxes:
        if x0 - 0.2 <= x <= x1 + 0.2 and y0 - 0.2 <= y <= y1 + 0.2 and floor_z + lo <= z <= floor_z + hi:
            best = z if best is None else max(best, z)
    return best if best is not None else typical


# ------------------------------------------------------------------ MEP connectors and pipes
def cmgr(o):
    return o.ConnectorManager if isinstance(o, DB.MEPCurve) else o.MEPModel.ConnectorManager


def phys(c):
    """Connectors physically joined to connector c (no MEP system references)."""
    return [r for r in c.AllRefs if not isinstance(r.Owner, DB.MEPSystem) and r.Owner.Id != c.Owner.Id]


def nearest_conn(o, pt):
    return min(cmgr(o).Connectors, key=lambda c: c.Origin.DistanceTo(pt))


def pipe_chain(start_conn, owner_ids_seen=None, limit=14, names=("Pipes", "Pipe Fittings")):
    """Owners reached from a connector, following physical connections (breadth first)."""
    seen = set(owner_ids_seen or [])
    seen.add(eint(start_conn.Owner.Id))
    out, queue = [], [start_conn]
    while queue and len(out) < limit:
        c = queue.pop(0)
        for r in phys(c):
            o = r.Owner
            if eint(o.Id) in seen or not o.Category or o.Category.Name not in names:
                continue
            seen.add(eint(o.Id))
            out.append(o)
            for oc in cmgr(o).Connectors:
                queue.append(oc)
    return out


def free_ends(doc):
    """(pipe curves, pipe fittings) free connector counts in the whole model."""
    a = sum(1 for e in cat_elements(doc, DB.BuiltInCategory.OST_PipeCurves) for c in e.ConnectorManager.Connectors if not c.IsConnected)
    b = sum(1 for e in cat_elements(doc, DB.BuiltInCategory.OST_PipeFitting) for c in e.MEPModel.ConnectorManager.Connectors if not c.IsConnected)
    return a, b


def seg_distance(p1, p2, q1, q2, n=20):
    """Approximate minimum distance between two 3D segments (points are (x, y, z) tuples)."""
    best = 9e9
    for i in range(n + 1):
        a = [p1[k] + (p2[k] - p1[k]) * i / float(n) for k in range(3)]
        for j in range(n + 1):
            b = [q1[k] + (q2[k] - q1[k]) * j / float(n) for k in range(3)]
            best = min(best, math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3))))
    return best


def clashes(doc, x0, x1, y0, y1, z0, z1, cats=None, ignore=()):
    """Ids (int) of MEP elements whose bounding box meets the box (host meters)."""
    cats = cats or (DB.BuiltInCategory.OST_DuctCurves, DB.BuiltInCategory.OST_DuctFitting,
                    DB.BuiltInCategory.OST_DuctAccessory, DB.BuiltInCategory.OST_PipeCurves,
                    DB.BuiltInCategory.OST_PipeFitting, DB.BuiltInCategory.OST_MechanicalEquipment,
                    DB.BuiltInCategory.OST_FlexDuctCurves)
    flt = DB.BoundingBoxIntersectsFilter(DB.Outline(DB.XYZ(F(x0), F(y0), F(z0)), DB.XYZ(F(x1), F(y1), F(z1))))
    ignore = set(ignore)
    hits = []
    for cat in cats:
        for e in DB.FilteredElementCollector(doc).OfCategory(cat).WherePasses(flt).WhereElementIsNotElementType():
            if eint(e.Id) not in ignore:
                hits.append(eint(e.Id))
    return hits


class Grid(object):
    """Tiny spatial index of occupied 2D boxes, for collision-free placement of tags and labels."""

    def __init__(self, cell=8.0):
        self.cell = cell
        self.cells = collections.defaultdict(list)

    def _range(self, x0, x1, y0, y1):
        c = self.cell
        return range(int(math.floor(x0 / c)), int(math.floor(x1 / c)) + 1), range(int(math.floor(y0 / c)), int(math.floor(y1 / c)) + 1)

    def add(self, x0, x1, y0, y1):
        xs, ys = self._range(x0, x1, y0, y1)
        for i in xs:
            for j in ys:
                self.cells[(i, j)].append((x0, x1, y0, y1))

    def hit(self, x0, x1, y0, y1):
        xs, ys = self._range(x0, x1, y0, y1)
        for i in xs:
            for j in ys:
                for b in self.cells.get((i, j), ()):
                    if x0 < b[1] and x1 > b[0] and y0 < b[3] and y1 > b[2]:
                        return True
        return False


# ------------------------------------------------------------------ transactions, jobs
class Attempt(object):
    """with Attempt(doc) as a:  ...   - a SubTransaction that rolls back by itself if the block fails.

    After the block: a.ok (True/False) and a.error (text). Only a cancel request is re-raised.
    Must be used inside the script's own transaction (the default).
    """

    def __init__(self, doc):
        self.doc = doc
        self.ok = False
        self.error = None
        self.sub = None

    def __enter__(self):
        self.sub = DB.SubTransaction(self.doc)
        self.sub.Start()
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            self.sub.Commit()
            self.ok = True
            return False
        try:
            self.sub.RollBack()
        except Exception:
            pass
        if issubclass(et, Cancelled):
            return False
        self.error = ("%s" % ev)[:160]
        return True


def unpin_and_delete(doc, elements):
    """Unpin, then delete. Returns how many were deleted."""
    elements = list(elements)
    ids = []
    for e in elements:
        try:
            if e.Pinned:
                e.Pinned = False
        except Exception:
            pass
        ids.append(e.Id)
    for i in ids:
        doc.Delete(i)
    return len(ids)


def progress(message, done=None, total=None):
    """Report progress of the running job (visible with job_status)."""
    if _jobs is not None:
        _jobs.progress(_state["job"], message, done, total)


def checkpoint():
    """Call inside long loops so the job can be cancelled between steps."""
    if _jobs is not None:
        _jobs.checkpoint(_state["job"])


def counter():
    return collections.Counter()


_EXPORTS = ["FT", "M", "F", "nm", "eid", "eint", "one", "levels", "cat_elements", "family_name", "pstr",
            "link", "rname", "link_rooms", "host_bbox", "wall_faces_index", "wall_distance",
            "ceiling_boxes", "ceiling_z", "cmgr", "phys", "nearest_conn", "pipe_chain", "free_ends",
            "seg_distance", "clashes", "Grid", "Attempt", "unpin_and_delete", "progress", "checkpoint",
            "counter", "Cancelled", "math", "collections", "System"]


def export(ns):
    """Put the helper names straight into a script namespace."""
    g = globals()
    for name in _EXPORTS:
        ns[name] = g[name]
    return ns
