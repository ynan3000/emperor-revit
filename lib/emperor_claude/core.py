# -*- coding: utf-8 -*-
"""Emperor Claude Connector - the Revit-API work behind every tool.

Every function runs on Revit's main thread (the listener hands requests over
through an ExternalEvent) and returns (http_status, dict).
IronPython 2.7 and CPython 3 compatible (no f-strings).
"""
import os
import re
import json
import time
import traceback

from pyrevit import DB, HOST_APP
from System.Collections.Generic import List

from emperor_claude import settings, jobs, helpers

try:
    string_types = (basestring,)  # noqa: F821  (IronPython 2.7)
except NameError:
    string_types = (str,)

VERSION = "1.6.1"
MAX_IDS = 500
MAX_ELEMENTS = 1000


# ----------------------------------------------------------------------------- helpers
def _resp(data, status=200):
    return status, data


def _err(message, status=400):
    return status, {"error": message}


def _body(request):
    if isinstance(request, dict):
        return request
    return {}


def _doc():
    return HOST_APP.doc


def _no_doc():
    return _err("No Revit project is open.", 409)


def _write_guard():
    if not settings.load().get("allow_write"):
        return _err("Write access is OFF. Ask the user to switch it ON in Revit: "
                    "Emperor tab > Claude Connector > Write access.", 403)
    return None


from pyrevit.compat import get_elementid_value_func as _get_eid_value_func
_EID_VALUE = _get_eid_value_func()   # ElementId.Value (2024+) or .IntegerValue (older)


def _eid_int(eid):
    """ElementId -> int on every Revit version."""
    return int(_EID_VALUE(eid))


def _make_eid(n):
    try:
        return DB.ElementId(int(n))
    except Exception:
        import System
        return DB.ElementId(System.Int64(int(n)))


def _to_m(value):
    return round(DB.UnitUtils.ConvertFromInternalUnits(value, DB.UnitTypeId.Meters), 4)


def _name(e):
    try:
        return DB.Element.Name.GetValue(e)   # works for element types too (IronPython quirk)
    except Exception:
        pass
    try:
        return e.Name
    except Exception:
        return None


def _type_name(doc, e):
    try:
        tid = e.GetTypeId()
        if tid is None or _eid_int(tid) == -1:
            return None
        t = doc.GetElement(tid)
        if t is None:
            return None
        try:
            return "%s : %s" % (t.FamilyName, _name(t))
        except Exception:
            return _name(t)
    except Exception:
        return None


def _param_value(p):
    if p is None:
        return None
    try:
        if not p.HasValue:
            return None
    except Exception:
        pass
    st = p.StorageType
    if st == DB.StorageType.String:
        return p.AsString()
    text = None
    try:
        text = p.AsValueString()
    except Exception:
        pass
    if st == DB.StorageType.Integer:
        return text if text is not None else p.AsInteger()
    if st == DB.StorageType.Double:
        return text if text is not None else p.AsDouble()
    if st == DB.StorageType.ElementId:
        return text if text else _eid_int(p.AsElementId())
    return text


def _lookup(doc, e, name):
    """Instance parameter first, then the element's type."""
    p = e.LookupParameter(name)
    if p is None:
        try:
            t = doc.GetElement(e.GetTypeId())
            if t is not None:
                p = t.LookupParameter(name)
        except Exception:
            p = None
    return p


def _elem_info(doc, e, names=None):
    info = {
        "id": _eid_int(e.Id),
        "category": e.Category.Name if e.Category else None,
        "name": _name(e),
        "family_type": _type_name(doc, e),
    }
    if names:
        info["parameters"] = dict((n, _param_value(_lookup(doc, e, n))) for n in names)
    return info


def _get_element(doc, n):
    try:
        return doc.GetElement(_make_eid(n))
    except Exception:
        return None


def _find_category(doc, text):
    wanted = (text or "").strip().lower()
    partial = []
    for c in doc.Settings.Categories:
        cname = c.Name
        if cname.lower() == wanted:
            return c, []
        if wanted and wanted in cname.lower():
            partial.append(c)
    if len(partial) == 1:
        return partial[0], []
    return None, [c.Name for c in partial][:15]


def _safe_filename(text):
    return re.sub(r'[\\/:*?"<>|]', "_", text).strip() or "export"


# ----------------------------------------------------------------------------- read routes
def _status():
    doc = _doc()
    return _resp({
        "ok": True,
        "revit_version": str(HOST_APP.version),
        "document": doc.Title if doc else None,
        "active_view": doc.ActiveView.Name if doc and doc.ActiveView else None,
        "write_access": bool(settings.load().get("allow_write")),
        "scripting_access": bool(settings.load().get("allow_scripts")),
        "connector_version": VERSION,
    })


def _project():
    doc = _doc()
    if doc is None:
        return _no_doc()
    pi = doc.ProjectInformation
    data = {
        "title": doc.Title,
        "path": doc.PathName,
        "is_workshared": doc.IsWorkshared,
        "is_cloud_model": doc.IsModelInCloud,
        "revit_version": str(HOST_APP.version),
    }
    for label, attr in (("project_name", "Name"), ("project_number", "Number"),
                        ("client", "ClientName"), ("address", "Address"),
                        ("status", "Status"), ("issue_date", "IssueDate"),
                        ("organization", "OrganizationName"), ("building", "BuildingName"),
                        ("author", "Author")):
        try:
            data[label] = getattr(pi, attr)
        except Exception:
            data[label] = None
    return _resp(data)


def _levels():
    doc = _doc()
    if doc is None:
        return _no_doc()
    items = []
    for lv in DB.FilteredElementCollector(doc).OfClass(DB.Level):
        items.append({"id": _eid_int(lv.Id), "name": lv.Name, "elevation_m": _to_m(lv.Elevation)})
    items.sort(key=lambda x: x["elevation_m"])
    return _resp({"count": len(items), "levels": items})


def _sheets():
    doc = _doc()
    if doc is None:
        return _no_doc()
    items = []
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
        try:
            placed = len(list(s.GetAllPlacedViews()))
        except Exception:
            placed = None
        items.append({"id": _eid_int(s.Id), "number": s.SheetNumber, "name": s.Name,
                      "placed_views": placed})
    items.sort(key=lambda x: x["number"])
    return _resp({"count": len(items), "sheets": items})


def _views():
    doc = _doc()
    if doc is None:
        return _no_doc()
    items = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
        try:
            if v.IsTemplate or isinstance(v, DB.ViewSheet):
                continue
            if v.ViewType in (DB.ViewType.Internal, DB.ViewType.ProjectBrowser,
                              DB.ViewType.SystemBrowser, DB.ViewType.Undefined):
                continue
        except Exception:
            continue
        level = None
        try:
            level = v.GenLevel.Name if v.GenLevel else None
        except Exception:
            pass
        template = None
        try:
            if _eid_int(v.ViewTemplateId) != -1:
                template = _name(doc.GetElement(v.ViewTemplateId))
        except Exception:
            pass
        items.append({"id": _eid_int(v.Id), "name": v.Name, "type": str(v.ViewType),
                      "level": level, "template": template})
        if len(items) >= 2000:
            break
    items.sort(key=lambda x: (x["type"], x["name"]))
    return _resp({"count": len(items), "views": items})


def _links():
    doc = _doc()
    if doc is None:
        return _no_doc()
    by_type = {}
    for inst in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance):
        by_type.setdefault(_eid_int(inst.GetTypeId()), []).append(inst)
    items = []
    for t in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkType):
        tid = _eid_int(t.Id)
        row = {"type_id": tid, "name": _name(t), "instances": []}
        try:
            row["status"] = str(t.GetLinkedFileStatus())
        except Exception:
            row["status"] = None
        try:
            row["pinned"] = t.Pinned
        except Exception:
            pass
        try:
            row["attachment"] = str(t.AttachmentType)
        except Exception:
            pass
        for inst in by_type.get(tid, []):
            ws = None
            try:
                if doc.IsWorkshared:
                    ws = doc.GetWorksetTable().GetWorkset(inst.WorksetId).Name
            except Exception:
                pass
            row["instances"].append({"id": _eid_int(inst.Id), "name": _name(inst),
                                     "pinned": inst.Pinned, "workset": ws})
        row["instance_count"] = len(row["instances"])
        items.append(row)
    items.sort(key=lambda x: x["name"] or "")
    return _resp({"count": len(items), "links": items})


def _categories():
    doc = _doc()
    if doc is None:
        return _no_doc()
    counts = {}
    for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
        cat = e.Category
        if cat is None or cat.CategoryType != DB.CategoryType.Model:
            continue
        counts[cat.Name] = counts.get(cat.Name, 0) + 1
    rows = sorted(counts.items(), key=lambda kv: -kv[1])[:80]
    return _resp({"categories": [{"category": k, "count": v} for k, v in rows]})


def _selection():
    doc = _doc()
    uidoc = HOST_APP.uidoc
    if doc is None or uidoc is None:
        return _no_doc()
    items = []
    for eid in list(uidoc.Selection.GetElementIds())[:200]:
        e = doc.GetElement(eid)
        if e is not None:
            items.append(_elem_info(doc, e))
    return _resp({"count": len(items), "elements": items})


def _query_elements(request):
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    cat_text = body.get("category")
    if not cat_text:
        return _err("'category' is required, e.g. 'Mechanical Equipment'.")
    cat, suggestions = _find_category(doc, cat_text)
    if cat is None:
        return _err("Category not found: %s. Close matches: %s" % (cat_text, suggestions))
    names = body.get("parameters") or []
    contains = (body.get("name_contains") or "").lower()
    limit = max(1, min(int(body.get("limit") or 100), MAX_ELEMENTS))

    if body.get("in_active_view") in (True, "true", "True", 1):
        collector = DB.FilteredElementCollector(doc, doc.ActiveView.Id).OfCategoryId(cat.Id).WhereElementIsNotElementType()
    else:
        collector = DB.FilteredElementCollector(doc).OfCategoryId(cat.Id).WhereElementIsNotElementType()
    level_filter = (body.get("level") or "").strip().lower()
    total = 0
    items = []
    for e in collector:
        if level_filter:
            try:
                from emperor_claude.mep_tools import _level_name
                if _level_name(doc, e).lower() != level_filter:
                    continue
            except Exception:
                pass
        if contains:
            hay = ("%s %s" % (_name(e), _type_name(doc, e))).lower()
            if contains not in hay:
                continue
        total += 1
        if len(items) < limit:
            items.append(_elem_info(doc, e, names))
    return _resp({"category": cat.Name, "total_matches": total, "returned": len(items),
                  "elements": items})


def _get_parameters(request):
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    ids = (body.get("element_ids") or [])[:MAX_IDS]
    names = body.get("names") or []
    if not ids:
        return _err("'element_ids' is required.")
    out = []
    for n in ids:
        e = _get_element(doc, n)
        if e is None:
            out.append({"id": n, "error": "element not found"})
            continue
        info = _elem_info(doc, e)
        if names:
            info["parameters"] = dict((nm, _param_value(_lookup(doc, e, nm))) for nm in names)
        else:
            allp = {}
            for p in e.Parameters:
                try:
                    allp[p.Definition.Name] = _param_value(p)
                except Exception:
                    pass
            info["parameters"] = allp
        out.append(info)
    return _resp({"elements": out})


# ----------------------------------------------------------------------------- write routes
def _apply_value(p, value):
    st = p.StorageType
    if st == DB.StorageType.String:
        return p.Set(value if isinstance(value, string_types) else "%s" % value)
    if st == DB.StorageType.Integer:
        low = ("%s" % value).strip().lower()
        if low in ("true", "yes", "on"):
            return p.Set(1)
        if low in ("false", "no", "off"):
            return p.Set(0)
        return p.Set(int(float(value)))
    if st == DB.StorageType.Double:
        text = value if isinstance(value, string_types) else "%s" % value
        if p.SetValueString(text):      # interpreted in the project's display units
            return True
        return p.Set(float(value))
    if st == DB.StorageType.ElementId:
        return p.Set(_make_eid(value))
    return False


def _set_parameters(request):
    guard = _write_guard()
    if guard is not None:
        return guard
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    ids = (body.get("element_ids") or [])[:MAX_IDS]
    name = body.get("name")
    if not ids or not name or "value" not in body:
        return _err("'element_ids', 'name' and 'value' are required.")
    value = body.get("value")
    dry_run = body.get("dry_run", True)
    if isinstance(dry_run, string_types):
        dry_run = dry_run.strip().lower() != "false"

    plan = []
    for n in ids:
        e = _get_element(doc, n)
        if e is None:
            plan.append({"id": n, "status": "skipped", "reason": "element not found"})
            continue
        p = e.LookupParameter(name)          # instance parameters only
        if p is None:
            plan.append({"id": n, "status": "skipped",
                         "reason": "no instance parameter '%s' (type parameters are not edited)" % name})
        elif p.IsReadOnly:
            plan.append({"id": n, "status": "skipped", "reason": "parameter is read-only"})
        else:
            plan.append({"id": n, "status": "will change", "current": _param_value(p),
                         "new": value})
    if dry_run:
        return _resp({"dry_run": True, "parameter": name, "plan": plan,
                      "note": "Nothing was changed. Repeat with dry_run=false to apply."})

    changed, failed = 0, []
    t, sink = _begin(doc, "Emperor Claude: set '%s'" % name)
    try:
        for row in plan:
            if row["status"] != "will change":
                continue
            e = _get_element(doc, row["id"])
            p = e.LookupParameter(name)
            try:
                if _apply_value(p, value):
                    row["status"] = "changed"
                    row["now"] = _param_value(p)
                    changed += 1
                else:
                    row["status"] = "failed"
                    row["reason"] = "Revit rejected the value"
                    failed.append(row["id"])
            except Exception as ex:
                row["status"] = "failed"
                row["reason"] = "%s" % ex
                failed.append(row["id"])
        _commit(t, sink)
    except Exception:
        try:
            if t.HasStarted():
                t.RollBack()
        except Exception:
            pass
        raise
    return _resp({"dry_run": False, "parameter": name, "changed": changed,
                  "failed": failed, "details": plan, "revit_messages": _dedupe(sink)})


def _export_dwg(request):
    guard = _write_guard()
    if guard is not None:
        return guard
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    numbers = body.get("sheet_numbers") or []
    folder = body.get("folder")
    if not numbers or not folder:
        return _err("'sheet_numbers' (list) and 'folder' are required.")
    xref = body.get("xref_views", True)
    if isinstance(xref, string_types):
        xref = xref.strip().lower() != "false"

    sheets = {}
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
        sheets[s.SheetNumber] = s
    if not os.path.isdir(folder):
        os.makedirs(folder)

    opts = DB.DWGExportOptions()
    opts.MergedViews = not xref      # False = views on sheets and links as external references

    results = []
    for num in numbers:
        s = sheets.get(num)
        if s is None:
            results.append({"sheet": num, "status": "not found"})
            continue
        ids = List[DB.ElementId]()
        ids.Add(s.Id)
        fname = _safe_filename("%s-%s" % (s.SheetNumber, s.Name))
        try:
            ok = doc.Export(folder, fname, ids, opts)
            results.append({"sheet": num, "file": fname + ".dwg",
                            "status": "exported" if ok else "failed"})
        except Exception as ex:
            results.append({"sheet": num, "status": "failed", "reason": "%s" % ex})
    return _resp({"folder": folder, "xref_views": bool(xref), "results": results})


# ----------------------------------------------------------------------------- quiet transactions
class _QuietFailures(DB.IFailuresPreprocessor):
    """Answers Revit's warning / error dialogs automatically and records what they said."""
    __namespace__ = "EmperorClaudeConnector"

    def __init__(self, sink):
        self.sink = sink

    def PreprocessFailures(self, accessor):
        unresolved = False
        try:
            for f in list(accessor.GetFailureMessages()):
                try:
                    text = f.GetDescriptionText()
                except Exception:
                    text = "(no text)"
                sev = f.GetSeverity()
                self.sink.append({"severity": "%s" % sev, "message": text})
                try:
                    if sev == DB.FailureSeverity.Warning:
                        accessor.DeleteWarning(f)
                    elif sev == DB.FailureSeverity.Error:
                        done = False
                        for name in ("DetachElements", "UnlockConstraints", "SkipElements"):
                            rt = getattr(DB.FailureResolutionType, name, None)
                            if rt is not None and f.HasResolutionOfType(rt):
                                f.SetCurrentResolutionType(rt)   # e.g. "Disconnect"
                                accessor.ResolveFailure(f)
                                done = True
                                break
                        if not done:
                            default_rt = f.GetDefaultResolutionType()
                            if f.HasResolutions() and default_rt != DB.FailureResolutionType.DeleteElements:
                                accessor.ResolveFailure(f)
                            else:
                                unresolved = True
                except Exception:
                    unresolved = True
        except Exception:
            pass
        if unresolved:
            return DB.FailureProcessingResult.ProceedWithRollBack
        return DB.FailureProcessingResult.Continue


def _begin(doc, name):
    """Start a transaction that never shows warning dialogs. Returns (transaction, messages)."""
    sink = []
    t = DB.Transaction(doc, name)
    t.Start()
    try:
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(_QuietFailures(sink))
        opts.SetForcedModalHandling(False)
        opts.SetClearAfterRollback(True)
        t.SetFailureHandlingOptions(opts)
    except Exception:
        pass
    return t, sink


def _commit(t, sink):
    status = t.Commit()
    if status != DB.TransactionStatus.Committed:
        raise Exception("Revit rolled the change back (%s). Messages: %s" % (status, _dedupe(sink)))


def _dedupe(sink):
    seen, out = {}, []
    for m in sink:
        key = (m.get("severity"), m.get("message"))
        if key in seen:
            seen[key]["count"] += 1
        else:
            seen[key] = {"severity": m.get("severity"), "message": m.get("message"), "count": 1}
            out.append(seen[key])
    return out[:20]


# ----------------------------------------------------------------------------- CAD reading
def _cad_list():
    doc = _doc()
    if doc is None:
        return _no_doc()
    items = []
    for inst in DB.FilteredElementCollector(doc).OfClass(DB.ImportInstance):
        view = None
        try:
            if inst.ViewSpecific:
                view = _name(doc.GetElement(inst.OwnerViewId))
        except Exception:
            pass
        try:
            cat = inst.Category.Name if inst.Category else None
        except Exception:
            cat = None
        items.append({"id": _eid_int(inst.Id), "name": cat or _name(inst),
                      "linked": bool(inst.IsLinked), "view_specific": bool(inst.ViewSpecific),
                      "view": view})
    return _resp({"count": len(items), "cad": items})


def _walk_geometry(geom, visit):
    for g in geom:
        if isinstance(g, DB.GeometryInstance):
            _walk_geometry(g.GetInstanceGeometry(), visit)
        else:
            visit(g)


def _inspect_cad(request):
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    if not body.get("import_id"):
        return _err("'import_id' is required (see list_cad_imports).")
    inst = _get_element(doc, body["import_id"])
    if inst is None or not isinstance(inst, DB.ImportInstance):
        return _err("That id is not a CAD import.")
    want = body.get("layers") or []
    want_l = [w.lower() for w in want]
    include = bool(body.get("include_segments", False)) and bool(want)
    max_seg = max(1, min(int(body.get("max_segments") or 2000), 6000))

    opts = DB.Options()
    try:
        if inst.ViewSpecific:
            opts.View = doc.GetElement(inst.OwnerViewId)
    except Exception:
        pass
    geom = inst.get_Geometry(opts)
    if geom is None:
        return _err("No geometry could be read from this CAD import.")

    styles = {}
    layers = {}
    segments = []
    state = {"truncated": False, "blocks": 0}

    def layer_of(g):
        sid = _eid_int(g.GraphicsStyleId)
        if sid not in styles:
            nm = "(no layer)"
            try:
                gs = doc.GetElement(g.GraphicsStyleId)
                if gs is not None and gs.GraphicsStyleCategory is not None:
                    nm = gs.GraphicsStyleCategory.Name
            except Exception:
                pass
            styles[sid] = nm
        return styles[sid]

    def stats(name):
        if name not in layers:
            layers[name] = {"lines": 0, "polylines": 0, "arcs_and_curves": 0, "other": 0,
                            "length_m": 0.0, "min": None, "max": None}
        return layers[name]

    def grow(st, x, y):
        if st["min"] is None:
            st["min"], st["max"] = [x, y], [x, y]
        else:
            st["min"][0] = min(st["min"][0], x)
            st["min"][1] = min(st["min"][1], y)
            st["max"][0] = max(st["max"][0], x)
            st["max"][1] = max(st["max"][1], y)

    def add_points(st, name, pts):
        for i, p in enumerate(pts):
            x, y = _to_m(p.X), _to_m(p.Y)
            grow(st, x, y)
            if i > 0:
                q = pts[i - 1]
                qx, qy = _to_m(q.X), _to_m(q.Y)
                st["length_m"] += ((x - qx) ** 2 + (y - qy) ** 2) ** 0.5
                if include and name.lower() in want_l:
                    if len(segments) < max_seg:
                        segments.append([round(qx, 3), round(qy, 3), round(x, 3), round(y, 3)])
                    else:
                        state["truncated"] = True

    def visit(g):
        if isinstance(g, DB.Line):
            name = layer_of(g)
            st = stats(name)
            st["lines"] += 1
            add_points(st, name, [g.GetEndPoint(0), g.GetEndPoint(1)])
        elif isinstance(g, DB.PolyLine):
            name = layer_of(g)
            st = stats(name)
            st["polylines"] += 1
            add_points(st, name, list(g.GetCoordinates()))
        elif isinstance(g, DB.Curve):
            name = layer_of(g)
            st = stats(name)
            st["arcs_and_curves"] += 1
            add_points(st, name, list(g.Tessellate()))
        else:
            try:
                stats(layer_of(g))["other"] += 1
            except Exception:
                pass

    _walk_geometry(geom, visit)

    rows = []
    for name, st in layers.items():
        st["length_m"] = round(st["length_m"], 2)
        if st["min"]:
            st["min"] = [round(v, 3) for v in st["min"]]
            st["max"] = [round(v, 3) for v in st["max"]]
        row = {"layer": name}
        row.update(st)
        rows.append(row)
    rows.sort(key=lambda r: -r["length_m"])
    out = {"import_id": body["import_id"], "layer_count": len(rows), "layers": rows,
           "note": "Coordinates are meters in Revit project coordinates (same system create_ducts uses). "
                   "CAD text is not available through the Revit API."}
    if include:
        out["segments"] = segments
        out["segment_count"] = len(segments)
        out["truncated"] = state["truncated"]
        out["segment_format"] = "[x1, y1, x2, y2] in meters"
    return _resp(out)


# ----------------------------------------------------------------------------- MEP types and ducts
def _mechanical():
    from Autodesk.Revit.DB import Mechanical
    return Mechanical


def _mep_types():
    doc = _doc()
    if doc is None:
        return _no_doc()
    Mech = _mechanical()
    duct_types = [{"id": _eid_int(t.Id), "name": _name(t)}
                  for t in DB.FilteredElementCollector(doc).OfClass(Mech.DuctType)]
    systems = [{"id": _eid_int(t.Id), "name": _name(t)}
               for t in DB.FilteredElementCollector(doc).OfClass(Mech.MechanicalSystemType)]
    terminals = []
    for sym in (DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_DuctTerminal)
                .WhereElementIsElementType()):
        terminals.append({"id": _eid_int(sym.Id), "name": "%s : %s" % (getattr(sym, "FamilyName", ""), _name(sym))})
    levels = [{"id": _eid_int(lv.Id), "name": lv.Name, "elevation_m": _to_m(lv.Elevation)}
              for lv in DB.FilteredElementCollector(doc).OfClass(DB.Level)]
    levels.sort(key=lambda x: x["elevation_m"])
    return _resp({"duct_types": duct_types, "duct_system_types": systems,
                  "air_terminal_types": terminals[:100], "levels": levels})


def _match_named(items, text, what):
    wanted = (text or "").strip().lower()
    exact, partial = None, []
    for it in items:
        nm = (_name(it) or "")
        if nm.lower() == wanted:
            exact = it
            break
        if wanted and wanted in nm.lower():
            partial.append(it)
    if exact is not None:
        return exact, None
    if len(partial) == 1:
        return partial[0], None
    names = [(_name(i) or "") for i in (partial or items)][:20]
    return None, "%s '%s' not found. Options: %s" % (what, text, names)


def _split_segments(segs, tol=0.002):
    """Split (a, b, size) segments where another segment's end point touches their interior."""
    ends = set()
    for a, b, sz in segs:
        ends.add(a)
        ends.add(b)
    out = []
    for a, b, sz in segs:
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        cuts = []
        for p in ends:
            if p == a or p == b:
                continue
            px, py = p
            if px < min(ax, bx) - tol or px > max(ax, bx) + tol:
                continue
            if py < min(ay, by) - tol or py > max(ay, by) + tol:
                continue
            t = ((px - ax) * dx + (py - ay) * dy) / l2
            if t <= 0.0 or t >= 1.0:
                continue
            cx, cy = ax + t * dx, ay + t * dy
            if (px - cx) ** 2 + (py - cy) ** 2 <= tol * tol:
                cuts.append((t, p))
        cuts.sort()
        pts = [a] + [c[1] for c in cuts] + [b]
        for i in range(len(pts) - 1):
            out.append((pts[i], pts[i + 1], sz))
    return out


def _same_size(a, b):
    try:
        if a.Shape != b.Shape:
            return False
        if a.Shape == DB.ConnectorProfileType.Round:
            return abs(a.Radius - b.Radius) < 1e-4
        return abs(a.Width - b.Width) < 1e-4 and abs(a.Height - b.Height) < 1e-4
    except Exception:
        return True


def _connect_fittings(doc, ducts):
    """Join duct ends that meet: unions, transitions, elbows, tees and crosses."""
    groups = {}
    for d in ducts:
        for c in d.ConnectorManager.Connectors:
            if c.IsConnected:
                continue
            o = c.Origin
            key = (int(round(o.X * 304.8)), int(round(o.Y * 304.8)), int(round(o.Z * 304.8)))
            groups.setdefault(key, []).append(c)

    counts = {"unions": 0, "transitions": 0, "elbows": 0, "tees": 0, "crosses": 0}
    failures = []

    def opposite(a, b):
        return a.CoordinateSystem.BasisZ.DotProduct(b.CoordinateSystem.BasisZ) < -0.99

    for key, cons in groups.items():
        where = [round(key[0] / 1000.0, 3), round(key[1] / 1000.0, 3)]
        try:
            if len(cons) == 2:
                if opposite(cons[0], cons[1]):
                    if _same_size(cons[0], cons[1]):
                        doc.Create.NewUnionFitting(cons[0], cons[1])
                        counts["unions"] += 1
                    else:
                        doc.Create.NewTransitionFitting(cons[0], cons[1])
                        counts["transitions"] += 1
                else:
                    doc.Create.NewElbowFitting(cons[0], cons[1])
                    counts["elbows"] += 1
            elif len(cons) == 3:
                done = False
                for i in range(3):
                    a, b = [cons[j] for j in range(3) if j != i]
                    if opposite(a, b):
                        doc.Create.NewTeeFitting(a, b, cons[i])
                        counts["tees"] += 1
                        done = True
                        break
                if not done:
                    failures.append({"at_m": where, "reason": "3 ducts meet without a straight run"})
            elif len(cons) == 4:
                pair = None
                for j in range(1, 4):
                    if opposite(cons[0], cons[j]):
                        pair = j
                        break
                if pair is None:
                    failures.append({"at_m": where, "reason": "4 ducts meet without straight runs"})
                else:
                    rest = [cons[k] for k in range(1, 4) if k != pair]
                    doc.Create.NewCrossFitting(cons[0], cons[pair], rest[0], rest[1])
                    counts["crosses"] += 1
            elif len(cons) > 4:
                failures.append({"at_m": where, "reason": "%d ducts meet at one point" % len(cons)})
        except Exception as ex:
            failures.append({"at_m": where, "reason": "%s" % ex})
    return counts, failures


def _create_ducts(request):
    guard = _write_guard()
    if guard is not None:
        return guard
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    Mech = _mechanical()

    raw = body.get("segments") or []
    if not raw:
        return _err("'segments' is required: rows of [x1, y1, x2, y2] (+ optional size) in meters.")
    if len(raw) > 1500:
        return _err("Too many segments in one call (%d). Send at most 1500." % len(raw))

    dtype, msg = _match_named(list(DB.FilteredElementCollector(doc).OfClass(Mech.DuctType)),
                              body.get("duct_type"), "Duct type")
    if dtype is None:
        return _err(msg)
    stype, msg = _match_named(list(DB.FilteredElementCollector(doc).OfClass(Mech.MechanicalSystemType)),
                              body.get("system_type"), "System type")
    if stype is None:
        return _err(msg)
    lvl, msg = _match_named(list(DB.FilteredElementCollector(doc).OfClass(DB.Level)),
                            body.get("level"), "Level")
    if lvl is None:
        return _err(msg)

    default_size = None
    if body.get("diameter_mm"):
        default_size = ("round", float(body["diameter_mm"]))
    elif body.get("width_mm") and body.get("height_mm"):
        default_size = ("rect", float(body["width_mm"]), float(body["height_mm"]))
    offset_m = float(body.get("offset_m", 2.7))
    snap = lambda v: round(float(v), 3)

    segs, seen = [], set()
    for row in raw:
        if len(row) >= 6:
            size = ("rect", float(row[4]), float(row[5]))
        elif len(row) == 5:
            size = ("round", float(row[4]))
        else:
            size = default_size
        if size is None:
            return _err("A segment has no size: add width_mm + height_mm (or diameter_mm) to the "
                        "call, or put the size at the end of each row: [x1,y1,x2,y2,width,height].")
        a = (snap(row[0]), snap(row[1]))
        b = (snap(row[2]), snap(row[3]))
        if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 < 0.001 ** 2:
            continue
        key = (a, b) if a <= b else (b, a)
        if key in seen:
            continue
        seen.add(key)
        segs.append((a, b, size))
    segs = _split_segments(segs)

    z = lvl.Elevation + DB.UnitUtils.ConvertToInternalUnits(offset_m, DB.UnitTypeId.Meters)
    to_ft = lambda v: DB.UnitUtils.ConvertToInternalUnits(v, DB.UnitTypeId.Meters)
    to_ft_mm = lambda v: DB.UnitUtils.ConvertToInternalUnits(float(v), DB.UnitTypeId.Millimeters)

    created, errors = [], []
    t, sink = _begin(doc, "Emperor Claude: create ducts")
    try:
        for a, b, size in segs:
            try:
                p1 = DB.XYZ(to_ft(a[0]), to_ft(a[1]), z)
                p2 = DB.XYZ(to_ft(b[0]), to_ft(b[1]), z)
                duct = Mech.Duct.Create(doc, stype.Id, dtype.Id, lvl.Id, p1, p2)
                if size[0] == "round":
                    prm = duct.get_Parameter(DB.BuiltInParameter.RBS_CURVE_DIAMETER_PARAM)
                    if prm is None:
                        errors.append({"segment_m": [a[0], a[1], b[0], b[1]],
                                       "reason": "duct type is rectangular, diameter ignored"})
                    else:
                        prm.Set(to_ft_mm(size[1]))
                else:
                    pw = duct.get_Parameter(DB.BuiltInParameter.RBS_CURVE_WIDTH_PARAM)
                    ph = duct.get_Parameter(DB.BuiltInParameter.RBS_CURVE_HEIGHT_PARAM)
                    if pw is None or ph is None:
                        errors.append({"segment_m": [a[0], a[1], b[0], b[1]],
                                       "reason": "duct type is round, width/height ignored"})
                    else:
                        pw.Set(to_ft_mm(size[1]))
                        ph.Set(to_ft_mm(size[2]))
                created.append(duct)
            except Exception as ex:
                errors.append({"segment_m": [a[0], a[1], b[0], b[1]], "reason": "%s" % ex})

        counts, failures = {}, []
        if created and body.get("connect_fittings", True):
            doc.Regenerate()
            counts, failures = _connect_fittings(doc, created)
        _commit(t, sink)
    except Exception:
        try:
            if t.HasStarted():
                t.RollBack()
        except Exception:
            pass
        raise
    return _resp({
        "ducts_created": len(created),
        "segments_after_splitting": len(segs),
        "fittings": counts,
        "fitting_failures": failures[:50],
        "fitting_failure_count": len(failures),
        "duct_errors": errors[:50],
        "duct_error_count": len(errors),
        "revit_messages": _dedupe(sink),
        "duct_ids_sample": [_eid_int(d.Id) for d in created[:50]],
        "undo": "One Ctrl+Z in Revit removes everything this call created.",
    })


# ----------------------------------------------------------------------------- grids and families
def _grids():
    doc = _doc()
    if doc is None:
        return _no_doc()
    items = []
    for g in DB.FilteredElementCollector(doc).OfClass(DB.Grid):
        row = {"id": _eid_int(g.Id), "name": g.Name}
        try:
            curve = g.Curve
            p0, p1 = curve.GetEndPoint(0), curve.GetEndPoint(1)
            row["start_m"] = [_to_m(p0.X), _to_m(p0.Y)]
            row["end_m"] = [_to_m(p1.X), _to_m(p1.Y)]
            row["straight"] = isinstance(curve, DB.Line)
        except Exception:
            pass
        items.append(row)
    items.sort(key=lambda r: r["name"])
    return _resp({"count": len(items), "grids": items,
                  "note": "Use grid intersections to calibrate a PDF or drawing to Revit coordinates."})


def _family_label(sym):
    try:
        return "%s : %s" % (sym.FamilyName, _name(sym))
    except Exception:
        return _name(sym)


def _family_types(request):
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    collector = DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol)
    if body.get("category"):
        cat, suggestions = _find_category(doc, body["category"])
        if cat is None:
            return _err("Category not found: %s. Close matches: %s" % (body["category"], suggestions))
        collector = collector.OfCategoryId(cat.Id)
    contains = (body.get("name_contains") or "").lower()
    limit = max(1, min(int(body.get("limit") or 100), 500))
    rows = []
    for sym in collector:
        label = _family_label(sym)
        if contains and contains not in (label or "").lower():
            continue
        row = {"id": _eid_int(sym.Id), "type": label,
               "category": sym.Category.Name if sym.Category else None}
        try:
            row["active"] = bool(sym.IsActive)
            row["placement"] = "%s" % sym.Family.FamilyPlacementType
        except Exception:
            pass
        rows.append(row)
        if len(rows) >= limit:
            break
    rows.sort(key=lambda r: r["type"] or "")
    return _resp({"count": len(rows), "family_types": rows,
                  "note": "placement OneLevelBased can be placed by place_family; "
                          "face-based / work-plane families need a host and will fail."})


def _load_family(request):
    guard = _write_guard()
    if guard is not None:
        return guard
    doc = _doc()
    if doc is None:
        return _no_doc()
    path = _body(request).get("path")
    if not path or not os.path.isfile(path):
        return _err("'path' must be an existing .rfa file on the Revit PC.")
    result = doc.LoadFamily(path)
    ok = result[0] if isinstance(result, tuple) else result
    return _resp({"loaded": bool(ok), "path": path,
                  "note": "False usually means the family is already loaded."})


def _place_family(request):
    guard = _write_guard()
    if guard is not None:
        return guard
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    import math
    from Autodesk.Revit.DB import Structure

    symbols = list(DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol))
    wanted = (body.get("family_type") or "").strip().lower()
    exact, partial = None, []
    for sym in symbols:
        label = (_family_label(sym) or "").lower()
        if label == wanted:
            exact = sym
            break
        if wanted and wanted in label:
            partial.append(sym)
    sym = exact or (partial[0] if len(partial) == 1 else None)
    if sym is None:
        options = [_family_label(x) for x in (partial or symbols)][:20]
        return _err("Family type '%s' not found or ambiguous. Options: %s" % (body.get("family_type"), options))
    lvl, msg = _match_named(list(DB.FilteredElementCollector(doc).OfClass(DB.Level)),
                            body.get("level"), "Level")
    if lvl is None:
        return _err(msg)
    places = body.get("placements") or []
    if not places:
        return _err("'placements' is required: list of {x, y, offset_m?, rotation_deg?} in meters.")
    if len(places) > 500:
        return _err("At most 500 placements per call.")
    default_offset = float(body.get("offset_m", 0.0))

    to_ft = lambda v: DB.UnitUtils.ConvertToInternalUnits(float(v), DB.UnitTypeId.Meters)
    placed, errors = [], []
    t, sink = _begin(doc, "Emperor Claude: place %s" % _family_label(sym))
    try:
        if not sym.IsActive:
            sym.Activate()
            doc.Regenerate()
        for p in places:
            try:
                offset = float(p.get("offset_m", default_offset))
                pt = DB.XYZ(to_ft(p["x"]), to_ft(p["y"]), lvl.Elevation + to_ft(offset))
                inst = doc.Create.NewFamilyInstance(pt, sym, lvl, Structure.StructuralType.NonStructural)
                for bip in (DB.BuiltInParameter.INSTANCE_ELEVATION_PARAM,
                            DB.BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM):
                    prm = inst.get_Parameter(bip)
                    if prm is not None and not prm.IsReadOnly:
                        prm.Set(to_ft(offset))
                        break
                rot = float(p.get("rotation_deg", 0.0))
                if abs(rot) > 1e-6:
                    axis = DB.Line.CreateBound(pt, DB.XYZ(pt.X, pt.Y, pt.Z + 1.0))
                    DB.ElementTransformUtils.RotateElement(doc, inst.Id, axis, math.radians(rot))
                placed.append(_eid_int(inst.Id))
            except Exception as ex:
                errors.append({"placement": p, "reason": "%s" % ex})
        _commit(t, sink)
    except Exception:
        try:
            if t.HasStarted():
                t.RollBack()
        except Exception:
            pass
        raise
    return _resp({"family_type": _family_label(sym), "placed": len(placed), "ids": placed[:100],
                  "errors": errors[:50], "error_count": len(errors),
                  "revit_messages": _dedupe(sink),
                  "undo": "One Ctrl+Z in Revit removes everything this call placed."})


# ----------------------------------------------------------------------------- script runner
def _jsonable(value):
    try:
        json.dumps(value)
        return value
    except Exception:
        return "%s" % (value,)


# ----------------------------------------------------------------------------- saved scripts
def _clean_name(name):
    return re.sub(r"[^A-Za-z0-9_\-]", "", "%s" % (name or ""))[:60]


def _scripts_dir():
    folder = os.path.join(settings.settings_dir(), "scripts")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return folder


def _recipes_dir():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "recipes")


def _script_file(name):
    """(path, origin) of a saved script (user folder first) or a built-in recipe."""
    name = _clean_name(name)
    if not name:
        return None, None
    for folder, origin in ((_scripts_dir(), "saved"), (_recipes_dir(), "recipe")):
        path = os.path.join(folder, name + ".py")
        if os.path.isfile(path):
            return path, origin
    return None, None


def _read_text(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8-sig")


def _meta(text):
    desc, params = "", []
    for line in text.splitlines()[:25]:
        s = line.strip()
        if s.startswith("# DESC:"):
            desc = s[7:].strip()
        elif s.startswith("# PARAM:"):
            params.append(s[8:].strip())
    return desc, params


def script_guard():
    if not settings.load().get("allow_scripts"):
        return _err("Script access is OFF. Ask the user to switch it ON in Revit: "
                    "Emperor tab > Claude Connector > Scripting access.", 403)
    return None


def _save_script(request):
    guard = script_guard()
    if guard:
        return guard
    body = _body(request)
    name, code = _clean_name(body.get("name")), body.get("code")
    if not name or not code:
        return _err("'name' (letters, digits, _ and -) and 'code' are required.")
    header = ""
    if not code.lstrip().startswith("# DESC:") and body.get("description"):
        header = "# DESC: %s\n" % ("%s" % body.get("description")).replace("\n", " ")
    path = os.path.join(_scripts_dir(), name + ".py")
    with open(path, "wb") as f:
        f.write((header + code).encode("utf-8"))
    return _resp({"saved": name, "path": path, "bytes": os.path.getsize(path)})


def _list_scripts():
    rows = []
    for folder, origin in ((_scripts_dir(), "saved"), (_recipes_dir(), "recipe")):
        if not os.path.isdir(folder):
            continue
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".py"):
                continue
            try:
                desc, params = _meta(_read_text(os.path.join(folder, fn)))
            except Exception:
                desc, params = "(unreadable)", []
            rows.append({"name": fn[:-3], "origin": origin, "description": desc, "params": params})
    return _resp({"count": len(rows), "scripts": rows})


def _get_script(request):
    path, origin = _script_file(_body(request).get("name"))
    if path is None:
        return _err("No saved script or recipe with that name.", 404)
    text = _read_text(path)
    return _resp({"name": _clean_name(_body(request).get("name")), "origin": origin, "code": text})


# ----------------------------------------------------------------------------- change ledger
class _Ledger(object):
    """Counts what a script created / changed / deleted (Revit DocumentChanged event)."""

    def __init__(self, app):
        self.app = app
        self.added = set()
        self.modified = 0
        self.deleted = 0
        self.active = False

    def on_changed(self, sender, args):
        try:
            for i in args.GetAddedElementIds():
                self.added.add(_eid_int(i))
            self.modified += len(list(args.GetModifiedElementIds()))
            self.deleted += len(list(args.GetDeletedElementIds()))
        except Exception:
            pass

    def start(self):
        try:
            self.app.DocumentChanged += self.on_changed
            self.active = True
        except Exception:
            self.active = False

    def stop(self):
        if self.active:
            try:
                self.app.DocumentChanged -= self.on_changed
            except Exception:
                pass
            self.active = False

    def summary(self):
        return {"created": len(self.added), "modified": self.modified, "deleted": self.deleted}


def _cap_output(text, limit):
    if limit and len(text) > limit:
        head = int(limit * 0.65)
        tail = limit - head
        return text[:head] + "\n... [%d characters hidden - print less, or raise max_output] ...\n" % (
            len(text) - limit) + text[-tail:], True
    return text, False


def _run_script(request):
    """Run Python inside Revit. Inline 'code' or a saved script / recipe 'name' with 'params'."""
    guard = script_guard()
    if guard:
        return guard
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    job = jobs.get(body.get("_job_id")) if body.get("_job_id") else None

    code, label = body.get("code"), body.get("description")
    if body.get("name"):
        path, origin = _script_file(body.get("name"))
        if path is None:
            return _err("No saved script or recipe named '%s'. Use list_scripts." % body.get("name"), 404)
        code = _read_text(path)
        label = label or body.get("name")
    if not code:
        return _err("Give either 'code' or the 'name' of a saved script / recipe.")
    params = body.get("params") or {}
    if not isinstance(params, dict):
        return _err("'params' must be an object.")

    use_tx = body.get("use_transaction", True)
    if isinstance(use_tx, string_types):
        use_tx = use_tx.strip().lower() != "false"
    dry = body.get("dry_run", False)
    if isinstance(dry, string_types):
        dry = dry.strip().lower() == "true"
    if dry and not use_tx:
        return _err("dry_run needs use_transaction=true (the changes are rolled back at the end).")
    try:
        max_out = int(body.get("max_output") or 8000)
    except Exception:
        max_out = 8000

    import sys
    try:
        from StringIO import StringIO
    except ImportError:
        from io import StringIO
    from Autodesk.Revit import UI

    ns = {"doc": doc, "uidoc": HOST_APP.uidoc, "uiapp": HOST_APP.uiapp, "DB": DB, "UI": UI,
          "List": List, "os": os, "json": json, "result": None, "P": params, "H": helpers, "job": job}
    helpers.export(ns)
    helpers.bind(job)
    ledger = _Ledger(HOST_APP.uiapp.Application)
    buf = StringIO()
    old_out = sys.stdout
    sys.stdout = buf
    tx, sink = None, []
    state = "done"
    if job is not None:
        job.status = "running"
        job.started = time.time()
        try:
            job.deadline = job.started + float(body.get("max_seconds") or 900)
        except Exception:
            job.deadline = job.started + 900
    try:
        ledger.start()
        if use_tx:
            tx, sink = _begin(doc, "Emperor Claude: %s" % (label or "script"))
        exec(code, ns)
        if tx is not None:
            if dry:
                tx.RollBack()
            else:
                _commit(tx, sink)
        ok, error, trace = True, None, None
    except Exception as ex:
        try:
            if tx is not None and tx.HasStarted():
                tx.RollBack()
        except Exception:
            pass
        ok, error, trace = False, "%s" % ex, traceback.format_exc()[-2500:]
        state = "cancelled" if isinstance(ex, jobs.Cancelled) else "failed"
    finally:
        sys.stdout = old_out
        ledger.stop()
        helpers.bind(None)
    text, cut = _cap_output(buf.getvalue(), max_out)
    out = {"ok": ok, "output": text, "result": _jsonable(ns.get("result")),
           "error": error, "trace": trace, "revit_messages": _dedupe(sink)}
    if cut:
        out["output_truncated"] = True
    if dry and ok:
        out["dry_run"] = True
        out["note"] = "DRY RUN: everything was rolled back, the model is unchanged. Run again without dry_run to apply."
    elif ok:
        out["changes"] = ledger.summary()
        out["note"] = "IronPython 2.7. One undo step (Ctrl+Z) reverts the whole script." if use_tx else "No transaction was used."
    if job is not None:
        job.finished = time.time()
        job.status = state
        job.result = out
        if ok and not dry:
            job.added_ids = sorted(ledger.added)[:20000]
    return _resp(out)


def _revert_job(request):
    """Delete the elements a finished job created (changes and deletions are NOT restored - use Ctrl+Z for that)."""
    guard = _write_guard() or script_guard()
    if guard:
        return guard
    doc = _doc()
    if doc is None:
        return _no_doc()
    job = jobs.get(_body(request).get("id"))
    if job is None:
        return _err("Unknown job id.", 404)
    if not job.added_ids:
        return _resp({"deleted": 0, "note": "That job created nothing (or it was a dry run)."})
    tx, sink = _begin(doc, "Emperor Claude: revert job %s" % job.id)
    gone = 0
    try:
        for n in job.added_ids:
            el = doc.GetElement(_make_eid(n))
            if el is not None:
                try:
                    if el.Pinned:
                        el.Pinned = False
                except Exception:
                    pass
                try:
                    doc.Delete(el.Id)
                    gone += 1
                except Exception:
                    pass
        _commit(tx, sink)
    except Exception:
        try:
            tx.RollBack()
        except Exception:
            pass
        raise
    job.added_ids = []
    return _resp({"deleted": gone, "note": "Created elements removed. Modified or deleted elements were not restored."})


# ----------------------------------------------------------------------------- view snapshot
def _snapshot(request):
    """PNG of a view, zoomed to some elements. Changes nothing in the model (only the view zoom, restored after)."""
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    uidoc = HOST_APP.uidoc
    import glob
    import tempfile
    from Autodesk.Revit import UI

    ids = [_make_eid(int(i)) for i in (body.get("element_ids") or [])][:200]
    view = None
    if body.get("view_name"):
        for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
            if not v.IsTemplate and v.Name == body.get("view_name"):
                view = v
                break
        if view is None:
            return _err("No view named '%s'." % body.get("view_name"), 404)
    old_view = uidoc.ActiveView
    view = view or old_view
    margin = float(body.get("margin_m") or 2.0) / 0.3048
    pixels = max(300, min(int(body.get("pixels") or 1000), 2400))

    box = None
    if body.get("center_x") is not None and body.get("center_y") is not None:
        cx, cy = float(body["center_x"]) / 0.3048, float(body["center_y"]) / 0.3048
        half = float(body.get("half_size_m") or 6.0) / 0.3048
        box = (cx - half, cy - half, cx + half, cy + half)
    for i in ids:
        e = doc.GetElement(i)
        bb = e.get_BoundingBox(view) or e.get_BoundingBox(None) if e is not None else None
        if bb is None:
            continue
        b = (bb.Min.X - margin, bb.Min.Y - margin, bb.Max.X + margin, bb.Max.Y + margin)
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))

    switched = view.Id != old_view.Id
    corners = None
    uiview = None
    try:
        if switched:
            uidoc.ActiveView = view
        for uv in uidoc.GetOpenUIViews():
            if uv.ViewId == view.Id:
                uiview = uv
                break
        if uiview is not None:
            corners = list(uiview.GetZoomCorners())
            if box is not None:
                uiview.ZoomAndCenterRectangle(DB.XYZ(box[0], box[1], 0), DB.XYZ(box[2], box[3], 0))
        folder = tempfile.mkdtemp(prefix="emperor_snap_")
        base = os.path.join(folder, "snap")
        opts = DB.ImageExportOptions()
        opts.ZoomType = DB.ZoomFitType.FitToPage
        opts.PixelSize = pixels
        opts.ImageResolution = DB.ImageResolution.DPI_150
        opts.FilePath = base
        opts.ExportRange = DB.ExportRange.VisibleRegionOfCurrentView
        opts.HLRandWFViewsFileType = DB.ImageFileType.PNG
        opts.ShadowViewsFileType = DB.ImageFileType.PNG
        doc.ExportImage(opts)
        files = sorted(glob.glob(base + "*.png"))
        if not files:
            return _err("Revit did not write an image (is the view a plan, section or 3D view?).", 500)
        path = files[0]
        return _resp({"path": path, "view": view.Name, "pixels": pixels,
                      "zoomed_to_elements": len(ids), "bytes": os.path.getsize(path)})
    finally:
        try:
            if uiview is not None and corners:
                uiview.ZoomAndCenterRectangle(corners[0], corners[1])
        except Exception:
            pass
        try:
            if switched:
                uidoc.ActiveView = old_view
        except Exception:
            pass


# ----------------------------------------------------------------------------- session brief
def _notes_path():
    return os.path.join(settings.settings_dir(), "project_notes.md")


def _brief(request=None):
    """One call that replaces the usual discovery round trips: project, levels, links, MEP types, views, notes."""
    doc = _doc()
    if doc is None:
        return _no_doc()
    body = _body(request)
    path = _notes_path()
    if body.get("append_note"):
        with open(path, "ab") as f:
            f.write(("- %s\n" % ("%s" % body["append_note"]).replace("\n", " ")).encode("utf-8"))
    if body.get("replace_notes") is not None:
        with open(path, "wb") as f:
            f.write(("%s" % body["replace_notes"]).encode("utf-8"))
    notes = _read_text(path) if os.path.isfile(path) else ""
    Mech = _mechanical()
    sheet_views = set()
    for vp in DB.FilteredElementCollector(doc).OfClass(DB.Viewport):
        sheet_views.add(_eid_int(vp.ViewId))
    plans = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan):
        if v.IsTemplate:
            continue
        tpl = None
        try:
            if _eid_int(v.ViewTemplateId) != -1:
                tpl = _name(doc.GetElement(v.ViewTemplateId))
        except Exception:
            pass
        plans.append({"name": v.Name, "level": v.GenLevel.Name if v.GenLevel else None,
                      "on_sheet": _eid_int(v.Id) in sheet_views, "template": tpl})
    plans.sort(key=lambda x: (x["level"] or "", x["name"]))
    links = []
    for row in _links()[1].get("links", []):
        links.append({"name": row["name"], "status": row.get("status"), "instances": row.get("instance_count")})
    pipe_sys = [_name(t) for t in DB.FilteredElementCollector(doc).OfClass(DB.Plumbing.PipingSystemType)]
    pipe_types = [_name(t) for t in DB.FilteredElementCollector(doc).OfClass(DB.Plumbing.PipeType)]
    ins_types = [_name(t) for t in DB.FilteredElementCollector(doc).OfClass(DB.Plumbing.PipeInsulationType)]
    duct_sys = [_name(t) for t in DB.FilteredElementCollector(doc).OfClass(Mech.MechanicalSystemType)]
    duct_types = [_name(t) for t in DB.FilteredElementCollector(doc).OfClass(Mech.DuctType)]
    return _resp({
        "project": _project()[1],
        "active_view": doc.ActiveView.Name if doc.ActiveView else None,
        "write_access": bool(settings.load().get("allow_write")),
        "scripting_access": bool(settings.load().get("allow_scripts")),
        "levels": _levels()[1].get("levels", []),
        "links": links,
        "duct_system_types": duct_sys, "duct_types": duct_types,
        "pipe_system_types": pipe_sys, "pipe_types": pipe_types, "pipe_insulation_types": ins_types,
        "plan_views": plans[:60],
        "spaces": len(list(DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType())),
        "notes_file": path,
        "notes": notes[-4000:],
        "scripts": [r["name"] for r in _list_scripts()[1]["scripts"]],
    })


# ----------------------------------------------------------------------------- route table
GET_ROUTES = {
    "/status": _status,
    "/project": _project,
    "/levels": _levels,
    "/sheets": _sheets,
    "/views": _views,
    "/links": _links,
    "/categories": _categories,
    "/selection": _selection,
    "/cad/list": _cad_list,
    "/mep/types": _mep_types,
    "/grids": _grids,
    "/script/list": _list_scripts,
}
POST_ROUTES = {
    "/elements/query": _query_elements,
    "/parameters/get": _get_parameters,
    "/parameters/set": _set_parameters,
    "/export/dwg": _export_dwg,
    "/cad/inspect": _inspect_cad,
    "/mep/ducts": _create_ducts,
    "/script/run": _run_script,
    "/script/save": _save_script,
    "/script/get": _get_script,
    "/job/revert": _revert_job,
    "/snapshot": _snapshot,
    "/brief": _brief,
    "/family/types": _family_types,
    "/family/load": _load_family,
    "/family/place": _place_family,
}
try:
    from emperor_claude import mep_tools as _mep_tools
    POST_ROUTES.update(_mep_tools.ROUTES)
    POST_ROUTES["/brief"] = _mep_tools.brief          # session_brief now comes from the project memory
except Exception:
    _mep_tools = None


def dispatch(method, path, body):
    """Entry point used by the listener. Returns (status, dict)."""
    method = (method or "GET").upper()
    path = "/" + (path or "").strip("/")
    try:
        if method == "GET" and path in GET_ROUTES:
            return GET_ROUTES[path]()
        if method == "POST" and path in POST_ROUTES:
            return POST_ROUTES[path](body or {})
        return 404, {"error": "Unknown route: %s %s" % (method, path)}
    except Exception as ex:
        return 500, {"error": "%s" % ex, "trace": traceback.format_exc()[-1500:]}
