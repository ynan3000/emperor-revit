# -*- coding: ascii -*-
"""System Box and Crop to 3D - 3D views with a section box.

system_elements(doc, element)            -> (systems, elements) of the MEP system(s) an element belongs to
make_system_box(doc, systems, ...)       -> View3D boxed around the whole system(s)
crop_box_from_plan(doc, plan, p1, p2)    -> (BoundingBoxXYZ, info) for a rectangle picked in a plan
make_view3d(doc, name, box, ...)         -> new / reused View3D with that section box
The caller owns the transaction.
"""
from Autodesk.Revit import DB

from emperor_mep.common import eid_int, name_of, is_invalid

FT_M = 0.3048


# ---------------------------------------------------------------- systems
def systems_of(element):
    found = {}
    try:
        s = element.MEPSystem               # ducts, pipes, flex
        if s is not None:
            found[eid_int(s.Id)] = s
    except Exception:
        pass
    try:
        mm = element.MEPModel                # terminals, equipment, fittings, accessories
        if mm is not None and mm.ConnectorManager is not None:
            for c in mm.ConnectorManager.Connectors:
                try:
                    if c.MEPSystem is not None:
                        found[eid_int(c.MEPSystem.Id)] = c.MEPSystem
                except Exception:
                    pass
    except Exception:
        pass
    return list(found.values())


def system_members(system):
    members = {}
    for getter in ('DuctNetwork', 'PipingNetwork', 'Elements'):
        try:
            coll = getattr(system, getter)
        except Exception:
            coll = None
        if coll is None:
            continue
        try:
            for e in coll:
                members[eid_int(e.Id)] = e
        except Exception:
            pass
    try:
        if system.BaseEquipment is not None:
            members[eid_int(system.BaseEquipment.Id)] = system.BaseEquipment
    except Exception:
        pass
    return list(members.values())


def union_box(elements, margin_ft=0.0):
    lo, hi = None, None
    for e in elements:
        try:
            bb = e.get_BoundingBox(None)
        except Exception:
            bb = None
        if bb is None:
            continue
        if lo is None:
            lo = [bb.Min.X, bb.Min.Y, bb.Min.Z]
            hi = [bb.Max.X, bb.Max.Y, bb.Max.Z]
        else:
            lo = [min(lo[0], bb.Min.X), min(lo[1], bb.Min.Y), min(lo[2], bb.Min.Z)]
            hi = [max(hi[0], bb.Max.X), max(hi[1], bb.Max.Y), max(hi[2], bb.Max.Z)]
    if lo is None:
        return None
    box = DB.BoundingBoxXYZ()
    box.Min = DB.XYZ(lo[0] - margin_ft, lo[1] - margin_ft, lo[2] - margin_ft)
    box.Max = DB.XYZ(hi[0] + margin_ft, hi[1] + margin_ft, hi[2] + margin_ft)
    return box


# ---------------------------------------------------------------- 3D views
def _three_d_type(doc):
    for vft in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
        if vft.ViewFamily == DB.ViewFamily.ThreeDimensional:
            return vft
    return None


def find_view3d(doc, name):
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View3D):
        if not v.IsTemplate and v.Name == name:
            return v
    return None


def unique_view_name(doc, base):
    names = set(v.Name for v in DB.FilteredElementCollector(doc).OfClass(DB.View) if not v.IsTemplate)
    if base not in names:
        return base
    n = 2
    while u'%s (%d)' % (base, n) in names:
        n += 1
    return u'%s (%d)' % (base, n)


def make_view3d(doc, name, box, reuse=True, detail_fine=True):
    """Create (or reuse by name) an isometric 3D view and set its section box."""
    view = find_view3d(doc, name) if reuse else None
    if view is None:
        vft = _three_d_type(doc)
        if vft is None:
            raise Exception('This project has no 3D view type.')
        view = DB.View3D.CreateIsometric(doc, vft.Id)
        view.Name = unique_view_name(doc, name)
    try:
        if not is_invalid(view.ViewTemplateId):
            view.ViewTemplateId = DB.ElementId.InvalidElementId   # a template could lock the section box
    except Exception:
        pass
    if detail_fine:
        try:
            view.DetailLevel = DB.ViewDetailLevel.Fine
        except Exception:
            pass
    view.IsSectionBoxActive = True
    view.SetSectionBox(box)
    return view


def system_label(system):
    try:
        return name_of(system) or u'System %d' % eid_int(system.Id)
    except Exception:
        return u'System'


def make_system_box(doc, systems, margin_m=0.3, reuse=True, hide_others=True, prefix='', separator='_',
                    create_missing=True, rename=True, show_context=True):
    elements = []
    for s in systems:
        elements.extend(system_members(s))
    box = union_box(elements, margin_m / FT_M)
    if box is None:
        raise Exception('The system has no elements with geometry.')
    label = u' + '.join(system_label(s) for s in systems[:3])
    if len(systems) > 3:
        label += u' + %d more' % (len(systems) - 3)
    view = make_view3d(doc, u'System Box - %s' % label, box, reuse=reuse)
    report = hide_other_systems(doc, view, systems, prefix, separator, create_missing, rename) if hide_others else None
    set_context_visibility(doc, view, show_context)
    return view, len(elements), report


# ---------------------------------------------------------------- crop a plan area to 3D
def _plane_z(doc, view_range, plane):
    try:
        lid = view_range.GetLevelId(plane)
    except Exception:
        return None
    if lid is None or is_invalid(lid):
        return None
    try:
        if lid == DB.PlanViewRange.Unlimited or lid == DB.PlanViewRange.LevelBelow or lid == DB.PlanViewRange.LevelAbove:
            return None
    except Exception:
        pass
    lvl = doc.GetElement(lid)
    if lvl is None:
        return None
    return lvl.ProjectElevation + view_range.GetOffset(plane)


def _levels_sorted(doc):
    return sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.ProjectElevation)


def _floor_boxes(doc):
    """(minX, minY, minZ, maxX, maxY, maxZ, source) of every floor in the host and in loaded links, host coordinates."""
    out = []
    for f in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Floors).WhereElementIsNotElementType():
        bb = f.get_BoundingBox(None)
        if bb is not None:
            out.append((bb.Min.X, bb.Min.Y, bb.Min.Z, bb.Max.X, bb.Max.Y, bb.Max.Z, u'host'))
    for inst in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance):
        try:
            ldoc = inst.GetLinkDocument()
        except Exception:
            ldoc = None
        if ldoc is None:
            continue
        tr = inst.GetTotalTransform()
        for f in DB.FilteredElementCollector(ldoc).OfCategory(DB.BuiltInCategory.OST_Floors).WhereElementIsNotElementType():
            bb = f.get_BoundingBox(None)
            if bb is None:
                continue
            xs, ys, zs = [], [], []
            for x in (bb.Min.X, bb.Max.X):
                for y in (bb.Min.Y, bb.Max.Y):
                    for z in (bb.Min.Z, bb.Max.Z):
                        p = tr.OfPoint(DB.XYZ(x, y, z))
                        xs.append(p.X)
                        ys.append(p.Y)
                        zs.append(p.Z)
            out.append((min(xs), min(ys), min(zs), max(xs), max(ys), max(zs), name_of(ldoc) or u'link'))
    return out


def crop_box_from_plan(doc, plan, p1, p2, fallback_height_m=4.0):
    """Section box for the rectangle p1-p2 picked in a plan view.

    Bottom = the bottom of the plan's view range.
    Top    = just under the floor of the level above (host or linked floor over the picked area);
             if no such floor is found: the level above, else the top of the view range.
    The box is aligned with the plan (works for rotated plans too)."""
    right, up = plan.RightDirection, plan.UpDirection
    u1, v1 = p1.DotProduct(right), p1.DotProduct(up)
    u2, v2 = p2.DotProduct(right), p2.DotProduct(up)
    umin, umax, vmin, vmax = min(u1, u2), max(u1, u2), min(v1, v2), max(v1, v2)
    if umax - umin < 0.1 or vmax - vmin < 0.1:
        raise Exception('The picked area is too small. Drag a rectangle around the area you want.')

    info = {}
    gen = plan.GenLevel
    base_z = gen.ProjectElevation if gen is not None else 0.0
    vr = plan.GetViewRange()
    bottom = _plane_z(doc, vr, DB.PlanViewPlane.BottomClipPlane)
    if bottom is None:
        bottom = _plane_z(doc, vr, DB.PlanViewPlane.ViewDepthPlane)
    if bottom is None:
        bottom = base_z
    top_range = _plane_z(doc, vr, DB.PlanViewPlane.TopClipPlane)

    above = None
    for lvl in _levels_sorted(doc):
        if lvl.ProjectElevation > base_z + 0.5:      # first level at least ~15 cm higher
            above = lvl
            break

    top = None
    if above is not None:
        za = above.ProjectElevation
        tol = 1.5 / FT_M                            # floors whose top is within 1.5 m of the level above
        best = None
        for (x0, y0, z0, x1, y1, z1, src) in _floor_boxes(doc):
            if abs(z1 - za) > tol or z0 <= bottom:
                continue
            # overlap with the picked rectangle, in the plan's own directions
            us, vs = [], []
            for x in (x0, x1):
                for y in (y0, y1):
                    p = DB.XYZ(x, y, 0)
                    us.append(p.DotProduct(right))
                    vs.append(p.DotProduct(up))
            if max(us) < umin or min(us) > umax or max(vs) < vmin or min(vs) > vmax:
                continue
            if best is None or z0 < best[0]:
                best = (z0, src)
        if best is not None:
            top = best[0] - 0.005 / FT_M            # 5 mm under the slab
            info['top_from'] = u'underside of the floor above (%s)' % best[1]
        else:
            top = za
            info['top_from'] = u'level above (%s) - no floor found over the area' % above.Name
    if top is None:
        top = top_range if top_range is not None else bottom + fallback_height_m / FT_M
        info['top_from'] = u'top of the view range'
    if top <= bottom:
        top = bottom + fallback_height_m / FT_M
        info['top_from'] = u'%s m above the bottom (top was below the bottom)' % fallback_height_m

    tr = DB.Transform.Identity
    tr.BasisX = right
    tr.BasisY = up
    tr.BasisZ = DB.XYZ.BasisZ
    tr.Origin = DB.XYZ.Zero
    box = DB.BoundingBoxXYZ()
    box.Transform = tr
    box.Min = DB.XYZ(umin, vmin, bottom)
    box.Max = DB.XYZ(umax, vmax, top)
    info['bottom_m'] = round(bottom * FT_M, 3)
    info['top_m'] = round(top * FT_M, 3)
    info['size_m'] = (round((umax - umin) * FT_M, 2), round((vmax - vmin) * FT_M, 2))
    return box, info


# ---------------------------------------------------------------- hide the other systems (view filters)
BIC = DB.BuiltInCategory
DUCT_FILTER_CATS = [BIC.OST_DuctTerminal, BIC.OST_DuctAccessory, BIC.OST_DuctFitting, BIC.OST_DuctInsulations,
                    BIC.OST_DuctLinings, BIC.OST_PlaceHolderDucts, BIC.OST_DuctCurves, BIC.OST_FlexDuctCurves]
PIPE_FILTER_CATS = [BIC.OST_PipeAccessory, BIC.OST_PipeFitting, BIC.OST_PipeInsulations, BIC.OST_PlaceHolderPipes,
                    BIC.OST_PipeCurves, BIC.OST_FlexPipeCurves, BIC.OST_PlumbingFixtures, BIC.OST_Sprinklers]
DUCT_PARAM = DB.BuiltInParameter.RBS_DUCT_SYSTEM_TYPE_PARAM
PIPE_PARAM = DB.BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM


def _all_system_types(doc):
    from Autodesk.Revit.DB import Mechanical, Plumbing
    out = []
    for t in DB.FilteredElementCollector(doc).OfClass(Mechanical.MechanicalSystemType):
        out.append((t, 'duct'))
    for t in DB.FilteredElementCollector(doc).OfClass(Plumbing.PipingSystemType):
        out.append((t, 'pipe'))
    return out


def _rules_of(element_filter):
    """Flatten an ElementParameterFilter / LogicalAndFilter into its FilterRules (None if it has OR / other parts)."""
    rules = []
    if isinstance(element_filter, DB.ElementParameterFilter):
        rules.extend(list(element_filter.GetRules()))
        return rules
    if isinstance(element_filter, DB.LogicalAndFilter):
        for f in element_filter.GetFilters():
            sub = _rules_of(f)
            if sub is None:
                return None
            rules.extend(sub)
        return rules
    return None


def _system_type_of_filter(doc, pfe):
    """Id (int) of the system type a filter selects with 'System Type equals X', else None."""
    try:
        rules = _rules_of(pfe.GetElementFilter())
    except Exception:
        rules = None
    if not rules or len(rules) != 1:
        return None
    rule = rules[0]
    if not isinstance(rule, DB.FilterElementIdRule):
        return None
    if eid_int(rule.GetRuleParameter()) not in (int(DUCT_PARAM), int(PIPE_PARAM)):
        return None
    try:
        if not isinstance(rule.GetEvaluator(), DB.FilterNumericEquals):
            return None
    except Exception:
        return None
    return eid_int(rule.RuleValue)


def existing_system_filters(doc):
    """{system type id: ParameterFilterElement} for every 'System Type equals X' filter in the project."""
    found = {}
    for pfe in DB.FilteredElementCollector(doc).OfClass(DB.ParameterFilterElement):
        tid = _system_type_of_filter(doc, pfe)
        if tid is not None and tid not in found:
            found[tid] = pfe
    return found


def _filter_categories(doc, kind):
    from System.Collections.Generic import List
    param = DUCT_PARAM if kind == 'duct' else PIPE_PARAM
    keep = List[DB.ElementId]()
    for bic in (DUCT_FILTER_CATS if kind == 'duct' else PIPE_FILTER_CATS):
        cid = DB.ElementId(bic)
        one = List[DB.ElementId]()
        one.Add(cid)
        try:
            common = DB.ParameterFilterUtilities.GetFilterableParametersInCommon(doc, one)
            if any(eid_int(p) == int(param) for p in common):
                keep.Add(cid)
        except Exception:
            pass
    return keep


def filter_name(doc, type_name, prefix='', separator='_'):
    base = type_name if type_name.upper().startswith(prefix.upper()) else u'%s%s%s' % (prefix, separator, type_name)
    name, n = base, 2
    while not DB.ParameterFilterElement.IsNameUnique(doc, name):
        name = u'%s (%d)' % (base, n)
        n += 1
    return name


def create_system_filter(doc, system_type, kind, prefix='', separator='_'):
    cats = _filter_categories(doc, kind)
    if cats.Count == 0:
        return None
    param = DB.ElementId(DUCT_PARAM if kind == 'duct' else PIPE_PARAM)
    rule = DB.ParameterFilterRuleFactory.CreateEqualsRule(param, system_type.Id)
    return DB.ParameterFilterElement.Create(doc, filter_name(doc, name_of(system_type), prefix, separator),
                                           cats, DB.ElementParameterFilter(rule))


EXTRA_CATS = {'duct': [BIC.OST_FlexDuctCurves, BIC.OST_DuctTerminal], 'pipe': [BIC.OST_FlexPipeCurves]}


def _kept_type_ids(systems):
    keep = set()
    for s in systems:
        try:
            keep.add(eid_int(s.GetTypeId()))
        except Exception:
            pass
    return keep


def plan_system_filters(doc, systems, prefix=''):
    """What System Box has to do before hiding the other systems (read only):
    missing    - system types that have no 'System Type equals X' filter yet
    unprefixed - existing such filters whose name does not start with the prefix"""
    existing = existing_system_filters(doc)
    missing, unprefixed = [], []
    for st, kind in _all_system_types(doc):
        pfe = existing.get(eid_int(st.Id))
        if pfe is None:
            if eid_int(st.Id) not in _kept_type_ids(systems):
                missing.append((st, kind))
        elif prefix and not pfe.Name.upper().startswith(prefix.upper()):
            unprefixed.append(pfe)
    return {'missing': missing, 'unprefixed': unprefixed, 'existing': existing}


def _ensure_extra_categories(doc, pfe, kind):
    """Make sure a reused filter also covers flex ducts / air terminals (flex pipes for pipe filters)."""
    from System.Collections.Generic import List
    try:
        current = set(eid_int(c) for c in pfe.GetCategories())
        wanted = [c for c in _filter_categories(doc, kind)
                  if eid_int(c) in set(int(b) for b in EXTRA_CATS[kind]) and eid_int(c) not in current]
        if not wanted:
            return False
        cats = List[DB.ElementId]()
        for c in pfe.GetCategories():
            cats.Add(c)
        for c in wanted:
            cats.Add(c)
        pfe.SetCategories(cats)
        return True
    except Exception:
        return False


def _prefixed_name(doc, name, prefix, separator):
    base = name if name.upper().startswith(prefix.upper()) else u'%s%s%s' % (prefix, separator, name)
    new, n = base, 2
    while not DB.ParameterFilterElement.IsNameUnique(doc, new):
        new = u'%s (%d)' % (base, n)
        n += 1
    return new


def hide_other_systems(doc, view, systems, prefix='', separator='_', create_missing=True, rename=True):
    """In 'view', hide every system type except those of 'systems' with 'System Type equals X' filters.
    Existing filters with that rule are reused (whatever their name), get flex ducts / air terminals added if
    missing, and (rename=True) get the prefix added. Missing filters are created when create_missing=True."""
    keep = _kept_type_ids(systems)
    existing = existing_system_filters(doc)
    applied = set(eid_int(i) for i in view.GetFilters())
    report = {'reused': [], 'created': [], 'renamed': [], 'categories_added': [], 'hidden': 0, 'shown': 0}
    for st, kind in _all_system_types(doc):
        tid = eid_int(st.Id)
        pfe = existing.get(tid)
        if pfe is not None:
            if _ensure_extra_categories(doc, pfe, kind):
                report['categories_added'].append(pfe.Name)
            if rename and prefix and not pfe.Name.upper().startswith(prefix.upper()):
                old = pfe.Name
                try:
                    pfe.Name = _prefixed_name(doc, old, prefix, separator)
                    report['renamed'].append(u'%s -> %s' % (old, pfe.Name))
                except Exception:
                    pass
        if tid in keep:
            if pfe is not None and eid_int(pfe.Id) in applied:
                view.SetFilterVisibility(pfe.Id, True)
                report['shown'] += 1
            continue
        if pfe is None:
            if not create_missing:
                continue
            pfe = create_system_filter(doc, st, kind, prefix, separator)
            if pfe is None:
                continue
            report['created'].append(pfe.Name)
        else:
            report['reused'].append(pfe.Name)
        if eid_int(pfe.Id) not in applied:
            view.AddFilter(pfe.Id)
        view.SetFilterVisibility(pfe.Id, False)
        report['hidden'] += 1
    return report


# ---------------------------------------------------------------- context (architecture / structure) on or off
MEP_KEEP = set(int(b) for b in [
    BIC.OST_DuctCurves, BIC.OST_DuctFitting, BIC.OST_DuctAccessory, BIC.OST_DuctTerminal, BIC.OST_FlexDuctCurves,
    BIC.OST_DuctInsulations, BIC.OST_DuctLinings, BIC.OST_PlaceHolderDucts, BIC.OST_MechanicalEquipment,
    BIC.OST_PipeCurves, BIC.OST_PipeFitting, BIC.OST_PipeAccessory, BIC.OST_FlexPipeCurves, BIC.OST_PipeInsulations,
    BIC.OST_PlaceHolderPipes, BIC.OST_PlumbingFixtures, BIC.OST_Sprinklers, BIC.OST_RvtLinks])


def set_context_visibility(doc, view, show):
    """Show or hide every model category that is not duct / pipe / equipment (walls, floors, ceilings, columns,
    framing, doors, furniture...). Applies to linked models seen in this view too. Returns the number changed."""
    changed = 0
    for cat in doc.Settings.Categories:
        try:
            if cat.CategoryType != DB.CategoryType.Model or eid_int(cat.Id) in MEP_KEEP:
                continue
            if not view.CanCategoryBeHidden(cat.Id):
                continue
            if view.GetCategoryHidden(cat.Id) == (not show):
                continue
            view.SetCategoryHidden(cat.Id, not show)
            changed += 1
        except Exception:
            pass
    return changed
