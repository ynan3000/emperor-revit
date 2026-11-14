# -*- coding: utf-8 -*-
"""Operations on the links of the current project. No UI code in here.

SAFETY: nothing here publishes, acquires or saves coordinates. Unloading a link passes a callback
that always answers "do not save" to Revit's shared-coordinates question.
"""
import io
from System.Collections.Generic import List
from pyrevit import revit, DB

from linkmgr_common import doc, ename
from linkmgr_data import room_bounding_param


def _first_line(ex):
    try:
        return u"{}".format(ex).split(u"\n")[0]
    except Exception:
        return u"error"


# ----------------------------------------------------------------------------
# Pin / unpin
# ----------------------------------------------------------------------------
def pin_instances(instances, flag, label):
    """Returns (ok_count, [failure texts]). Raises when the transaction itself fails."""
    t = DB.Transaction(doc, "Link Manager: " + label)
    ok, failed = 0, []
    try:
        t.Start()
        for i in instances:
            try:
                if i.Pinned != flag:
                    i.Pinned = flag
                ok += 1
            except Exception as ex:
                failed.append(u"{}: {}".format(ename(i), _first_line(ex)))
        t.Commit()
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
        raise
    return ok, failed


# ----------------------------------------------------------------------------
# Reload / unload (outside any transaction)
# ----------------------------------------------------------------------------
def reload_links(rows, progress=None):
    ok, failed = 0, []
    for idx, r in enumerate(rows):
        if progress is not None:
            progress(idx, len(rows), r["name"])
        try:
            r["type"].Reload()
            ok += 1
        except Exception as ex:
            failed.append(u"{}: {}".format(r["name"], _first_line(ex)))
    return ok, failed


try:
    class _DoNotSaveCallback(DB.ISaveSharedCoordinatesCallbackForLinks):
        """Revit may ask whether to save shared coordinates into a link when it is unloaded.
        The answer is always NO: the plugin never writes into linked files."""

        def GetSaveModifiedLinksOption(self, link_type):
            return DB.SaveModifiedLinksOptions.DoNotSaveLink
except Exception:
    _DoNotSaveCallback = None


def unload_links(rows, progress=None):
    ok, failed, skipped = 0, [], 0
    for idx, r in enumerate(rows):
        if progress is not None:
            progress(idx, len(rows), r["name"])
        if u"unloaded" in (r["status"] or u"").lower():
            skipped += 1
            continue
        try:
            r["type"].Unload(_DoNotSaveCallback() if _DoNotSaveCallback else None)
            ok += 1
        except Exception as ex:
            failed.append(u"{}: {}".format(r["name"], _first_line(ex)))
    return ok, failed, skipped


# ----------------------------------------------------------------------------
# Remove links / change reference type
# ----------------------------------------------------------------------------
def remove_links(rows):
    """Deletes the link types (and with them all their instances). One undo step."""
    t = DB.Transaction(doc, "Link Manager: remove links")
    ok, failed = 0, []
    try:
        t.Start()
        for r in rows:
            try:
                doc.Delete(r["type"].Id)
                ok += 1
            except Exception as ex:
                failed.append(u"{}: {}".format(r["name"], _first_line(ex)))
        t.Commit()
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
        raise
    return ok, failed


def set_reference_type(rows, overlay):
    wanted = DB.AttachmentType.Overlay if overlay else DB.AttachmentType.Attachment
    t = DB.Transaction(doc, "Link Manager: set reference type")
    ok, failed, skipped = 0, [], 0
    try:
        t.Start()
        for r in rows:
            try:
                if r["type"].AttachmentType == wanted:
                    skipped += 1
                    continue
                r["type"].AttachmentType = wanted
                ok += 1
            except Exception as ex:
                failed.append(u"{}: {}".format(r["name"], _first_line(ex)))
        t.Commit()
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
        raise
    return ok, failed, skipped


# ----------------------------------------------------------------------------
# Room bounding (type parameter of the link)
# ----------------------------------------------------------------------------
def set_room_bounding(rows, flag):
    """Switch 'Room Bounding' on / off for the link types. One undo step.
    Returns (changed, failed texts, unchanged count)."""
    t = DB.Transaction(doc, "Link Manager: room bounding " + ("on" if flag else "off"))
    changed, failed, same = 0, [], 0
    try:
        t.Start()
        for r in rows:
            try:
                p = room_bounding_param(r["type"])
                if p is None:
                    failed.append(u"{}: no Room Bounding parameter".format(r["name"]))
                    continue
                if p.IsReadOnly:
                    failed.append(u"{}: parameter is read-only".format(r["name"]))
                    continue
                if (p.AsInteger() == 1) == bool(flag):
                    same += 1
                    continue
                p.Set(1 if flag else 0)
                changed += 1
            except Exception as ex:
                failed.append(u"{}: {}".format(r["name"], _first_line(ex)))
        t.Commit()
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
        raise
    return changed, failed, same


# ----------------------------------------------------------------------------
# Select / zoom in Revit
# ----------------------------------------------------------------------------
def select_in_revit(instances):
    """Selects the link instances in the active view and tries to zoom to them."""
    ids = List[DB.ElementId]([i.Id for i in instances])
    uidoc = revit.uidoc
    uidoc.Selection.SetElementIds(ids)
    try:
        uidoc.ShowElements(ids)
    except Exception:
        pass
    return ids.Count


# ----------------------------------------------------------------------------
# CSV export (opens in Excel)
# ----------------------------------------------------------------------------
CSV_HEADER = [u"Link", u"Status", u"Reference type", u"Path type", u"Saved path", u"Resolved path",
              u"Link workset", u"Room bounding", u"Instance", u"Pinned", u"Shared position", u"Shared site",
              u"X (m)", u"Y (m)", u"Z (m)", u"Rotation", u"Instance workset", u"Level"]


def _cell(value):
    text = u"{}".format(value if value is not None else u"")
    return u'"' + text.replace(u'"', u'""') + u'"'


def export_csv(path, rows):
    """Writes one line per instance (one line for a link without instances). UTF-8 with BOM."""
    lines = [u",".join(_cell(h) for h in CSV_HEADER)]
    for r in rows:
        head = [r["name"], r["status"], r["attach"], r["path_type"], r["saved_path"],
                r["resolved_path"], r["workset"],
                {True: u"Yes", False: u"No"}.get(r.get("room_bounding"), u"")]
        if not r["idata"]:
            lines.append(u",".join(_cell(x) for x in head + [u"", u"", u"", u"", u"", u"", u"", u"",
                                                              u"", u""]))
        for d in r["idata"]:
            xyz = [p.strip() for p in d["xyz"].split(u",")]
            xyz += [u""] * (3 - len(xyz))
            level = (u"~" + d["level"]) if d["level_approx"] else d["level"]
            cells = head + [d["name"], u"Pinned" if d["pinned"] else u"Not pinned", d["shared_txt"],
                            d["shared_loc"], xyz[0], xyz[1], xyz[2], d["rot"], d["workset"], level]
            lines.append(u",".join(_cell(x) for x in cells))
    with io.open(path, "wb") as fh:
        fh.write(u"\ufeff".encode("utf-8"))
        fh.write((u"\r\n".join(lines) + u"\r\n").encode("utf-8"))
    return len(lines) - 1
