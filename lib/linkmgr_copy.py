# -*- coding: utf-8 -*-
"""Copying links (and their instances) into another open model.

SAFETY: this module never writes into linked files. It does not call PublishCoordinates,
SavePositions or AcquireCoordinates, and it never changes a link document's project location.
"""
import math
from pyrevit import DB

from linkmgr_common import doc, eid, ename, transforms_equal, DASH
from linkmgr_data import (shared_location_param, site_is_named, same_site_name, site_check_text,
                          room_bounding_param)
from linkmgr_sitepick import SitePicker


def open_target_models():
    """Project documents open in this session, other than the current one."""
    out = []
    for d in doc.Application.Documents:
        try:
            if d.IsLinked or d.IsFamilyDocument:
                continue
            if d.Equals(doc):
                continue
            out.append(d)
        except Exception:
            pass
    out.sort(key=lambda d: d.Title.lower())
    return out


COPY_STATE = {"site_mismatch": False, "saveable": False, "picks": []}


def reset_copy_state():
    COPY_STATE["site_mismatch"] = False
    COPY_STATE["saveable"] = False
    COPY_STATE["picks"] = []


def ensure_workset(tdoc, name):
    """WorksetId of the user workset called `name` in tdoc (created if missing), or None."""
    if not name or not tdoc.IsWorkshared:
        return None
    for ws in DB.FilteredWorksetCollector(tdoc).OfKind(DB.WorksetKind.UserWorkset):
        if ws.Name == name:
            return ws.Id
    return DB.Workset.Create(tdoc, name).Id


def set_workset(element, wid):
    if wid is None:
        return False
    p = element.get_Parameter(DB.BuiltInParameter.ELEM_PARTITION_PARAM)
    if p is not None and not p.IsReadOnly:
        p.Set(wid.IntegerValue)  # compat-ignore: WorksetId keeps IntegerValue in every Revit version
        return True
    return False


def match_transform(tdoc, inst, src_tf):
    """Make `inst` sit exactly where the source instance sits. Returns a short text."""
    tdoc.Regenerate()
    if transforms_equal(inst.GetTotalTransform(), src_tf):
        return "exact"
    if hasattr(inst, "SetTransform"):
        try:
            inst.SetTransform(src_tf)
            tdoc.Regenerate()
            if transforms_equal(inst.GetTotalTransform(), src_tf):
                return "transform applied"
        except Exception:
            pass
    tf = inst.GetTotalTransform()
    d_ang = (math.atan2(src_tf.BasisX.Y, src_tf.BasisX.X) -
             math.atan2(tf.BasisX.Y, tf.BasisX.X))
    if abs(d_ang) > 1e-9:
        axis = DB.Line.CreateBound(tf.Origin, tf.Origin.Add(DB.XYZ.BasisZ))
        DB.ElementTransformUtils.RotateElement(tdoc, inst.Id, axis, d_ang)
    vec = src_tf.Origin.Subtract(inst.GetTotalTransform().Origin)
    if vec.GetLength() > 1e-9:
        DB.ElementTransformUtils.MoveElement(tdoc, inst.Id, vec)
    tdoc.Regenerate()
    if transforms_equal(inst.GetTotalTransform(), src_tf):
        return "moved / rotated"
    return "POSITION DIFFERS"


def copy_shared_location(tdoc, inst, value):
    """Verify a named site without pretending a parameter write can create the association."""
    if not site_is_named(value):
        # An unshared source is expected to remain <Not Shared>; do not report that expected
        # state as a mismatch merely because the label is non-empty.
        try:
            cur = shared_location_param(inst)
            if not site_is_named(cur):
                return ""
            return "source is not shared, but target instance unexpectedly reports shared site '{}'".format(cur)
        except Exception as ex:
            return "shared-site status could not be verified ({})".format(ex)
    try:
        cur = shared_location_param(inst)
        if same_site_name(cur, value):
            return ""
        return "shared site is '{}' in the target (source '{}')".format(cur or DASH, value)
    except Exception as ex:
        return "shared site could not be verified ({})".format(ex)


def try_match_transform_preserving_site(tdoc, inst, src_tf, expected_site):
    """Try an exact transform in a SubTransaction and keep it only if the named site survives.

    If moving/rotating the instance detaches it from its shared site, roll the transform
    changes back. Returns (success, transform_result, observed_site).
    """
    sub = DB.SubTransaction(tdoc)
    started = False
    try:
        sub.Start()
        started = True
        how = match_transform(tdoc, inst, src_tf)
        tdoc.Regenerate()
        observed = shared_location_param(inst)
        exact = transforms_equal(inst.GetTotalTransform(), src_tf)
        if how != "POSITION DIFFERS" and exact and same_site_name(observed, expected_site):
            sub.Commit()
            return True, how, observed
        sub.RollBack()
        started = False
        tdoc.Regenerate()
        return False, how, observed
    except Exception:
        if started:
            try:
                sub.RollBack()
            except Exception:
                pass
        try:
            tdoc.Regenerate()
        except Exception:
            pass
        return False, "transform/site verification failed", shared_location_param(inst)

def _copy_instance(tdoc, type_id, row, d, copy_unshared_exact, notes, c):
    """Place ONE instance in the target. Raises on failure (the caller rolls that instance back)."""
    src_tf = d["inst"].GetTotalTransform()
    expected_site = (d["shared_loc"] or "").strip()
    # A named Shared Site is the strongest available indication of the instance's
    # Revit association. The exact-location option applies only when there is no
    # named site (for example, the instance name contains '<Not Shared>').
    source_marked_unshared = not site_is_named(expected_site)
    force_exact_unshared = bool(copy_unshared_exact and source_marked_unshared)
    expected_site_for_target = "" if force_exact_unshared else expected_site
    use_shared_placement = (not force_exact_unshared and
                            (d["shared"] is True or site_is_named(expected_site)))
    inst = None
    preserve_shared_transform = False

    if force_exact_unshared:
        if site_is_named(expected_site):
            notes.append(
                "instance '{}' is marked not shared-positioned; exact-position option used and "
                "the named site '{}' was intentionally not assigned".format(d["name"], expected_site))
        else:
            notes.append(
                "instance '{}' has no named shared site; exact source position option used".format(
                    d["name"]))

    # First try Revit's Shared placement for instances associated with a named site.
    # A shared-placement candidate is not discarded merely because its transform
    # differs: first verify the candidate's site, then attempt a transform correction
    # in a SubTransaction and roll it back if that would lose the site association.
    if use_shared_placement:
        picker = SitePicker(expected_site, row["name"])
        cand = None
        try:
            with picker:
                cand = DB.RevitLinkInstance.Create(tdoc, type_id, DB.ImportPlacement.Shared)
            if picker.result:
                COPY_STATE["picks"].append((d["name"], picker.result))
            tdoc.Regenerate()
            candidate_site = shared_location_param(cand)
            position_matches = transforms_equal(cand.GetTotalTransform(), src_tf)

            if same_site_name(candidate_site, expected_site):
                # This is the requested named site. Keep this instance even when the
                # target's shared-coordinate transform differs from the source.
                inst = cand
                c["shared"] += 1
                if not position_matches:
                    adjusted, how_candidate, observed_site = try_match_transform_preserving_site(
                        tdoc, cand, src_tf, expected_site)
                    if adjusted:
                        c["adjusted"] += 1
                    else:
                        preserve_shared_transform = True
                        notes.append(
                            "instance '{}' retained on shared site '{}' but target transform "
                            "differs from the source; transform correction was rolled back "
                            "to preserve the named site (observed '{}', result '{}')".format(
                                d["name"], expected_site, observed_site or DASH, how_candidate))
            elif expected_site and candidate_site:
                # The dialog returned a position, but it is not the source's named site.
                # Build and verify the exact-position replacement first; only then remove
                # the wrong candidate. This avoids a zero-instance interval that triggers
                # Revit's 'all instances ... have been deleted' warning.
                fallback = DB.RevitLinkInstance.Create(tdoc, type_id)
                how_fallback = match_transform(tdoc, fallback, src_tf)
                if how_fallback != "POSITION DIFFERS":
                    inst = fallback
                    if how_fallback != "exact":
                        c["adjusted"] += 1
                    tdoc.Delete(cand.Id)
                    notes.append(
                        "instance '{}' did not retain source shared site '{}' (candidate site '{}'); "
                        "exact-position fallback used and requires manual shared-site assignment".format(
                            d["name"], expected_site or DASH, candidate_site or DASH))
                else:
                    tdoc.Delete(fallback.Id)
                    inst = cand
                    preserve_shared_transform = True
                    notes.append(
                        "instance '{}' candidate site '{}' differs from source site '{}'; "
                        "exact-position fallback failed, so the shared-placement candidate was "
                        "kept rather than silently discarded".format(
                            d["name"], candidate_site or DASH, expected_site or DASH))
            else:
                # An empty/unreadable site is not proof that the candidate is wrong.
                # Keep it and do not move it blindly; further movement may detach the site.
                inst = cand
                if not position_matches:
                    preserve_shared_transform = True
                    notes.append(
                        "instance '{}' shared placement was created but its named site could "
                        "not be verified; transform differs, so the candidate was retained "
                        "without moving it".format(d["name"]))
                else:
                    notes.append(
                        "instance '{}' is at the exact transform, but its shared-site name "
                        "could not be verified".format(d["name"]))
        except Exception as ex:
            if picker.result:
                COPY_STATE["picks"].append((d["name"], picker.result))
            why = str(ex).split("\n")[0]
            if picker.result:
                why = why + " [position dialog: " + picker.result + "]"
            notes.append("shared placement failed for '{}': {}".format(d["name"], why))
            # If creation failed before returning an instance, use exact-origin fallback.
            # If a candidate was returned and a later check failed, keep it rather than
            # deleting a possibly valid shared placement.
            if cand is not None:
                inst = cand
                preserve_shared_transform = not transforms_equal(cand.GetTotalTransform(), src_tf)

    if inst is None:
        inst = DB.RevitLinkInstance.Create(tdoc, type_id)

    if preserve_shared_transform:
        how = "shared site preserved; transform left unchanged"
    elif (not use_shared_placement and not copy_unshared_exact):
        how = "origin-to-origin (exact-position option disabled)"
        notes.append(
            "instance '{}': no shared site; left at Revit's origin-to-origin placement because "
            "the exact-position option is disabled".format(d["name"]))
    else:
        how = match_transform(tdoc, inst, src_tf)
        if how == "POSITION DIFFERS":
            notes.append("instance '{}': position could not be matched exactly".format(d["name"]))
        elif how != "exact":
            c["adjusted"] += 1

    try:
        set_workset(inst, ensure_workset(tdoc, d["workset_raw"]))
    except Exception as ex:
        notes.append("instance workset not set ({})".format(ex))

    note = copy_shared_location(tdoc, inst, expected_site_for_target)
    if note:
        notes.append(note)
        COPY_STATE["site_mismatch"] = True
    elif site_is_named(expected_site_for_target):
        # Revit exposes the instance's named site in its instance name, while the
        # geometric Shared Position classifier is only a heuristic. The copy path
        # verifies the actual named association here; the table still shows the
        # separate geometric classification.
        if same_site_name(shared_location_param(inst), expected_site_for_target):
            c["site_ok"] += 1
        else:
            notes.append("instance '{}': expected shared site '{}' was not retained".format(
                d["name"], expected_site_for_target))
            COPY_STATE["site_mismatch"] = True
    if d["pinned"]:
        try:
            inst.Pinned = True
            c["pinned"] += 1
        except Exception:
            pass


def _first_line(ex):
    try:
        return u"{}".format(ex).split(u"\n")[0]
    except Exception:
        return u"error"


def copy_link(tdoc, row, sel, copy_unshared_exact=True, existing_type=None):
    """Copy one link and the selected instances into tdoc.

    * every instance is its own SubTransaction: one failing instance no longer loses the link
    * existing_type: the link already exists in the target; only missing instances are added
    """
    name = row["name"]
    t = DB.Transaction(tdoc, "Link Manager: copy link " + name)
    try:
        t.Start()
        notes = []
        if existing_type is None:
            mp = row["abs_mp"]
            if mp is None:
                mp = DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(row["resolved_path"])
            relative = row["path_type"].lower() == "relative" and bool(tdoc.PathName)
            lo = DB.RevitLinkOptions(
                relative, DB.WorksetConfiguration(DB.WorksetConfigurationOption.OpenLastViewed))
            res = DB.RevitLinkType.Create(tdoc, mp, lo)
            type_id = res.ElementId
            if type_id is None or eid(type_id) == -1:
                raise Exception("Revit could not load the model ({})".format(res.LoadResult))
            ltype = tdoc.GetElement(type_id)
            try:
                ltype.AttachmentType = (DB.AttachmentType.Overlay if row["attach"] == "Overlay"
                                        else DB.AttachmentType.Attachment)
            except Exception:
                pass
            try:
                set_workset(ltype, ensure_workset(tdoc, row["workset_raw"]))
            except Exception as ex:
                notes.append("link workset not set ({})".format(_first_line(ex)))
            if row.get("room_bounding") is not None:
                try:
                    rp = room_bounding_param(ltype)
                    if rp is not None and not rp.IsReadOnly:
                        rp.Set(1 if row["room_bounding"] else 0)
                except Exception as ex:
                    notes.append("room bounding not set ({})".format(_first_line(ex)))
            existing_tfs = []
        else:
            ltype = existing_type
            type_id = ltype.Id
            existing_tfs = [i.GetTotalTransform()
                            for i in DB.FilteredElementCollector(tdoc).OfClass(DB.RevitLinkInstance)
                            if eid(i.GetTypeId()) == eid(type_id)]

        counters = {"shared": 0, "adjusted": 0, "pinned": 0, "site_ok": 0}
        n_ok = n_present = 0
        failures = []
        for d in sel:
            src_tf = d["inst"].GetTotalTransform()
            if existing_tfs and any(transforms_equal(src_tf, tf) for tf in existing_tfs):
                n_present += 1
                continue
            snapshot = dict(counters)
            sub = DB.SubTransaction(tdoc)
            started = False
            try:
                sub.Start()
                started = True
                _copy_instance(tdoc, type_id, row, d, copy_unshared_exact, notes, counters)
                sub.Commit()
                started = False
                n_ok += 1
            except Exception as ex:
                if started:
                    try:
                        sub.RollBack()
                    except Exception:
                        pass
                counters.clear()
                counters.update(snapshot)
                failures.append(u"'{}': {}".format(d["name"], _first_line(ex)))

        if existing_type is None and sel and n_ok == 0:
            raise Exception("no instance could be copied: " + u"; ".join(failures[:3]))
        try:
            if ltype.HasSaveablePositions():
                COPY_STATE["saveable"] = True
        except Exception:
            pass
        t.Commit()

        msg = u"{} of {} instance{} copied".format(n_ok, len(sel), "" if len(sel) == 1 else "s")
        if existing_type is not None:
            msg = u"link already in the target: " + msg
            if n_present:
                msg += u", {} already there (skipped)".format(n_present)
        if counters["shared"]:
            msg += u", {} placed by shared coordinates".format(counters["shared"])
        if counters["site_ok"]:
            msg += u", {} on the right shared site".format(counters["site_ok"])
        if counters["adjusted"]:
            msg += u", {} adjusted to the exact position".format(counters["adjusted"])
        if counters["pinned"]:
            msg += u", {} pinned".format(counters["pinned"])
        if failures:
            msg += u", {} FAILED and were skipped: {}".format(len(failures), u"; ".join(failures[:5]))
        if notes:
            msg += u"  [" + u"; ".join(sorted(set(notes))) + u"]"
        return (name, True, msg)
    except Exception as ex:
        try:
            t.RollBack()
        except Exception:
            pass
        return (name, False, u"failed: {}".format(_first_line(ex)))


def copy_items_to_target(tdoc, items, copy_unshared_exact=True, policy="skip", progress=None):
    """Copy [(row, selected instances)] into one target model as a SINGLE undo step.

    policy: "skip" leaves links that already exist in the target alone,
            "add" adds only the instances the target link is missing.
    """
    results = []
    types = {}
    for t in DB.FilteredElementCollector(tdoc).OfClass(DB.RevitLinkType):
        types[ename(t).lower()] = t
    group = DB.TransactionGroup(tdoc, "Link Manager: copy links")
    started = False
    try:
        group.Start()
        started = True
        for idx, (r, sel) in enumerate(items):
            if progress is not None:
                progress(idx, len(items), r["name"])
            existing = types.get(r["name"].lower())
            if existing is not None and policy != "add":
                results.append((r["name"], False, u"already linked in the target, skipped"))
                continue
            results.append(copy_link(tdoc, r, sel, copy_unshared_exact, existing))
    finally:
        if started:
            try:
                if any(x[1] for x in results):
                    group.Assimilate()
                else:
                    group.RollBack()
            except Exception:
                try:
                    group.RollBack()
                except Exception:
                    pass
    return results


def build_preview(items, tdocs):
    """What a copy would do, per link: [{name, count, sites, site_check, present_in}]."""
    present = {}
    for td in tdocs:
        names = set()
        try:
            for t in DB.FilteredElementCollector(td).OfClass(DB.RevitLinkType):
                names.add(ename(t).lower())
        except Exception:
            pass
        present[td.Title] = names
    out = []
    for r, sel in items:
        sites = sorted(set(d["shared_loc"] for d in sel if site_is_named(d["shared_loc"])),
                       key=lambda x: x.lower())
        where = [title for title, names in present.items() if r["name"].lower() in names]
        out.append({
            "name": r["name"],
            "count": len(sel),
            "sites": u", ".join(sites),
            "site_check": site_check_text(r, sites),
            "present_in": u", ".join(where),
        })
    return out
