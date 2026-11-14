# DESC: Place a host family type at every instance of a family found in a link (e.g. ID grilles -> return slot diffusers), at a chosen elevation per level, with rotation, long-axis match and duplicate removal.
# PARAM: link - text in the link's name (default "_ID_")
# PARAM: source_contains - text in the link family name, e.g. "Return 2015" (required)
# PARAM: family - host family name (required)
# PARAM: type_name - host family type name (required)
# PARAM: elevation_by_level - {"LEVEL NAME": metres above that level} (required)
# PARAM: rotation_offset_deg - added to the source rotation (default -180)
# PARAM: local_offset_m - [x, y] shift in the source's local axes (default [0, -0.01])
# PARAM: match_axis - rotate 90 when the long axis differs from the source (default true)
ld, tr = link(doc, P.get("link", "_ID_"))
src_text = P["source_contains"].upper()
elev = P["elevation_by_level"]
lv_all = levels(doc)
lv_use = dict((k, v) for k, v in lv_all.items() if k in elev)
sym = [s for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol) if s.FamilyName == P["family"] and nm(s) == P["type_name"]]
if len(sym) != 1:
    raise Exception("family type '%s : %s' found %d times" % (P["family"], P["type_name"], len(sym)))
sym = sym[0]
if not sym.IsActive:
    sym.Activate()
    doc.Regenerate()
rot_off = P.get("rotation_offset_deg", -180.0)
lx, ly = P.get("local_offset_m", [0.0, -0.01])
match_axis = P.get("match_axis", True)
tr_rot = math.degrees(math.atan2(tr.BasisX.Y, tr.BasisX.X))
existing = [(e.Location.Point, e) for e in cat_elements(doc, DB.BuiltInCategory.OST_DuctTerminal) if family_name(e) == P["family"]]
sources = []
for e in DB.FilteredElementCollector(ld).OfClass(DB.FamilyInstance):
    fam = family_name(e)
    if fam and src_text in fam.upper():
        sources.append(e)
print("source instances in the link: %d" % len(sources))
placed, skipped, fixed = [], 0, 0
for k, e in enumerate(sources):
    if k % 25 == 0:
        checkpoint()
        progress("placing %d / %d" % (k, len(sources)), k, len(sources))
    p = tr.OfPoint(e.Location.Point)
    th = math.radians(math.degrees(e.Location.Rotation) + tr_rot)
    dx, dy = lx * math.cos(th) - ly * math.sin(th), lx * math.sin(th) + ly * math.cos(th)
    x, y, z = M(p.X) + dx, M(p.Y) + dy, M(p.Z)
    cand = [(n, l) for n, l in lv_use.items() if M(l.Elevation) <= z + 0.3]
    if not cand:
        continue
    lname, lvl = max(cand, key=lambda c: c[1].Elevation)
    if any(math.hypot(M(q.X) - x, M(q.Y) - y) < 0.05 and abs(M(q.Z) - (M(lvl.Elevation) + elev[lname])) < 0.3 for q, _ in existing):
        skipped += 1
        continue
    pt = DB.XYZ(F(x), F(y), lvl.Elevation + F(elev[lname]))
    inst = doc.Create.NewFamilyInstance(pt, sym, lvl, DB.Structure.StructuralType.NonStructural)
    prm = inst.get_Parameter(DB.BuiltInParameter.INSTANCE_ELEVATION_PARAM)
    if prm is not None and not prm.IsReadOnly:
        prm.Set(F(elev[lname]))
    ang = (math.degrees(th) + rot_off) % 360.0
    if abs(ang) > 1e-6 and abs(ang - 360.0) > 1e-6:
        DB.ElementTransformUtils.RotateElement(doc, inst.Id, DB.Line.CreateBound(pt, pt + DB.XYZ.BasisZ), math.radians(ang))
    placed.append((inst, e))
doc.Regenerate()
if match_axis:                                   # long axis of the new instance must equal the source's
    for inst, e in placed:
        a, b = host_bbox(inst), host_bbox(e, tr)
        if a is None or b is None:
            continue
        la = "x" if (a[1] - a[0]) > (a[3] - a[2]) else "y"
        lb = "x" if (b[1] - b[0]) > (b[3] - b[2]) else "y"
        if la != lb:
            p = inst.Location.Point
            DB.ElementTransformUtils.RotateElement(doc, inst.Id, DB.Line.CreateBound(p, p + DB.XYZ.BasisZ), math.pi / 2)
            fixed += 1
doc.Regenerate()
groups = collections.defaultdict(list)           # stacked sources produce identical instances: keep the oldest
for inst, e in placed:
    p = inst.Location.Point
    groups[(round(M(p.X), 3), round(M(p.Y), 3), round(M(p.Z), 3))].append(inst)
dups = 0
for g in groups.values():
    g.sort(key=lambda i: eint(i.Id))
    for extra in g[1:]:
        doc.Delete(extra.Id)
        dups += 1
print("placed %d | skipped (already there) %d | rotated 90 to match axis %d | stacked duplicates removed %d" % (len(placed) - dups, skipped, fixed, dups))
result = {"placed": len(placed) - dups}
