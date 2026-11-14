# DESC: Tag every untagged space in the documentation plan views, placing each tag in free space (inside the space if possible, else nearby with a leader) so it never overlaps another tag, text, annotation or dimension.
# PARAM: views - list of view names (default: plan views whose view template name contains template_contains)
# PARAM: template_contains - default "DOCUMENTATION"
# PARAM: tag_type - space tag type name (default "Space Tag")
# PARAM: type_by_view - {"VIEW NAME": "tag type"} overrides
# PARAM: margin_m - clear gap kept around each tag (default 0.10)
# PARAM: search_m - how far from the space centre a tag may move (default 6)
margin = P.get("margin_m", 0.10) * FT
search = int(P.get("search_m", 6.0) / 0.25)
types = dict((nm(t), t) for t in cat_elements(doc, DB.BuiltInCategory.OST_MEPSpaceTags, types=True))
sheet_views = set(eint(vp.ViewId) for vp in DB.FilteredElementCollector(doc).OfClass(DB.Viewport))
views = []
for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan):
    if v.IsTemplate:
        continue
    if P.get("views"):
        if v.Name in P["views"]:
            views.append(v)
    else:
        tpl = doc.GetElement(v.ViewTemplateId) if eint(v.ViewTemplateId) != -1 else None
        if tpl is not None and P.get("template_contains", "DOCUMENTATION").upper() in nm(tpl).upper():
            views.append(v)
views.sort(key=lambda v: v.Name)
offs = sorted(((i * 0.25 * FT, j * 0.25 * FT) for i in range(-search, search + 1) for j in range(-search, search + 1)), key=lambda o: o[0] ** 2 + o[1] ** 2)
report = []
for vi, view in enumerate(views):
    checkpoint()
    tname = (P.get("type_by_view") or {}).get(view.Name, P.get("tag_type", "Space Tag"))
    if tname not in types:
        report.append((view.Name, "tag type '%s' not found" % tname))
        continue
    ttype = types[tname]
    level = view.GenLevel
    z_in = level.Elevation + 3.0 * FT
    grid = Grid(8.0)
    tagged = set()
    for label, col in (("tag", DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag)),
                       ("text", DB.FilteredElementCollector(doc, view.Id).OfClass(DB.TextNote)),
                       ("annotation", DB.FilteredElementCollector(doc, view.Id).OfCategory(DB.BuiltInCategory.OST_GenericAnnotation)),
                       ("dimension", DB.FilteredElementCollector(doc, view.Id).OfCategory(DB.BuiltInCategory.OST_Dimensions)),
                       ("space tag", DB.FilteredElementCollector(doc, view.Id).OfCategory(DB.BuiltInCategory.OST_MEPSpaceTags)),
                       ("room tag", DB.FilteredElementCollector(doc, view.Id).OfCategory(DB.BuiltInCategory.OST_RoomTags))):
        for e in col:
            bb = e.get_BoundingBox(view)
            if bb is None:
                continue
            grid.add(bb.Min.X - margin, bb.Max.X + margin, bb.Min.Y - margin, bb.Max.Y + margin)
            if label == "space tag":
                try:
                    tagged.add(eint(e.Space.Id))
                except Exception:
                    pass
    spaces = [s for s in cat_elements(doc, DB.BuiltInCategory.OST_MEPSpaces) if s.Level is not None and s.Level.Id == level.Id and s.Area > 0 and eint(s.Id) not in tagged]
    spaces.sort(key=lambda s: (s.Area, eint(s.Id)))
    tags = []
    for s in spaces:                               # phase 1: create all tags at the space centre, regenerate ONCE
        p = s.Location.Point
        t = doc.Create.NewSpaceTag(s, DB.UV(p.X, p.Y), view)
        t.ChangeTypeId(ttype.Id)
        tags.append((s, t, p))
    doc.Regenerate()
    stat = collections.Counter()
    for k, (s, t, p) in enumerate(tags):           # phase 2: move each into a free spot
        if k % 20 == 0:
            checkpoint()
            progress("%s: %d / %d" % (view.Name, k, len(tags)), vi, len(views))
        try:
            bb = t.get_BoundingBox(view)
            if bb is None:
                stat["no bounding box (skipped)"] += 1
                continue
            w, h = bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y
            head = t.TagHeadPosition
            cx, cy = (bb.Min.X + bb.Max.X) / 2 - head.X, (bb.Min.Y + bb.Max.Y) / 2 - head.Y
            chosen = None
            for ox, oy in offs:
                hx, hy = p.X + ox, p.Y + oy
                x0, x1 = hx + cx - w / 2 - margin / 2, hx + cx + w / 2 + margin / 2
                y0, y1 = hy + cy - h / 2 - margin / 2, hy + cy + h / 2 + margin / 2
                if grid.hit(x0, x1, y0, y1):
                    continue
                if all(s.IsPointInSpace(DB.XYZ(px, py, z_in)) for px, py in ((x0, y0), (x1, y0), (x0, y1), (x1, y1), (hx + cx, hy + cy))):
                    chosen = (hx, hy, x0, x1, y0, y1, False)
                    break
            if chosen is None:                      # nothing free inside: nearest free spot outside, with a leader
                for ox, oy in offs:
                    hx, hy = p.X + ox, p.Y + oy
                    x0, x1 = hx + cx - w / 2 - margin / 2, hx + cx + w / 2 + margin / 2
                    y0, y1 = hy + cy - h / 2 - margin / 2, hy + cy + h / 2 + margin / 2
                    if not grid.hit(x0, x1, y0, y1):
                        chosen = (hx, hy, x0, x1, y0, y1, True)
                        break
            if chosen is None:
                stat["no free spot (left at centre)"] += 1
                grid.add(bb.Min.X, bb.Max.X, bb.Min.Y, bb.Max.Y)
                continue
            hx, hy, x0, x1, y0, y1, outside = chosen
            if outside:
                t.HasLeader = True
                stat["outside, with leader"] += 1
            else:
                stat["inside the space"] += 1
            t.TagHeadPosition = DB.XYZ(hx, hy, p.Z)                  # Z must be the space's own Z, or Revit rejects tags without a leader
            grid.add(x0 - margin / 2, x1 + margin / 2, y0 - margin / 2, y1 + margin / 2)
        except Exception as ex:
            stat["failed: %s" % ("%s" % ex)[:40]] += 1
    print("%s [%s]: %d tags -> %s" % (view.Name, tname, len(tags), dict(stat)))
result = {"views": [v.Name for v in views], "notes": report}
