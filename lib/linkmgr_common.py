# -*- coding: utf-8 -*-
"""Shared helpers for the Link Manager: current document, constants and small utilities."""
import os
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows.Threading import (Dispatcher, DispatcherPriority, DispatcherFrame,
                                      DispatcherOperationCallback)
from pyrevit import revit, DB

doc = revit.doc
FT_TO_M = 0.3048
DASH = u"\u2014"
DOT = u"\u00B7"
CHEV_CLOSED = u"\u25B8"
CHEV_OPEN = u"\u25BE"


from pyrevit.compat import get_elementid_value_func as _get_eid_value_func
_EID_VALUE = _get_eid_value_func()   # ElementId.Value (2024+) or .IntegerValue (older)


def eid(element_id):
    """ElementId -> int on every Revit version."""
    return int(_EID_VALUE(element_id))


def ename(element):
    try:
        return DB.Element.Name.GetValue(element)
    except Exception:
        try:
            return element.Name
        except Exception:
            return "?"


def ws_raw(element):
    """Workset name or None (not workshared / unknown)."""
    if not doc.IsWorkshared:
        return None
    try:
        wid = element.WorksetId
        if wid.IntegerValue == -1:
            return None
        return doc.GetWorksetTable().GetWorkset(wid).Name
    except Exception:
        return None


def ws_name(element):
    if not doc.IsWorkshared:
        return "N/A (project is not workshared)"
    return ws_raw(element) or DASH


def doevents():
    """Let WPF repaint while a long operation is running."""
    try:
        frame = DispatcherFrame()

        def _exit(arg):
            frame.Continue = False
            return None

        Dispatcher.CurrentDispatcher.BeginInvoke(
            DispatcherPriority.Background, DispatcherOperationCallback(_exit), None)
        Dispatcher.PushFrame(frame)
    except Exception:
        pass


def transforms_equal(a, b, tol=1e-4):
    def same(p, q):
        return abs(p.X - q.X) < tol and abs(p.Y - q.Y) < tol and abs(p.Z - q.Z) < tol
    return (same(a.Origin, b.Origin) and same(a.BasisX, b.BasisX) and
            same(a.BasisY, b.BasisY) and same(a.BasisZ, b.BasisZ))


def same_path(a, b):
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except Exception:
        return False
