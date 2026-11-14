# -*- coding: ascii -*-
"""Smart Tag - tag MEP elements in a view by rules, skipping tagged ones and avoiding overlaps.

Rule per category key (see CATEGORIES):
    {"key": "ducts", "tag_type_id": 12345, "orientation": "auto" | "horizontal" | "vertical"}
Options:
    skip_tagged=True, leader=False, avoid_overlap=True, min_length_mm=1000, offset_mm=3 (paper mm),
    ids=None (only these elements, else everything visible in the view)
The caller owns the transaction.
"""
from Autodesk.Revit import DB

from emperor_mep.common import eid_int, name_of, type_label, to_uv

BIC = DB.BuiltInCategory
# key: (label, element category, tag category, is_curve)
CATEGORIES = [
    ('ducts', 'Ducts', BIC.OST_DuctCurves, BIC.OST_DuctTags, True),
    ('flex_ducts', 'Flex Ducts', BIC.OST_FlexDuctCurves, BIC.OST_FlexDuctTags, True),
    ('pipes', 'Pipes', BIC.OST_PipeCurves, BIC.OST_PipeTags, True),
    ('flex_pipes', 'Flex Pipes', BIC.OST_FlexPipeCurves, BIC.OST_FlexPipeTags, True),
    ('terminals', 'Air Terminals', BIC.OST_DuctTerminal, BIC.OST_DuctTerminalTags, False),
    ('equipment', 'Mechanical Equipment', BIC.OST_MechanicalEquipment, BIC.OST_MechanicalEquipmentTags, False),
    ('duct_accessories', 'Duct Accessories', BIC.OST_DuctAccessory, BIC.OST_DuctAccessoryTags, False),
    ('pipe_accessories', 'Pipe Accessories', BIC.OST_PipeAccessory, BIC.OST_PipeAccessoryTags, False),
    ('plumbing_fixtures', 'Plumbing Fixtures', BIC.OST_PlumbingFixtures, BIC.OST_PlumbingFixtureTags, False),
]
CATEGORY_INDEX = dict((c[0], c) for c in CATEGORIES)


def tag_types(doc, key):
    c = CATEGORY_INDEX[key]
    syms = list(DB.FilteredElementCollector(doc).OfCategory(c[3]).WhereElementIsElementType())
    return sorted(syms, key=lambda s: type_label(s).lower())


def _tagged_ids(doc, view):
    """Ids already tagged in the view, and the 2D boxes of every annotation that new tags must not cover."""
    done = set()
    boxes = []
    for t in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag):
        try:
            for i in t.GetTaggedLocalElementIds():      # Revit 2022+
                done.add(eid_int(i))
        except Exception:
            try:
                done.add(eid_int(t.TaggedLocalElementId))
            except Exception:
                pass
        b = _box2d(t, view)
        if b is not None:
            boxes.append(b)
    # text notes and room / space / area tags count as obstacles too
    for cls in (DB.TextNote, DB.SpatialElementTag):
        try:
            for el in DB.FilteredElementCollector(doc, view.Id).OfClass(cls):
                b = _box2d(el, view)
                if b is not None:
                    boxes.append(b)
        except Exception:
            pass
    return done, boxes


def _box2d(elem, view):
    try:
        bb = elem.get_BoundingBox(view)
        if bb is None:
            return None
        right, up = view.RightDirection, view.UpDirection
        pts = [bb.Min, bb.Max, DB.XYZ(bb.Min.X, bb.Max.Y, bb.Min.Z), DB.XYZ(bb.Max.X, bb.Min.Y, bb.Min.Z)]
        try:
            pts = [bb.Transform.OfPoint(p) for p in pts]
        except Exception:
            pass
        us = [p.DotProduct(right) for p in pts]
        vs = [p.DotProduct(up) for p in pts]
        return (min(us), min(vs), max(us), max(vs))
    except Exception:
        return None


OBSTACLE_CATS = [BIC.OST_DuctCurves, BIC.OST_FlexDuctCurves, BIC.OST_DuctFitting, BIC.OST_DuctAccessory,
                 BIC.OST_DuctTerminal, BIC.OST_MechanicalEquipment, BIC.OST_PipeCurves, BIC.OST_FlexPipeCurves,
                 BIC.OST_PipeFitting, BIC.OST_PipeAccessory, BIC.OST_PlumbingFixtures]


# damper (V.D) tags may sit over ducts, duct fittings and flex ducts, like hand-placed ones
DAMPER_FREE = set(int(b) for b in (BIC.OST_DuctCurves, BIC.OST_DuctFitting, BIC.OST_FlexDuctCurves))


class Obstacles(object):
    """Model elements drawn in the view that a tag must not cover.
    Straight ducts / pipes are kept as thick segments (their real width and direction), everything else
    as its 2D box. A grid keeps the look-ups fast in big views."""

    def __init__(self, doc, view, cell_ft=6.0):
        self.cell = cell_ft
        self.grid = {}
        right, up = view.RightDirection, view.UpDirection
        for bic in OBSTACLE_CATS:
            try:
                elems = DB.FilteredElementCollector(doc, view.Id).OfCategory(bic).WhereElementIsNotElementType()
            except Exception:
                continue
            for e in elems:
                item = None
                if isinstance(e, DB.MEPCurve) and bic in (BIC.OST_DuctCurves, BIC.OST_PipeCurves):
                    try:
                        c = e.Location.Curve
                        a, b = c.GetEndPoint(0), c.GetEndPoint(1)
                        hw = _drawn_width_ft(e, view) / 2.0
                        item = ('seg', (a.DotProduct(right), a.DotProduct(up), b.DotProduct(right), b.DotProduct(up), hw),
                                eid_int(e.Id), int(bic))
                    except Exception:
                        item = None
                if item is None:
                    bx = _drawn_box(e, view) if bic in (BIC.OST_DuctTerminal, BIC.OST_DuctAccessory,
                                                         BIC.OST_PipeAccessory) else _box2d(e, view)
                    if bx is None:
                        continue
                    item = ('box', bx, eid_int(e.Id), int(bic))
                self._add(item)

    def _rect(self, item):
        kind, g = item[0], item[1]
        if kind == 'box':
            return g
        hw = g[4]
        return (min(g[0], g[2]) - hw, min(g[1], g[3]) - hw, max(g[0], g[2]) + hw, max(g[1], g[3]) + hw)

    def _cells(self, r):
        for i in range(int(r[0] // self.cell), int(r[2] // self.cell) + 1):
            for j in range(int(r[1] // self.cell), int(r[3] // self.cell) + 1):
                yield (i, j)

    def _add(self, item):
        r = self._rect(item)
        if (r[2] - r[0]) / self.cell * (r[3] - r[1]) / self.cell > 4000:   # huge diagonal box: index loosely
            r = (r[0], r[1], r[0], r[1])
        for key in self._cells(r):
            self.grid.setdefault(key, []).append(item)

    def hits(self, box, ignore_id=None, ignore_segments=False, ignore_cats=None):
        seen = set()
        for key in self._cells(box):
            for item in self.grid.get(key, ()):
                if id(item) in seen:
                    continue
                seen.add(id(item))
                if ignore_id is not None and item[2] == ignore_id:
                    continue
                if ignore_segments and item[0] == 'seg':
                    continue                      # damper tags may sit inside the duct body
                if ignore_cats and item[3] in ignore_cats:
                    continue
                if item[0] == 'box':
                    b = item[1]
                    if box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3]:
                        return True
                elif _seg_rect_dist(item[1], box) < item[1][4]:
                    return True
        return False


def _seg_rect_dist(seg, r):
    """Distance between segment (ua, va, ub, vb, _) and the axis-aligned rectangle r (0 if they cross)."""
    ax, ay, bx, by = seg[0], seg[1], seg[2], seg[3]
    if _seg_hits_rect(ax, ay, bx, by, r):
        return 0.0
    best = min(_pt_rect(ax, ay, r), _pt_rect(bx, by, r))
    for cx, cy in ((r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])):
        best = min(best, _pt_seg(cx, cy, ax, ay, bx, by))
    return best


def _pt_rect(x, y, r):
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return (dx * dx + dy * dy) ** 0.5


def _pt_seg(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    qx, qy = ax + t * vx - px, ay + t * vy - py
    return (qx * qx + qy * qy) ** 0.5


def _seg_hits_rect(ax, ay, bx, by, r):
    if r[0] <= ax <= r[2] and r[1] <= ay <= r[3]:
        return True
    if r[0] <= bx <= r[2] and r[1] <= by <= r[3]:
        return True
    edges = [(r[0], r[1], r[2], r[1]), (r[2], r[1], r[2], r[3]), (r[2], r[3], r[0], r[3]), (r[0], r[3], r[0], r[1])]
    for ex, ey, fx, fy in edges:
        if _segs_cross(ax, ay, bx, by, ex, ey, fx, fy):
            return True
    return False


def _segs_cross(ax, ay, bx, by, cx, cy, dx, dy):
    def orient(px, py, qx, qy, rx, ry):
        v = (qx - px) * (ry - py) - (qy - py) * (rx - px)
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)
    o1, o2 = orient(ax, ay, bx, by, cx, cy), orient(ax, ay, bx, by, dx, dy)
    o3, o4 = orient(cx, cy, dx, dy, ax, ay), orient(cx, cy, dx, dy, bx, by)
    return o1 != o2 and o3 != o4


def _drawn_box(e, view):
    """2D box of what is actually DRAWN for the element in this view (visible lines / edges only).
    Family bounding boxes are often much bigger than the plan symbol (hidden 3D parts, connector
    lengths), which pushed tags far away. Falls back to the bounding box."""
    right, up = view.RightDirection, view.UpDirection
    us, vs = [], []

    def add_pts(pts):
        for p in pts:
            us.append(p.DotProduct(right))
            vs.append(p.DotProduct(up))

    def walk(geom, depth=0):
        if geom is None or depth > 4:
            return
        for g in geom:
            try:
                if g.Visibility != DB.Visibility.Visible:
                    continue
            except Exception:
                pass
            if isinstance(g, DB.GeometryInstance):
                walk(g.GetInstanceGeometry(), depth + 1)
            elif isinstance(g, DB.Curve):
                try:
                    add_pts(g.Tessellate())
                except Exception:
                    pass
            elif isinstance(g, DB.Solid):
                try:
                    for edge in g.Edges:
                        add_pts(edge.AsCurve().Tessellate())
                except Exception:
                    pass
            elif isinstance(g, DB.PolyLine):
                try:
                    add_pts(g.GetCoordinates())
                except Exception:
                    pass
    try:
        opts = DB.Options()
        opts.View = view
        opts.IncludeNonVisibleObjects = False
        walk(e.get_Geometry(opts))
    except Exception:
        pass
    if us:
        return (min(us), min(vs), max(us), max(vs))
    return _box2d(e, view)


def _overlaps(a, boxes, gap=0.0):
    for b in boxes:
        if a[0] - gap < b[2] and b[0] - gap < a[2] and a[1] - gap < b[3] and b[1] - gap < a[3]:
            return True
    return False


def _crop_uv(view):
    """Crop region in view coordinates (u, v), or None when the crop box is off."""
    try:
        if not view.CropBoxActive:
            return None
        cb = view.CropBox
        tr = cb.Transform
        pts = [tr.OfPoint(cb.Min), tr.OfPoint(cb.Max)]
        right, up = view.RightDirection, view.UpDirection
        us = [p.DotProduct(right) for p in pts]
        vs = [p.DotProduct(up) for p in pts]
        return (min(us), min(vs), max(us), max(vs))
    except Exception:
        return None


def _drawn_width_ft(e, view):
    """Width of a duct / pipe as drawn in the view (plan: the horizontal size)."""
    best = 0.0
    try:
        conns = list(e.ConnectorManager.Connectors)
    except Exception:
        conns = []
    for c in conns:
        try:
            if c.Shape == DB.ConnectorProfileType.Round:
                best = max(best, c.Radius * 2.0)
            else:
                best = max(best, c.Width)
        except Exception:
            pass
    return best


def _candidates(e, view, is_curve, key=None):
    """[(anchor point, normal direction, natural orientation, half size of the element along normal)] best first.

    ducts / pipes   : 5 spots along the run, both sides
    air terminals   : the side the terminal faces first (in front of it, not behind)
    duct accessories: above or below the damper only"""
    right, up = view.RightDirection, view.UpDirection
    out = []
    if is_curve:
        try:
            curve = e.Location.Curve
        except Exception:
            return out
        p0, p1 = curve.GetEndPoint(0), curve.GetEndPoint(1)
        d = p1 - p0
        du, dv = d.DotProduct(right), d.DotProduct(up)
        horizontal = abs(du) >= abs(dv)
        normal = up if horizontal else right
        half = _drawn_width_ft(e, view) / 2.0
        for t in (0.5, 0.3, 0.7, 0.15, 0.85):
            try:
                p = curve.Evaluate(t, True)
            except Exception:
                continue
            for side in (1.0, -1.0):
                out.append((p, normal.Multiply(side), 'horizontal' if horizontal else 'vertical', half))
        return out
    b = _drawn_box(e, view)
    p = None
    if b is not None:      # centre of the element as drawn in this view
        cu, cv = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        try:
            depth = e.Location.Point.DotProduct(view.ViewDirection)
        except Exception:
            depth = 0.0
        p = right.Multiply(cu) + up.Multiply(cv) + view.ViewDirection.Multiply(depth)
    if p is None:
        try:
            p = e.Location.Point
        except Exception:
            return out
    if key == 'duct_accessories':
        dirs = [up.Negate(), up, right, right.Negate()]      # below, above, then the sides
    else:
        dirs = [up, right, up.Negate(), right.Negate()]
        if key == 'terminals':
            front = _facing_axis(e, view)
            if front is not None:
                back = front.Negate()
                rest = [v for v in (up.Negate(), up, right, right.Negate())
                        if not v.IsAlmostEqualTo(front) and not v.IsAlmostEqualTo(back)]
                dirs = [front] + rest + [back]          # in front, then below / above, behind last
    for vec in dirs:
        half = 0.0
        if b is not None:
            half = ((b[3] - b[1]) if abs(vec.DotProduct(up)) > 0.7 else (b[2] - b[0])) / 2.0
        out.append((p, vec, 'horizontal', half))
    return out


def _facing_axis(e, view):
    """The view axis (up / down / right / left) an air terminal faces, or None (e.g. ceiling diffusers in plan)."""
    try:
        f = e.FacingOrientation
    except Exception:
        return None
    right, up = view.RightDirection, view.UpDirection
    fu, fv = f.DotProduct(right), f.DotProduct(up)
    if (fu * fu + fv * fv) ** 0.5 < 0.5:
        return None
    if abs(fu) >= abs(fv):
        return right if fu > 0 else right.Negate()
    return up if fv > 0 else up.Negate()


def _orientation(choice, natural, always_horizontal=False):
    if always_horizontal:
        return DB.TagOrientation.Horizontal
    pick = natural if choice in (None, '', 'auto') else choice
    return DB.TagOrientation.Vertical if pick == 'vertical' else DB.TagOrientation.Horizontal


def _move_tag(tag, view, du, dv):
    right, up = view.RightDirection, view.UpDirection
    tag.TagHeadPosition = tag.TagHeadPosition + right.Multiply(du) + up.Multiply(dv)


def _set_elbow(tag, ref, point):
    try:
        tag.SetLeaderElbow(ref, point)          # Revit 2022+
        return True
    except Exception:
        pass
    try:
        tag.LeaderElbow = point                 # older Revit
        return True
    except Exception:
        return False


def _place_clear(tag, view, anchor, normal, half_width, gap_ft, leader=False, ref=None, horizontal_text=True):
    """Put the tag beside the element on the 'normal' side, its edge gap_ft beyond the element's edge.
    With a leader the tag also moves sideways so the leader leaves the LEFT or RIGHT side of the text
    (an elbow at the text's mid height), then goes to the element. Returns the tag's 2D box."""
    right, up = view.RightDirection, view.UpDirection
    b = _box2d(tag, view)
    if b is None:
        return None
    w, h = b[2] - b[0], b[3] - b[1]
    cu, cv = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    nu, nv = normal.DotProduct(right), normal.DotProduct(up)
    au, av = anchor.DotProduct(right), anchor.DotProduct(up)
    along_normal_half = (h if abs(nv) > 0.7 else w) / 2.0
    dist = half_width + gap_ft + along_normal_half
    tu, tv = au + nu * dist, av + nv * dist
    side = 1.0
    if leader and abs(nv) > 0.7:
        # tag above / below: shift it sideways so a side of the text faces the element
        tu = au + side * (w / 2.0 + 2.0 * gap_ft)
        tv = av + nv * (half_width + 2.0 * gap_ft + h / 2.0)
    _move_tag(tag, view, tu - cu, tv - cv)
    box = (tu - w / 2.0, tv - h / 2.0, tu + w / 2.0, tv + h / 2.0)
    if leader and ref is not None and horizontal_text:
        # the text side that faces the element, at the text's mid height
        near_u = tu - w / 2.0 if au < tu else tu + w / 2.0
        step = gap_ft if au < tu else -gap_ft
        depth = anchor.DotProduct(view.ViewDirection)
        elbow = right.Multiply(near_u - step) + up.Multiply(tv) + view.ViewDirection.Multiply(depth)
        _set_elbow(tag, ref, elbow)
    return box


def _damper_frame(e, view):
    """Damper symbol in view coordinates: centre (cu, cv), flow axis ('u' or 'v'), half length along the
    flow, the two ends of the blade line (across the duct) and which end carries the handle (+1 / -1)."""
    b = _drawn_box(e, view)
    if b is None:
        return None
    right, up = view.RightDirection, view.UpDirection
    # flow axis from the two connectors; fall back to the short side of the drawn symbol
    pts = []
    try:
        for c in e.MEPModel.ConnectorManager.Connectors:
            pts.append(c.Origin)
    except Exception:
        pass
    if len(pts) >= 2:
        du = abs(pts[0].DotProduct(right) - pts[1].DotProduct(right))
        dv = abs(pts[0].DotProduct(up) - pts[1].DotProduct(up))
        flow = 'u' if du >= dv else 'v'
        mu = sum(p.DotProduct(right) for p in pts[:2]) / 2.0
        mv = sum(p.DotProduct(up) for p in pts[:2]) / 2.0
    else:
        flow = 'u' if (b[2] - b[0]) < (b[3] - b[1]) else 'v'
        mu, mv = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    if flow == 'v':       # duct runs up / down, blade line across = left / right
        lo, hi, centre = b[0], b[2], mu
        half_flow = (b[3] - b[1]) / 2.0
    else:
        lo, hi, centre = b[1], b[3], mv
        half_flow = (b[2] - b[0]) / 2.0
    # the handle sticks out further from the duct centre line
    handle = 1 if (hi - centre) >= (centre - lo) * 0.98 else -1
    return {'cu': (b[0] + b[2]) / 2.0, 'cv': (b[1] + b[3]) / 2.0, 'flow': flow, 'half_flow': half_flow,
            'lo': lo, 'hi': hi, 'handle': handle}


def _damper_spots(fr, w, h, gap_ft):
    """Text positions for a damper tag, best first: [(tu, tv, elbow_u, elbow_v, end_u, end_v)].
    The text sits just below / above the blade (beside it when the duct runs left-right), near one end
    of the blade, and the leader leaves the side of the text facing that end and goes to it."""
    out = []
    ends = [fr['handle'], -fr['handle']]
    for sign in ends:
        end = fr['hi'] if sign > 0 else fr['lo']
        for s in (-1.0, 1.0):                       # below first, then above (left, then right)
            if fr['flow'] == 'v':
                tv = fr['cv'] + s * (fr['half_flow'] + 2.0 * gap_ft + h / 2.0)
                tu = end - sign * (0.25 * w + w / 2.0)
                side_u = tu + sign * w / 2.0
                out.append((tu, tv, side_u + sign * gap_ft, tv, end, fr['cv']))
            else:
                tu = fr['cu'] + s * (fr['half_flow'] + 2.0 * gap_ft + w / 2.0)
                tv = end - sign * (0.25 * h + h / 2.0)
                side_u = tu - s * w / 2.0
                out.append((tu, tv, side_u - s * gap_ft, tv, fr['cu'], end))
    return out


def _set_leader_end(tag, ref, point):
    try:
        tag.LeaderEndCondition = DB.LeaderEndCondition.Free
    except Exception:
        pass
    try:
        tag.SetLeaderEnd(ref, point)             # Revit 2022+
        return True
    except Exception:
        pass
    try:
        tag.LeaderEnd = point
        return True
    except Exception:
        return False


def _tag_damper(doc, view, e, ref, type_id, gap_ft, boxes, obstacles, eid, place_anyway):
    """Damper (V.D) tag with a short leader from the side of the text to the end of the blade.
    Returns (tag, box, kept_without_free_spot) or (None, None, False)."""
    fr = _damper_frame(e, view)
    if fr is None:
        return None, None, False
    right, up, vd = view.RightDirection, view.UpDirection, view.ViewDirection
    try:
        depth = e.Location.Point.DotProduct(vd)
    except Exception:
        depth = 0.0

    def P(u_, v_):
        return right.Multiply(u_) + up.Multiply(v_) + vd.Multiply(depth)
    tag = DB.IndependentTag.Create(doc, type_id, view.Id, ref, False, DB.TagOrientation.Horizontal,
                                   P(fr['cu'], fr['cv']))
    doc.Regenerate()
    tb = _box2d(tag, view)                       # text only (no leader yet)
    if tb is None:
        return tag, None, False
    w, h = tb[2] - tb[0], tb[3] - tb[1]
    head = tag.TagHeadPosition
    off_u = head.DotProduct(right) - (tb[0] + tb[2]) / 2.0
    off_v = head.DotProduct(up) - (tb[1] + tb[3]) / 2.0
    spots = _damper_spots(fr, w, h, gap_ft)
    chosen = None
    for spot in spots:
        tu, tv = spot[0], spot[1]
        box = (tu - w / 2.0, tv - h / 2.0, tu + w / 2.0, tv + h / 2.0)
        if obstacles is None:
            chosen = (spot, box)
            break
        if not _overlaps(box, boxes) and not obstacles.hits(box, eid, ignore_segments=True, ignore_cats=DAMPER_FREE):
            chosen = (spot, box)
            break
    kept = False
    if chosen is None:
        if not place_anyway:
            doc.Delete(tag.Id)
            return None, None, False
        kept = True
        tu, tv = spots[0][0], spots[0][1]
        chosen = (spots[0], (tu - w / 2.0, tv - h / 2.0, tu + w / 2.0, tv + h / 2.0))
    spot, box = chosen
    tu, tv, eu, ev, endu, endv = spot
    tag.TagHeadPosition = P(tu + off_u, tv + off_v)
    try:
        tag.HasLeader = True
        doc.Regenerate()
        _set_leader_end(tag, ref, P(endu, endv))
        _set_elbow(tag, ref, P(eu, ev))
    except Exception:
        pass
    return tag, box, kept


MIN_FLOW_FT3S = 0.5 / 28.316846592      # 0.5 L/s - anything smaller is shown as 0 on the tag


def _zero_flow(e):
    """True when the duct shows no airflow: no calculated value, or less than 0.5 L/s."""
    try:
        p = e.get_Parameter(DB.BuiltInParameter.RBS_DUCT_FLOW_PARAM)
        if p is None or not p.HasValue:
            return True
        return abs(p.AsDouble()) < MIN_FLOW_FT3S
    except Exception:
        return False


def run(doc, view, rules, skip_tagged=True, leader=False, avoid_overlap=True,
        min_length_mm=1000.0, offset_mm=2.0, ids=None, progress=None, skip_zero_flow=True,
        place_anyway=False, always_horizontal=False, damper_leader=False, use_learned=True):
    """Place tags. Returns a report dict.
    use_learned: try the spots learned from the user first (emperor_mep.tag_learn), then the built-in ones.
    Every placed tag is remembered so the user can move it and press "Learn from my changes".
    damper_leader (old, off): V.D tags near one blade end with a short leader.
    Ducts / pipes: the tag goes beside the element (its edge offset_mm paper mm from the duct edge), trying
    5 spots along it on both sides. With avoid_overlap a tag that finds no free spot is NOT placed unless
    place_anyway=True (then it is counted in overlap_kept)."""
    report = {'tagged': 0, 'skipped_tagged': 0, 'skipped_short': 0, 'skipped_outside': 0, 'skipped_zero_flow': 0,
              'no_free_spot': 0, 'overlap_kept': 0, 'failed': 0, 'errors': [], 'by_category': {}, 'new_tag_ids': []}
    scale = max(1, int(getattr(view, 'Scale', 100) or 100))
    gap_ft = (float(offset_mm) * scale) / 304.8
    done, boxes = _tagged_ids(doc, view)
    obstacles = Obstacles(doc, view) if avoid_overlap else None
    crop = _crop_uv(view)
    right, up = view.RightDirection, view.UpDirection
    wanted_ids = set(eid_int(i) for i in ids) if ids else None
    from emperor_mep import tag_learn
    placed = []
    report['learned_used'] = 0

    for rule in rules:
        key = rule.get('key')
        if key not in CATEGORY_INDEX:
            continue
        label, cat, _tagcat, is_curve = CATEGORY_INDEX[key][1:]
        type_id = rule.get('tag_type_id')
        if type_id is None:
            types = tag_types(doc, key)
            if not types:
                report['errors'].append(u'No tag family loaded for %s.' % label)
                continue
            type_id = types[0].Id
        elif not isinstance(type_id, DB.ElementId):
            from emperor_mep.common import make_eid
            type_id = make_eid(type_id)
        flow_check = skip_zero_flow and key in ('ducts', 'flex_ducts')
        elems = list(DB.FilteredElementCollector(doc, view.Id).OfCategory(cat).WhereElementIsNotElementType())
        for n, e in enumerate(elems):
            if progress is not None and n % 25 == 0:
                try:
                    progress(u'%s %d / %d' % (label, n, len(elems)))
                except Exception:
                    pass
            eid = eid_int(e.Id)
            if wanted_ids is not None and eid not in wanted_ids:
                continue
            if skip_tagged and eid in done:
                report['skipped_tagged'] += 1
                continue
            if flow_check and _zero_flow(e):
                report['skipped_zero_flow'] += 1
                continue
            if is_curve and min_length_mm:
                try:
                    if e.Location.Curve.Length * 304.8 < float(min_length_mm):
                        report['skipped_short'] += 1
                        continue
                except Exception:
                    pass
            cands = _candidates(e, view, is_curve, key)
            if crop is not None:
                cands = [c for c in cands if crop[0] <= c[0].DotProduct(right) <= crop[2]
                         and crop[1] <= c[0].DotProduct(up) <= crop[3]]
                if not cands:
                    report['skipped_outside'] += 1
                    continue
            if not cands:
                report['failed'] += 1
                continue
            tag = None
            if damper_leader and key == 'duct_accessories':
                try:
                    tag, box, kept = _tag_damper(doc, view, e, DB.Reference(e), type_id, gap_ft, boxes,
                                                 obstacles, eid, place_anyway or not avoid_overlap)
                    if tag is None:
                        report['no_free_spot'] += 1
                        continue
                    if kept:
                        report['overlap_kept'] += 1
                    if box is not None:
                        boxes.append(box)
                    done.add(eid)
                    report['tagged'] += 1
                    report['by_category'][label] = report['by_category'].get(label, 0) + 1
                    report['new_tag_ids'].append(eid_int(tag.Id))
                    placed.append((tag, e, key))
                except Exception as ex:
                    report['failed'] += 1
                    if tag is not None:
                        try:
                            doc.Delete(tag.Id)
                        except Exception:
                            pass
                    if len(report['errors']) < 12:
                        report['errors'].append(u'%s %d: %s' % (label, eid, ex))
                continue
            try:
                ref = DB.Reference(e)
                anchor, normal, natural, half = cands[0]
                orient = _orientation(rule.get('orientation'), natural, always_horizontal)
                horizontal_text = orient == DB.TagOrientation.Horizontal
                tag = DB.IndependentTag.Create(doc, type_id, view.Id, ref, bool(leader), orient, anchor)
                doc.Regenerate()
                free_box = None
                last_box = None
                learned_ok = False
                if use_learned:
                    fr = tag_learn.frame(e, view, key)
                    spots = tag_learn.spots_for(fr['sit']) if fr is not None else []
                    ts = (0.5, 0.3, 0.7, 0.15, 0.85) if is_curve else (0.5,)
                    for spot in spots:
                        for t_ in ts:
                            try:
                                tag_learn.apply_spot(doc, view, tag, e, ref, fr, spot, t_, always_horizontal)
                                doc.Regenerate()
                            except Exception:
                                continue
                            b = _box2d(tag, view)
                            if b is None:
                                continue
                            if crop is not None and not (crop[0] <= (b[0] + b[2]) / 2.0 <= crop[2]
                                                         and crop[1] <= (b[1] + b[3]) / 2.0 <= crop[3]):
                                continue
                            if not avoid_overlap or (not _overlaps(b, boxes) and not obstacles.hits(
                                    b, eid, ignore_segments=(key == 'duct_accessories'),
                                    ignore_cats=DAMPER_FREE if key == 'duct_accessories' else None)):
                                free_box, learned_ok = b, True
                                break
                        if learned_ok:
                            break
                    if learned_ok:
                        report['learned_used'] += 1
                    elif spots:
                        try:                       # back to the built-in behaviour
                            tag.HasLeader = bool(leader)
                            tag.TagOrientation = orient
                        except Exception:
                            pass
                for anchor, normal, natural, half in ([] if learned_ok else (cands if avoid_overlap else cands[:1])):
                    try:
                        tag.TagHeadPosition = anchor
                        doc.Regenerate()
                    except Exception:
                        pass
                    if not always_horizontal and rule.get('orientation') in (None, '', 'auto'):
                        try:
                            tag.TagOrientation = _orientation(None, natural)
                            horizontal_text = tag.TagOrientation == DB.TagOrientation.Horizontal
                            doc.Regenerate()
                        except Exception:
                            pass
                    last_box = _place_clear(tag, view, anchor, normal, half, gap_ft, bool(leader), ref, horizontal_text)
                    if not avoid_overlap:
                        free_box = last_box
                        break
                    doc.Regenerate()
                    b = _box2d(tag, view) or last_box
                    if b is not None and not _overlaps(b, boxes) and \
                            not obstacles.hits(b, eid, ignore_segments=(key == 'duct_accessories'),
                                               ignore_cats=DAMPER_FREE if key == 'duct_accessories' else None):
                        free_box = b
                        break
                if free_box is None and avoid_overlap and not learned_ok:
                    if place_anyway:
                        report['overlap_kept'] += 1
                        free_box = _box2d(tag, view) or last_box
                    else:
                        doc.Delete(tag.Id)
                        tag = None
                        report['no_free_spot'] += 1
                        continue
                if free_box is not None:
                    boxes.append(free_box)
                placed.append((tag, e, key))
                done.add(eid)
                report['tagged'] += 1
                report['by_category'][label] = report['by_category'].get(label, 0) + 1
                report['new_tag_ids'].append(eid_int(tag.Id))
            except Exception as ex:
                report['failed'] += 1
                if tag is not None:
                    try:
                        doc.Delete(tag.Id)
                    except Exception:
                        pass
                if len(report['errors']) < 12:
                    report['errors'].append(u'%s %d: %s' % (label, eid, ex))
    try:
        tag_learn.remember(doc, view, placed)
    except Exception:
        pass
    return report


def remove_tags(doc, view, keys):
    """Delete the tags of the given category keys in the view. Returns the count."""
    tag_cats = set(int(CATEGORY_INDEX[k][3]) for k in keys if k in CATEGORY_INDEX)
    ids = []
    for t in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag):
        try:
            if t.Category is not None and eid_int(t.Category.Id) in tag_cats:
                ids.append(t.Id)
        except Exception:
            pass
    for i in ids:
        try:
            doc.Delete(i)
        except Exception:
            pass
    return len(ids)


def describe(report):
    lines = [u'Tagged: %d' % report['tagged']]
    if report.get('learned_used'):
        lines.append(u'  on a spot learned from you: %d' % report['learned_used'])
    for label, n in sorted(report['by_category'].items()):
        if n:
            lines.append(u'  %s: %d' % (label, n))
    lines.append(u'Skipped - already tagged: %d, too short: %d, 0 L/s: %d, outside the crop: %d' % (
        report['skipped_tagged'], report['skipped_short'], report.get('skipped_zero_flow', 0), report['skipped_outside']))
    if report.get('no_free_spot'):
        lines.append(u'Not tagged - no free spot without overlapping: %d (tag those by hand, or tick "Place even '
                     u'without a free spot")' % report['no_free_spot'])
    if report['overlap_kept']:
        lines.append(u'Placed although no free spot was found: %d (check them)' % report['overlap_kept'])
    if report['failed']:
        lines.append(u'Failed: %d' % report['failed'])
    if report['errors']:
        lines.append(u'')
        lines.extend(u'  ' + x for x in report['errors'][:12])
    return u'\n'.join(lines)
