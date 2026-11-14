# -*- coding: utf-8 -*-
"""Reading link data from the current project, plus filtering and sorting of the link table."""
import math
from pyrevit import DB

from linkmgr_common import (doc, FT_TO_M, DASH, eid, ename, ws_raw, ws_name, transforms_equal)


# ----------------------------------------------------------------------------
# Reading link data
# ----------------------------------------------------------------------------
def path_info(link_type):
    info = {"status": "Unknown", "path_type": "Unknown", "saved_path": "", "resolved_path": "",
            "abs_mp": None}
    ref = None
    try:
        ref = DB.ExternalFileUtils.GetExternalFileReference(doc, link_type.Id)
    except Exception:
        try:
            ref = link_type.GetExternalFileReference()
        except Exception:
            ref = None
    if ref is not None:
        try:
            info["path_type"] = str(ref.PathType)
        except Exception:
            pass
        try:
            info["status"] = str(ref.GetLinkedFileStatus())
        except Exception:
            pass
        try:
            info["saved_path"] = DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(ref.GetPath())
        except Exception:
            pass
        try:
            info["abs_mp"] = ref.GetAbsolutePath()
            info["resolved_path"] = DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(
                info["abs_mp"])
        except Exception:
            pass
    return info


def position_kind(inst, host_tf):
    """Classify shared positioning against the named site used by this instance.

    Important: a Revit link can be placed using a named ProjectLocation that is not
    the linked document's ActiveProjectLocation. Comparing only against the active
    location can therefore report a false "No" for a correctly shared-positioned
    instance. Use the instance's observed Shared Site/name first, and only compare
    transforms against that matching ProjectLocation. This is read-only; it never
    changes project locations or acquires/publishes coordinates.
    """
    try:
        tf = inst.GetTotalTransform()
        link_doc = inst.GetLinkDocument()
        if link_doc is None:
            return None, "Unknown  (link not loaded)"

        site_name = shared_location_param(inst)
        selected_location = None
        if site_is_named(site_name):
            try:
                for loc in link_doc.ProjectLocations:
                    if same_site_name(ename(loc), site_name):
                        selected_location = loc
                        break
            except Exception:
                selected_location = None

            # If an instance reports a named site but that site cannot be resolved,
            # do not silently substitute ActiveProjectLocation and mislabel the result.
            if selected_location is None:
                return None, "Unknown  (named site not found in link)"

            tl = selected_location.GetTotalTransform()
            candidates = [host_tf.Inverse.Multiply(tl), host_tf.Multiply(tl.Inverse),
                          tl.Inverse.Multiply(host_tf), tl.Multiply(host_tf.Inverse)]
            # Check shared-coordinate relationships before checking identity: two
            # correctly shared-positioned models can legitimately yield an identity
            # instance transform when their relevant named coordinates coincide.
            for candidate in candidates:
                if transforms_equal(tf, candidate):
                    return True, "Yes  (shared coordinates)"
            return False, "No  (moved / center / manual)"

        # No named site is reported by the instance, so identity is origin-to-origin;
        # a non-identity transform is a manually/moved/center-positioned instance.
        if transforms_equal(tf, DB.Transform.Identity):
            return False, "No  (origin to origin)"
        return False, "No  (moved / center / manual)"
    except Exception:
        return None, "Unknown"


SHARED_LOC_NAMES = ("Shared Site", "Shared Location")


def shared_site_param(inst):
    """The instance's shared site parameter (or None). Tries known names, then scans."""
    for nm in SHARED_LOC_NAMES:
        try:
            p = inst.LookupParameter(nm)
            if p is not None:
                return p
        except Exception:
            pass
    try:
        for p in inst.Parameters:
            n = p.Definition.Name.lower()
            if "shared" in n and ("site" in n or "location" in n):
                return p
    except Exception:
        pass
    return None


def param_text(p, owner_doc=None):
    """Read a parameter as text, resolving ElementId values in its own document."""
    try:
        v = p.AsValueString()
        if not v and p.StorageType == DB.StorageType.String:
            v = p.AsString()
        if not v and p.StorageType == DB.StorageType.ElementId:
            d = owner_doc or doc
            e = d.GetElement(p.AsElementId()) if d is not None else None
            v = ename(e) if e is not None else ""
        return v or ""
    except Exception:
        return ""


NOT_SHARED = ("", "not shared", "<not shared>", "<not shared>.")


def site_from_name(inst_name):
    """Revit names a link instance '<file> : <n> : location <shared site>'."""
    try:
        for part in [x.strip() for x in inst_name.split(" : ")][1:]:
            if part.lower().startswith("location"):
                return part[len("location"):].strip()
    except Exception:
        pass
    return ""


def shared_location_param(inst):
    """Return the named shared site shown by this instance, when available.

    Revit's instance name is the most useful observable indication of the selected
    position. If it does not contain a named location, fall back to the parameter.
    Resolve ElementId parameter values against the instance's own document.
    """
    try:
        named = site_from_name(ename(inst))
        if site_is_named(named):
            return named
    except Exception:
        pass
    p = shared_site_param(inst)
    try:
        owner_doc = inst.Document
    except Exception:
        owner_doc = doc
    txt = param_text(p, owner_doc) if p is not None else ""
    return txt or site_from_name(ename(inst))


def site_is_named(txt):
    return (txt or "").strip().lower() not in NOT_SHARED


def same_site_name(a, b):
    """Case/whitespace-insensitive comparison for two explicit named sites."""
    return (site_is_named(a) and site_is_named(b) and
            u" ".join((a or u"").split()).lower() ==
            u" ".join((b or u"").split()).lower())


def inst_level(inst, levels):
    """Returns (text, approximate_bool)."""
    try:
        lid = inst.LevelId
        if lid is not None and eid(lid) != -1:
            lvl = doc.GetElement(lid)
            if lvl is not None:
                return ename(lvl), False
    except Exception:
        pass
    for bip in ("INSTANCE_REFERENCE_LEVEL_PARAM", "FAMILY_LEVEL_PARAM", "SCHEDULE_LEVEL_PARAM"):
        try:
            p = inst.get_Parameter(getattr(DB.BuiltInParameter, bip))
            if p is not None and p.HasValue:
                lvl = doc.GetElement(p.AsElementId())
                if lvl is not None:
                    return ename(lvl), False
        except Exception:
            pass
    if not levels:
        return DASH, False
    z = inst.GetTotalTransform().Origin.Z
    best = min(levels, key=lambda l: abs(l.Elevation - z))
    off = (z - best.Elevation) * FT_TO_M
    return u"{} ({:+.2f} m)".format(ename(best), off), True


def inst_data(inst, host_tf, levels):
    tf = inst.GetTotalTransform()
    o = tf.Origin
    rot = math.degrees(math.atan2(tf.BasisX.Y, tf.BasisX.X))
    shared, shared_txt = position_kind(inst, host_tf)
    lvl_txt, lvl_approx = inst_level(inst, levels)
    return {
        "inst": inst,
        "id": eid(inst.Id),
        "name": ename(inst),
        "pinned": bool(inst.Pinned),
        "shared": shared,
        "shared_txt": shared_txt,
        "shared_loc": shared_location_param(inst),
        "xyz": u"{:.3f},  {:.3f},  {:.3f}".format(o.X * FT_TO_M, o.Y * FT_TO_M, o.Z * FT_TO_M),
        "rot": u"{:.2f}\u00B0".format(rot),
        "workset": ws_name(inst),
        "workset_raw": ws_raw(inst),
        "level": lvl_txt,
        "level_approx": lvl_approx,
    }


def room_bounding_param(link_type):
    """The 'Room Bounding' type parameter of a link type (None when it cannot be found)."""
    try:
        p = link_type.get_Parameter(DB.BuiltInParameter.WALL_ATTR_ROOM_BOUNDING)
        if p is not None:
            return p
    except Exception:
        pass
    try:
        return link_type.LookupParameter("Room Bounding")
    except Exception:
        return None


def read_room_bounding(link_type):
    """True / False, or None when the link type has no readable Room Bounding parameter."""
    p = room_bounding_param(link_type)
    try:
        if p is None or not p.HasValue:
            return None
        return p.AsInteger() == 1
    except Exception:
        return None


def collect_links():
    host_tf = doc.ActiveProjectLocation.GetTotalTransform()
    levels = sorted(list(DB.FilteredElementCollector(doc).OfClass(DB.Level)),
                    key=lambda l: l.Elevation)
    by_type = {}
    for i in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance):
        by_type.setdefault(eid(i.GetTypeId()), []).append(i)

    rows = []
    for t in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkType):
        try:
            if t.IsNestedLink:
                continue
        except Exception:
            pass
        info = path_info(t)
        try:
            attach = str(t.AttachmentType)
        except Exception:
            attach = "Unknown"
        idata = [inst_data(i, host_tf, levels) for i in by_type.get(eid(t.Id), [])]
        idata.sort(key=lambda d: d["name"].lower())
        pinned_n = len([d for d in idata if d["pinned"]])
        rows.append({
            "id": eid(t.Id),
            "type": t,
            "name": ename(t),
            "status": info["status"],
            "path_type": info["path_type"],
            "saved_path": info["saved_path"],
            "resolved_path": info["resolved_path"],
            "attach": attach,
            "workset": ws_name(t),
            "workset_raw": ws_raw(t),
            "room_bounding": read_room_bounding(t),
            "shared_site": ", ".join(sorted(set(d["shared_loc"] for d in idata if d["shared_loc"]))),
            "abs_mp": info["abs_mp"],
            "idata": idata,
            "pinned_n": pinned_n,
        })
    rows.sort(key=lambda r: r["name"].lower())
    return rows


# ----------------------------------------------------------------------------
# Shared sites available in a link (read only)
# ----------------------------------------------------------------------------
_ALWAYS_PRESENT = (u"default site", u"internal")


def link_site_names(row):
    """Names of the project locations (shared sites) of a link, or None when the link is not loaded."""
    for d in row["idata"]:
        try:
            ld = d["inst"].GetLinkDocument()
            if ld is not None:
                return [ename(loc) for loc in ld.ProjectLocations]
        except Exception:
            pass
    return None


def site_check_text(row, sites):
    """Preview text: are the shared sites the instances use present in the link?"""
    if not sites:
        return u"not shared"
    available = link_site_names(row)
    if available is None:
        return u"link not loaded: cannot check"
    missing = [s for s in sites
               if s.strip().lower() not in _ALWAYS_PRESENT and
               not any(same_site_name(s, a) for a in available)]
    if missing:
        return u"not found in link: " + u", ".join(missing)
    return u"all found in link"


# ----------------------------------------------------------------------------
# Table filtering / sorting
# ----------------------------------------------------------------------------
NO_SITE = u"(not shared)"
ALL_SITES = u"All shared sites"


def all_sites(rows):
    names = set()
    for r in rows:
        for d in r["idata"]:
            if site_is_named(d["shared_loc"]):
                names.add(d["shared_loc"])
    return sorted(names, key=lambda x: x.lower())


def is_problem(row):
    return (row["status"] or u"").strip().lower() != u"loaded"


def row_matches(r, text=u"", site=u"", only_unpinned=False, only_problems=False):
    if only_problems and not is_problem(r):
        return False
    if only_unpinned and not any(not d["pinned"] for d in r["idata"]):
        return False
    if site and site != ALL_SITES:
        if site == NO_SITE:
            if not any(not site_is_named(d["shared_loc"]) for d in r["idata"]):
                return False
        elif not any(same_site_name(d["shared_loc"], site) for d in r["idata"]):
            return False
    text = (text or u"").strip().lower()
    if text:
        hay = [r["name"], r["saved_path"], r["resolved_path"], r["workset"], r["shared_site"],
               r["status"], r["attach"], r["path_type"]]
        for d in r["idata"]:
            hay.extend([d["name"], d["workset"], d["level"], d["shared_loc"], d["shared_txt"]])
        if not any(text in (h or u"").lower() for h in hay):
            return False
    return True


SORT_KEYS = {
    "name": lambda r: r["name"].lower(),
    "status": lambda r: (r["status"] or u"").lower(),
    "attach": lambda r: (r["attach"] or u"").lower(),
    "path_type": lambda r: (r["path_type"] or u"").lower(),
    "workset": lambda r: (r["workset"] or u"").lower(),
    "shared_site": lambda r: (r["shared_site"] or u"").lower(),
    "pinned": lambda r: (float(r["pinned_n"]) / len(r["idata"])) if r["idata"] else -1.0,
    "instances": lambda r: len(r["idata"]),
    "room_bounding": lambda r: {True: 1, False: 0}.get(r.get("room_bounding"), -1),
    "path": lambda r: (r["resolved_path"] or r["saved_path"] or u"").lower(),
}


def sort_rows(rows, key, desc=False):
    fn = SORT_KEYS.get(key)
    if fn is None:
        return list(rows)
    return sorted(rows, key=fn, reverse=bool(desc))
