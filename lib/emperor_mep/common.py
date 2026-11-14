# -*- coding: ascii -*-
"""Small helpers shared by the Emperor MEP tools. IronPython 2.7 and CPython 3 compatible."""
import os
import json
import re

from Autodesk.Revit import DB

FT_PER_MM = 1.0 / 304.8


def eid_int(eid):
    try:
        return int(eid.Value)          # Revit 2024+
    except AttributeError:
        return int(eid.IntegerValue)


def make_eid(n):
    try:
        return DB.ElementId(int(n))
    except Exception:
        import System
        return DB.ElementId(System.Int64(int(n)))


def is_invalid(eid):
    return eid is None or eid_int(eid) == -1


def name_of(e):
    if e is None:
        return u''
    try:
        return DB.Element.Name.GetValue(e)
    except Exception:
        pass
    try:
        return e.Name
    except Exception:
        return u''


def type_label(sym):
    try:
        return u'%s : %s' % (sym.FamilyName, name_of(sym))
    except Exception:
        return name_of(sym)


def mm_to_ft(v):
    return float(v) * FT_PER_MM


def ft_to_mm(v):
    return float(v) * 304.8


def bip_element_name(doc, e, bip):
    """Name of the element an ElementId parameter points to (e.g. the system type)."""
    try:
        p = e.get_Parameter(bip)
        if p is None or not p.HasValue:
            return u''
        t = doc.GetElement(p.AsElementId())
        return name_of(t) if t is not None else u''
    except Exception:
        return u''


def connectors_of(e):
    try:
        if isinstance(e, DB.MEPCurve):
            return list(e.ConnectorManager.Connectors)
    except Exception:
        pass
    try:
        mm = e.MEPModel
        if mm is not None and mm.ConnectorManager is not None:
            return list(mm.ConnectorManager.Connectors)
    except Exception:
        pass
    return []


def size_mm(e):
    """Nominal size of a duct / pipe / fitting in mm: diameter, or the larger side of a rectangle."""
    best = 0.0
    for c in connectors_of(e):
        try:
            shape = c.Shape
            if shape == DB.ConnectorProfileType.Round:
                best = max(best, c.Radius * 2.0)
            else:
                best = max(best, c.Width, c.Height)
        except Exception:
            pass
    return round(ft_to_mm(best), 1)


# ---------------------------------------------------------------- settings storage
def settings_dir():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    folder = os.path.join(base, 'Emperor')
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except OSError:
            pass
    return folder


def load_json(name, default=None):
    path = os.path.join(settings_dir(), name)
    try:
        with open(path, 'rb') as f:
            return json.loads(f.read().decode('utf-8-sig'))
    except Exception:
        return default if default is not None else {}


def save_json(name, data):
    path = os.path.join(settings_dir(), name)
    try:
        with open(path, 'wb') as f:
            f.write(json.dumps(data, indent=1).encode('utf-8'))
        return True
    except Exception:
        return False


def project_key(doc):
    """Stable key per project for remembered settings."""
    try:
        path = doc.PathName or u''
    except Exception:
        path = u''
    title = doc.Title or u'project'
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', u'%s' % title)[:60] + (u'_%08x' % stable_hash(path) if path else u'')


def stable_hash(text):
    """Same value in every Revit session (Python's hash() is randomized on .NET 8 / Revit 2025)."""
    h = 2166136261
    for ch in u'%s' % text:
        h = ((h ^ ord(ch)) * 16777619) & 0xffffffff
    return h


# ---------------------------------------------------------------- quiet transactions
class QuietFailures(DB.IFailuresPreprocessor):
    """Deletes warnings (and counts them) so a batch is not interrupted by dialogs."""
    __namespace__ = 'EmperorMEP'

    def __init__(self, sink):
        self.sink = sink

    def PreprocessFailures(self, accessor):
        try:
            for f in list(accessor.GetFailureMessages()):
                try:
                    self.sink.append(f.GetDescriptionText())
                except Exception:
                    self.sink.append('(warning)')
                if f.GetSeverity() == DB.FailureSeverity.Warning:
                    accessor.DeleteWarning(f)
        except Exception:
            pass
        return DB.FailureProcessingResult.Continue


def begin(doc, name):
    """Transaction that never shows warning dialogs. Returns (transaction, warnings list)."""
    sink = []
    t = DB.Transaction(doc, name)
    t.Start()
    try:
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(QuietFailures(sink))
        opts.SetForcedModalHandling(False)
        t.SetFailureHandlingOptions(opts)
    except Exception:
        pass
    return t, sink


def view_axes(view):
    """(right, up) unit vectors of a view - used to work in the view's own 2D coordinates."""
    return view.RightDirection, view.UpDirection


def to_uv(p, right, up):
    return (p.DotProduct(right), p.DotProduct(up))
