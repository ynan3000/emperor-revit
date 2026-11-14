# -*- coding: utf-8 -*-
"""2D line tools for turning drawings into ducts - Python 3 standard library only.

All segments are (x1, y1, x2, y2) in one unit (meters for model work).
    merge_collinear(segs, tol)              join pieces of the same straight line
    pair_double_lines(segs, min_w, max_w)   duct drawn as two parallel lines -> centerline + width
    snap_ends(lines, extra)                 extend / trim ends onto the duct they meet (tees, elbows)
    Calibration(points | scale)             PDF points -> model meters
"""
import math


def _len(s):
    return math.hypot(s[2] - s[0], s[3] - s[1])


def _dir(s):
    L = _len(s) or 1.0
    return ((s[2] - s[0]) / L, (s[3] - s[1]) / L)


def _angle(s):
    a = math.atan2(s[3] - s[1], s[2] - s[0]) % math.pi
    return a


def _adiff(a, b):
    d = abs(a - b) % math.pi
    return min(d, math.pi - d)


# ---------------------------------------------------------------------------- calibration
class Calibration(object):
    """Maps PDF points to model meters.

    points: [[px, py, mx, my], [px, py, mx, my]]  two known positions (e.g. two grid intersections)
            -> scale, rotation and offset are all solved (most reliable)
    scale:  drawing scale denominator (100 for 1:100) with origin [px, py, mx, my] for one known point
    """

    def __init__(self, points=None, scale=None, origin=None):
        if points and len(points) >= 2:
            (p1x, p1y, m1x, m1y), (p2x, p2y, m2x, m2y) = points[0][:4], points[1][:4]
            zp1, zp2 = complex(p1x, p1y), complex(p2x, p2y)
            zm1, zm2 = complex(m1x, m1y), complex(m2x, m2y)
            if abs(zp2 - zp1) < 1e-9:
                raise ValueError('The two calibration points are the same PDF point.')
            self.a = (zm2 - zm1) / (zp2 - zp1)
            self.b = zm1 - self.a * zp1
            self.mode = 'two points'
        elif scale:
            k = (25.4 / 72.0) * float(scale) / 1000.0          # pt -> mm on paper -> m in the model
            self.a = complex(k, 0)
            if origin:
                px, py, mx, my = origin[:4]
                self.b = complex(mx, my) - self.a * complex(px, py)
            else:
                self.b = complex(0, 0)
            self.mode = '1:%s' % scale
        else:
            self.a, self.b, self.mode = complex(1, 0), complex(0, 0), 'none (PDF points)'

    @property
    def meters_per_point(self):
        return abs(self.a)

    def pt(self, x, y):
        z = self.a * complex(x, y) + self.b
        return (z.real, z.imag)

    def seg(self, s):
        a = self.pt(s[0], s[1])
        b = self.pt(s[2], s[3])
        return (a[0], a[1], b[0], b[1])

    def describe(self):
        return {'mode': self.mode, 'meters_per_pdf_point': round(self.meters_per_point, 6),
                'rotation_deg': round(math.degrees(math.atan2(self.a.imag, self.a.real)), 3)}


# ---------------------------------------------------------------------------- merge
def merge_collinear(segs, tol=0.002, angle_tol_deg=0.5):
    """Join overlapping / touching pieces that lie on the same straight line."""
    atol = math.radians(angle_tol_deg)
    groups = {}
    for s in segs:
        if _len(s) < 1e-9:
            continue
        a = _angle(s)
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        off = s[0] * nx + s[1] * ny
        key = (round(a / atol), round(off / max(tol, 1e-9)))
        groups.setdefault(key, []).append((s, ux, uy, nx, ny, off))
    out = []
    for items in groups.values():
        ux, uy, nx, ny, off = items[0][1:]
        spans = []
        for s, *_ in items:
            t1 = s[0] * ux + s[1] * uy
            t2 = s[2] * ux + s[3] * uy
            spans.append((min(t1, t2), max(t1, t2)))
        spans.sort()
        cur = list(spans[0])
        for a, b in spans[1:]:
            if a <= cur[1] + tol:
                cur[1] = max(cur[1], b)
            else:
                out.append(_from_span(cur, ux, uy, nx, ny, off))
                cur = [a, b]
        out.append(_from_span(cur, ux, uy, nx, ny, off))
    return out


def _from_span(span, ux, uy, nx, ny, off):
    a, b = span
    return (a * ux + off * nx, a * uy + off * ny, b * ux + off * nx, b * uy + off * ny)


# ---------------------------------------------------------------------------- double lines
def pair_double_lines(segs, min_w, max_w, angle_tol_deg=2.0, min_overlap=0.5):
    """Parallel line pairs at a duct-like distance -> (cx1, cy1, cx2, cy2, width).

    Closest partners first; a long side line can pair with several shorter pieces of the other side
    (e.g. a main whose other side is broken by branch openings). Returns (centerlines, unpaired)."""
    atol = math.radians(angle_tol_deg)
    items = []
    for i, s in enumerate(segs):
        L = _len(s)
        if L < 1e-9:
            continue
        a = _angle(s)
        ux, uy = math.cos(a), math.sin(a)
        t1 = s[0] * ux + s[1] * uy
        t2 = s[2] * ux + s[3] * uy
        items.append({'i': i, 's': s, 'a': a, 'u': (ux, uy), 'n': (-uy, ux),
                      'off': s[0] * -uy + s[1] * ux, 't': (min(t1, t2), max(t1, t2)), 'L': L})
    # bucket by angle so the search stays fast
    buckets = {}
    for it in items:
        buckets.setdefault(int(it['a'] / atol), []).append(it)
    cands = []
    for it in items:
        k = int(it['a'] / atol)
        for kk in (k - 1, k, k + 1, k + int(math.pi / atol) - 1, k - int(math.pi / atol) + 1):
            for jt in buckets.get(kk, []):
                if jt['i'] <= it['i'] or _adiff(it['a'], jt['a']) > atol:
                    continue
                # distance between the parallel lines, measured on it's normal
                nx, ny = it['n']
                d = abs((jt['s'][0] + jt['s'][2]) / 2.0 * nx + (jt['s'][1] + jt['s'][3]) / 2.0 * ny - it['off'])
                if d < min_w or d > max_w:
                    continue
                ux, uy = it['u']
                j1 = jt['s'][0] * ux + jt['s'][1] * uy
                j2 = jt['s'][2] * ux + jt['s'][3] * uy
                lo, hi = max(it['t'][0], min(j1, j2)), min(it['t'][1], max(j1, j2))
                ov = hi - lo
                if ov <= 0 or ov < min_overlap * min(it['L'], jt['L']):
                    continue
                cands.append((d, it, jt, lo, hi))
    cands.sort(key=lambda c: c[0])
    covered = {}          # item index -> list of covered (t0, t1) in that item's own axis
    lines = []

    def free_parts(item, lo, hi):
        parts = [(lo, hi)]
        for c0, c1 in covered.get(item['i'], []):
            nxt = []
            for a, b in parts:
                if c1 <= a or c0 >= b:
                    nxt.append((a, b))
                    continue
                if a < c0:
                    nxt.append((a, c0))
                if c1 < b:
                    nxt.append((c1, b))
            parts = nxt
        return parts

    def to_axis(item, x, y):
        return x * item['u'][0] + y * item['u'][1]

    for d, it, jt, lo, hi in cands:
        ux, uy = it['u']
        nx, ny = it['n']
        joff = (jt['s'][0] + jt['s'][2]) / 2.0 * nx + (jt['s'][1] + jt['s'][3]) / 2.0 * ny
        coff = (it['off'] + joff) / 2.0
        for a, b in free_parts(it, lo, hi):
            # same stretch measured on the partner line
            pa = (a * ux + joff * nx, a * uy + joff * ny)
            pb = (b * ux + joff * nx, b * uy + joff * ny)
            ja, jb = sorted((to_axis(jt, *pa), to_axis(jt, *pb)))
            for c, e in free_parts(jt, ja, jb):
                # back to it's axis
                qa = (c * jt['u'][0] + joff * nx, c * jt['u'][1] + joff * ny)
                qb = (e * jt['u'][0] + joff * nx, e * jt['u'][1] + joff * ny)
                t0, t1 = sorted((qa[0] * ux + qa[1] * uy, qb[0] * ux + qb[1] * uy))
                t0, t1 = max(t0, a), min(t1, b)
                if t1 - t0 < max(0.25 * d, 1e-6):
                    continue
                lines.append((t0 * ux + coff * nx, t0 * uy + coff * ny, t1 * ux + coff * nx, t1 * uy + coff * ny, d))
                covered.setdefault(it['i'], []).append((t0, t1))
                j0, j1 = sorted((to_axis(jt, t0 * ux + joff * nx, t0 * uy + joff * ny),
                                 to_axis(jt, t1 * ux + joff * nx, t1 * uy + joff * ny)))
                covered.setdefault(jt['i'], []).append((j0, j1))
    used = set(covered)
    unpaired = [it['s'] for it in items if it['i'] not in used]
    return lines, unpaired


# ---------------------------------------------------------------------------- connect ends
def _line_intersection(p, r, q, s):
    """p + t r  and  q + u s.  Returns (t, u) or None if parallel."""
    cross = r[0] * s[1] - r[1] * s[0]
    if abs(cross) < 1e-12:
        return None
    qp = (q[0] - p[0], q[1] - p[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / cross
    u = (qp[0] * r[1] - qp[1] * r[0]) / cross
    return t, u


def snap_ends(lines, extra=0.15, angle_min_deg=20.0):
    """lines: [x1, y1, x2, y2, width]. Moves each end that stops near another (non-parallel) duct:
    - onto that duct's centerline (tee: branch ends on the main's centerline)
    - for two ends meeting at a corner, both go to the corner point (elbow)
    Returns new lines (lists)."""
    L = [list(l) for l in lines]
    amin = math.radians(angle_min_deg)
    for i, a in enumerate(L):
        for end in (0, 1):
            ex, ey = a[2 * end], a[2 * end + 1]
            ox, oy = a[2 - 2 * end], a[3 - 2 * end]           # the other end of a
            r = (ex - ox, ey - oy)
            la = math.hypot(*r)
            if la < 1e-9:
                continue
            best = None
            for j, b in enumerate(L):
                if j == i:
                    continue
                s = (b[2] - b[0], b[3] - b[1])
                lb = math.hypot(*s)
                if lb < 1e-9:
                    continue
                cosang = abs((r[0] * s[0] + r[1] * s[1]) / (la * lb))
                if math.acos(min(1.0, cosang)) < amin:
                    continue
                hit = _line_intersection((ox, oy), r, (b[0], b[1]), s)
                if hit is None:
                    continue
                t, u = hit
                reach = (b[4] / 2.0 + a[4] / 2.0 + extra)
                ix, iy = ox + r[0] * t, oy + r[1] * t
                gap = math.hypot(ix - ex, iy - ey)
                if gap > reach:
                    continue
                along_b = u * lb
                if along_b < -reach or along_b > lb + reach:
                    continue
                if best is None or gap < best[0]:
                    best = (gap, j, ix, iy, along_b, lb)
            if best is None:
                continue
            _gap, j, ix, iy, along_b, lb = best
            a[2 * end], a[2 * end + 1] = ix, iy
            b = L[j]
            reach_b = b[4] / 2.0 + a[4] / 2.0 + extra
            # corner: the meeting point is beyond / near an end of b -> move that end too (elbow)
            if along_b < reach_b:
                b[0], b[1] = ix, iy
            elif along_b > lb - reach_b:
                b[2], b[3] = ix, iy
    return [tuple(l) for l in L if math.hypot(l[2] - l[0], l[3] - l[1]) > 1e-6]


def round_size(width_m, step_mm=50, min_mm=100):
    mm = width_m * 1000.0
    return max(min_mm, int(round(mm / step_mm)) * step_mm)
