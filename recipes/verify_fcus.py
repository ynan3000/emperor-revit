# DESC: Check ducted FCUs: counts per level, rotations, unconnected refrigerant connectors, unclosed pipe joints, mirrored units and return-side wall clearance, plus free pipe ends in the whole model.
# PARAM: fcu_family - FCU family name (required)
# PARAM: min_id - only units with id >= this (default 0)
fam = P.get("fcu_family")
if not fam:
    raise Exception("Pass fcu_family = the ducted FCU family name")
min_id = P.get("min_id", 0)
ard, trf = link(doc, "_AR_")
VW, HW = wall_faces_index(ard, trf)
def nxt(c, exclude):
    for r in c.AllRefs:
        o = r.Owner
        if isinstance(o, DB.MEPSystem) or eint(o.Id) in exclude or not o.Category or o.Category.Name not in ("Pipes", "Pipe Fittings"):
            continue
        return r
def joints_ok(f):
    for c in f.MEPModel.ConnectorManager.Connectors:
        if "Piping" not in str(c.Domain) or "Sanitary" in str(c.PipeSystemType):
            continue
        ex = set([eint(f.Id)])
        cur = c
        for _ in range(10):
            r = nxt(cur, ex)
            if r is None:
                break
            if r.Origin.DistanceTo(cur.Origin) > 0.002 * 3.2808:
                return False
            o = r.Owner
            ex.add(eint(o.Id))
            oth = [cc for cc in cmgr(o).Connectors if cc.Origin.DistanceTo(r.Origin) > 1e-3]
            if not oth:
                break
            cur = max(oth, key=lambda cc: cc.Origin.DistanceTo(r.Origin)) if isinstance(o, DB.MEPCurve) else oth[0]
            if isinstance(o, DB.MEPCurve) and o.Location.Curve.Length / FT > 4:
                break
    return True
bylevel, rots = collections.Counter(), collections.Counter()
unconn, open_j, ret_cl, mirrored = [], [], [], 0
for e in cat_elements(doc, DB.BuiltInCategory.OST_MechanicalEquipment):
    if family_name(e) != fam or eint(e.Id) < min_id:
        continue
    bylevel[pstr(e, DB.BuiltInParameter.FAMILY_LEVEL_PARAM)] += 1
    rots[round(math.degrees(e.Location.Rotation))] += 1
    refr = [c for c in e.MEPModel.ConnectorManager.Connectors if "Piping" in str(c.Domain) and "Sanitary" not in str(c.PipeSystemType)]
    if refr and not all(c.IsConnected for c in refr):
        unconn.append(eint(e.Id))
    if not joints_ok(e):
        open_j.append(eint(e.Id))
    if e.Mirrored:
        mirrored += 1
        hv = [c for c in e.MEPModel.ConnectorManager.Connectors if "Hvac" in str(c.Domain)]
        sup = [c for c in hv if "SupplyAir" in str(c.DuctSystemType)]
        ret = [c for c in hv if "ReturnAir" in str(c.DuctSystemType)]
        if sup and ret:
            b = host_bbox(e)
            up = sup[0].Origin.Y > ret[0].Origin.Y
            d = wall_distance(HW, b[0], b[1], b[2] if up else b[3], -1 if up else +1)
            if d is not None:
                ret_cl.append(d)
fp, ff = free_ends(doc)
print("FCUs by level: %s | rotations: %s | mirrored: %d" % (dict(bylevel), dict(rots), mirrored))
print("unconnected refrigerant connector: %d %s | unclosed pipe joints: %d %s" % (len(unconn), unconn[:8], len(open_j), open_j[:8]))
if ret_cl:
    print("return-side wall clearance (m): min %.3f median %.3f max %.3f | below 0.30: %d" % (min(ret_cl), sorted(ret_cl)[len(ret_cl) // 2], max(ret_cl), sum(1 for d in ret_cl if d < 0.299)))
print("free connector ends in the model: pipes %d, pipe fittings %d" % (fp, ff))
result = {"unconnected": len(unconn), "open_joints": len(open_j)}
