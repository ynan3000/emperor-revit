# -*- coding: ascii -*-
"""Smart Tag - learn tag spots from the user.

How it works
  1. Every tag Smart Tag places is remembered (smart_tag_placed.json): which element, the "situation"
     and where the tag head sits relative to the element, in PAPER mm (scale independent).
  2. The user drags the tags he does not like (or adds / removes a leader, rotates them).
  3. learn() compares each remembered tag with where it is now. A moved tag is a strong vote for the
     new spot, an untouched one a small vote for the spot it has. Tags placed by hand in the view can
     vote too. The votes are kept per situation in smart_tag_learned.json (on this PC, all projects).
  4. Next runs try the learned spots first (most votes first), then the built-in ones.

Situation = category + how the element sits in the view:
  ducts / pipes     : 'ducts|h' / 'ducts|v'  (run left-right or up-down). Spot = side (+1 above / right,
                      -1 below / left) + gap from the duct EDGE in paper mm.
  duct accessories  : 'duct_accessories|v' / '|u' (the duct runs up-down / left-right). Frame x points
                      across the duct towards the HANDLE side, y along the duct.
  air terminals     : 'terminals|side' (faces left / right / up / down in the view: x = the side it faces)
                      or 'terminals|plan' (ceiling diffusers: view axes).
  others            : the category key, view axes.
"""
from Autodesk.Revit import DB

from emperor_mep.common import eid_int, load_json, save_json, project_key

PLACED = 'smart_tag_placed.json'
LEARNED = 'smart_tag_learned.json'
MERGE_MM = 1.5          # spots closer than this (paper mm) are the same spot
MOVED_MM = 0.7          # a tag moved more than this counts as "moved by the user"
W_MOVED, W_KEPT, W_HAND = 3.0, 1.0, 2.0
MAX_SPOTS = 8


# ---------------------------------------------------------------- frames
def _uv(p, view):
    return p.DotProduct(view.RightDirection), p.DotProduct(view.UpDirection)


def _xyz(view, u, v, depth):
    return (view.RightDirection.Multiply(u) + view.UpDirection.Multiply(v)
            + view.ViewDirection.Multiply(depth))


def _k(view):
    """feet -> paper mm"""
    scale = max(1, int(getattr(view, 'Scale', 100) or 100))
    return 304.8 / scale


def frame(e, view, key):
    """Element frame in view coordinates, or None.
    curves : {'curve': True, 'sit', 'a': (u, v) start, 'd': unit dir, 'n': unit normal axis, 'half': ft}
    others : {'curve': False, 'sit', 'c': (u, v), 'x': unit, 'y': unit}"""
    from emperor_mep import tagging as TG
    try:
        depth = e.Location.Point.DotProduct(view.ViewDirection)
    except Exception:
        depth = None
    is_curve = TG.CATEGORY_INDEX[key][4] if key in TG.CATEGORY_INDEX else False
    if is_curve:
        try:
            c = e.Location.Curve
        except Exception:
            return None
        a, b = _uv(c.GetEndPoint(0), view), _uv(c.GetEndPoint(1), view)
        du, dv = b[0] - a[0], b[1] - a[1]
        L = (du * du + dv * dv) ** 0.5
        if L < 1e-9:
            return None
        horizontal = abs(du) >= abs(dv)
        nx, ny = -dv / L, du / L                     # true perpendicular, pointing up / right
        if (ny if horizontal else nx) < 0:
            nx, ny = -nx, -ny
        return {'curve': True, 'sit': key + ('|h' if horizontal else '|v'), 'a': a, 'b': b,
                'd': (du / L, dv / L), 'n': (nx, ny),
                'half': TG._drawn_width_ft(e, view) / 2.0,
                'depth': c.GetEndPoint(0).DotProduct(view.ViewDirection)}
    if key == 'duct_accessories':
        fr = TG._damper_frame(e, view)
        if fr is None:
            return None
        h = float(fr['handle'])
        if fr['flow'] == 'v':
            x, y, sit = (h, 0.0), (0.0, 1.0), key + '|v'
        else:
            x, y, sit = (0.0, h), (1.0, 0.0), key + '|u'
        return {'curve': False, 'sit': sit, 'c': (fr['cu'], fr['cv']), 'x': x, 'y': y, 'depth': depth}
    b = TG._drawn_box(e, view)
    if b is None:
        return None
    c = ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
    if key == 'terminals':
        f = TG._facing_axis(e, view)
        if f is not None:
            fx, fy = f.DotProduct(view.RightDirection), f.DotProduct(view.UpDirection)
            return {'curve': False, 'sit': key + '|side', 'c': c, 'x': (fx, fy), 'y': (-fy, fx), 'depth': depth}
        return {'curve': False, 'sit': key + '|plan', 'c': c, 'x': (1.0, 0.0), 'y': (0.0, 1.0), 'depth': depth}
    return {'curve': False, 'sit': key, 'c': c, 'x': (1.0, 0.0), 'y': (0.0, 1.0), 'depth': depth}


def _to_frame(fr, u, v, k):
    du, dv = u - fr['c'][0], v - fr['c'][1]
    return ((du * fr['x'][0] + dv * fr['x'][1]) * k, (du * fr['y'][0] + dv * fr['y'][1]) * k)


def _from_frame(fr, x, y, k):
    return (fr['c'][0] + (fr['x'][0] * x + fr['y'][0] * y) / k,
            fr['c'][1] + (fr['x'][1] * x + fr['y'][1] * y) / k)


# ---------------------------------------------------------------- reading a tag
def tag_reference(tag, e):
    try:
        refs = list(tag.GetTaggedReferences())          # 2022+
        if refs:
            return refs[0]
    except Exception:
        pass
    try:
        return DB.Reference(e)
    except Exception:
        return None


def tagged_element(doc, tag):
    try:
        ids = list(tag.GetTaggedLocalElementIds())
        if ids:
            return doc.GetElement(ids[0])
    except Exception:
        pass
    try:
        return doc.GetElement(tag.TaggedLocalElementId)
    except Exception:
        return None


def sample(doc, view, tag, e, key):
    """Where this tag sits relative to its element (paper mm, element frame). None when unknown."""
    fr = frame(e, view, key)
    if fr is None:
        return None
    k = _k(view)
    hu, hv = _uv(tag.TagHeadPosition, view)
    s = {'sit': fr['sit'], 'leader': bool(getattr(tag, 'HasLeader', False)),
         'orient': 'v' if tag.TagOrientation == DB.TagOrientation.Vertical else 'h'}
    if fr['curve']:
        n = fr['n']
        dist = (hu - fr['a'][0]) * n[0] + (hv - fr['a'][1]) * n[1]
        s['x'] = 1.0 if dist >= 0 else -1.0                      # side
        s['y'] = (abs(dist) - fr['half']) * k                    # gap from the duct edge
        return s
    s['x'], s['y'] = _to_frame(fr, hu, hv, k)
    if s['leader']:
        ref = tag_reference(tag, e)
        try:
            if ref is not None and tag.HasLeaderElbow(ref):
                eu, ev = _uv(tag.GetLeaderElbow(ref), view)
                s['elbow'] = list(_to_frame(fr, eu, ev, k))
        except Exception:
            pass
        try:
            if tag.LeaderEndCondition == DB.LeaderEndCondition.Free and ref is not None:
                eu, ev = _uv(tag.GetLeaderEnd(ref), view)
                s['end'] = list(_to_frame(fr, eu, ev, k))
        except Exception:
            pass
    return s


def _moved(a, b):
    if a is None or b is None:
        return True
    if a.get('leader') != b.get('leader') or a.get('orient') != b.get('orient'):
        return True
    return ((a['x'] - b['x']) ** 2 + (a['y'] - b['y']) ** 2) ** 0.5 > MOVED_MM


# ---------------------------------------------------------------- the stores
def _view_key(doc, view):
    try:
        return project_key(doc) + '|' + view.UniqueId
    except Exception:
        return project_key(doc) + '|' + str(eid_int(view.Id))


def remember(doc, view, placed):
    """placed: [(tag, element, key)] - store where Smart Tag put them."""
    if not placed:
        return
    store = load_json(PLACED, {})
    vk = _view_key(doc, view)
    bucket = store.get(vk, {})
    for tag, e, key in placed:
        try:
            s = sample(doc, view, tag, e, key)
            if s is not None:
                bucket[tag.UniqueId] = {'key': key, 'elem': e.UniqueId, 'sample': s}
        except Exception:
            pass
    store[vk] = bucket
    save_json(PLACED, store)


def _merge(spots, s, weight):
    for sp in spots:
        if sp.get('leader') == s.get('leader') and sp.get('orient') == s.get('orient') and \
                ((sp['x'] - s['x']) ** 2 + (sp['y'] - s['y']) ** 2) ** 0.5 <= MERGE_MM:
            n = sp['n'] + weight
            sp['x'] = (sp['x'] * sp['n'] + s['x'] * weight) / n
            sp['y'] = (sp['y'] * sp['n'] + s['y'] * weight) / n
            for f in ('elbow', 'end'):
                if s.get(f):
                    sp[f] = s[f]
            sp['n'] = n
            return
    item = dict((k, v) for k, v in s.items() if k != 'sit')
    item['n'] = weight
    spots.append(item)


def learn(doc, view, include_hand_placed=True, categories=None):
    """Read the tags of the view and learn from them. Returns a report dict."""
    from emperor_mep import tagging as TG
    rep = {'moved': 0, 'kept': 0, 'hand': 0, 'deleted': 0, 'situations': {}}
    placed = load_json(PLACED, {})
    vk = _view_key(doc, view)
    bucket = placed.get(vk, {})
    learned = load_json(LEARNED, {})
    seen = set()

    def add(s, weight):
        if s is None:
            return
        spots = learned.setdefault(s['sit'], [])
        _merge(spots, s, weight)
        spots.sort(key=lambda sp: -sp['n'])
        del spots[MAX_SPOTS:]
        rep['situations'][s['sit']] = rep['situations'].get(s['sit'], 0) + 1

    for uid, rec in list(bucket.items()):
        tag = doc.GetElement(uid)
        seen.add(uid)
        if tag is None:
            rep['deleted'] += 1
            continue
        e = tagged_element(doc, tag)
        if e is None:
            continue
        now = sample(doc, view, tag, e, rec['key'])
        if _moved(rec.get('sample'), now):
            add(now, W_MOVED)
            rep['moved'] += 1
        else:
            add(now, W_KEPT)
            rep['kept'] += 1
    placed[vk] = {}                       # learned once - start fresh for this view
    save_json(PLACED, placed)

    if include_hand_placed:
        by_tag_cat = dict((int(c[3]), c[0]) for c in TG.CATEGORIES)
        for tag in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag):
            try:
                if tag.UniqueId in seen or tag.Category is None:
                    continue
                key = by_tag_cat.get(eid_int(tag.Category.Id))
                if key is None or (categories and key not in categories):
                    continue
                e = tagged_element(doc, tag)
                if e is None:
                    continue
                add(sample(doc, view, tag, e, key), W_HAND)
                rep['hand'] += 1
            except Exception:
                pass
    save_json(LEARNED, learned)
    return rep


def spots_for(sit, limit=4):
    return list(load_json(LEARNED, {}).get(sit, []))[:limit]


def forget(sit_prefix=None):
    if sit_prefix is None:
        save_json(LEARNED, {})
        return
    learned = load_json(LEARNED, {})
    for k in list(learned):
        if k.split('|')[0] == sit_prefix:
            del learned[k]
    save_json(LEARNED, learned)


def summary():
    learned = load_json(LEARNED, {})
    if not learned:
        return u'Nothing learned yet.'
    lines = []
    for sit in sorted(learned):
        spots = learned[sit]
        best = spots[0]
        lines.append(u'%s: %d spot(s), best x %.1f / y %.1f mm%s (%.0f votes)' % (
            sit, len(spots), best['x'], best['y'], ', leader' if best.get('leader') else '', best['n']))
    return u'\n'.join(lines)


# ---------------------------------------------------------------- placing on a learned spot
def apply_spot(doc, view, tag, e, ref, fr, spot, t=0.5, always_horizontal=False):
    """Move the tag to a learned spot. For ducts / pipes t is the position along the run."""
    k = _k(view)
    depth = fr.get('depth')
    if depth is None:
        try:
            depth = tag.TagHeadPosition.DotProduct(view.ViewDirection)
        except Exception:
            depth = 0.0
    if not always_horizontal:
        try:
            want = DB.TagOrientation.Vertical if spot.get('orient') == 'v' else DB.TagOrientation.Horizontal
            if tag.TagOrientation != want:
                tag.TagOrientation = want
        except Exception:
            pass
    try:
        if bool(tag.HasLeader) != bool(spot.get('leader')):
            tag.HasLeader = bool(spot.get('leader'))
    except Exception:
        pass
    if fr['curve']:
        a, b = fr['a'], fr['b']
        pu, pv = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        dist = spot['x'] * (fr['half'] + max(0.0, spot['y']) / k)
        hu, hv = pu + fr['n'][0] * dist, pv + fr['n'][1] * dist
        tag.TagHeadPosition = _xyz(view, hu, hv, depth)
        return
    hu, hv = _from_frame(fr, spot['x'], spot['y'], k)
    tag.TagHeadPosition = _xyz(view, hu, hv, depth)
    if spot.get('leader') and ref is not None:
        doc.Regenerate()
        if spot.get('end'):
            try:
                tag.LeaderEndCondition = DB.LeaderEndCondition.Free
                eu, ev = _from_frame(fr, spot['end'][0], spot['end'][1], k)
                tag.SetLeaderEnd(ref, _xyz(view, eu, ev, depth))
            except Exception:
                pass
        if spot.get('elbow'):
            try:
                eu, ev = _from_frame(fr, spot['elbow'][0], spot['elbow'][1], k)
                tag.SetLeaderElbow(ref, _xyz(view, eu, ev, depth))
            except Exception:
                pass
