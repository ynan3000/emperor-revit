# DESC: Create one MEP space per placed room of a linked architecture model, copying room name and number. Optionally deletes all current spaces first.
# PARAM: link - text in the link's name (default "_AR_")
# PARAM: levels - list of level names (default: every host level that also has rooms in the link)
# PARAM: exclude - list of name fragments to skip, e.g. ["SHAFT"] (default ["SHAFT"])
# PARAM: delete_existing - true = unpin and delete ALL existing spaces first (default false)
link_key = P.get("link", "_AR_")
exclude = [x.upper() for x in P.get("exclude", ["SHAFT"])]
ld, tr = link(doc, link_key)
host_levels = levels(doc)
want = P.get("levels") or sorted(host_levels.keys())
if P.get("delete_existing"):
    old = list(cat_elements(doc, DB.BuiltInCategory.OST_MEPSpaces))
    print("old spaces deleted: %d" % unpin_and_delete(doc, old))
    doc.Regenerate()
summary = []
for i, lv in enumerate(want):
    if lv not in host_levels:
        continue
    checkpoint()
    rooms = [r for r in link_rooms(ld, lv) if not any(x in rname(r).upper() for x in exclude)]
    skipped = len(link_rooms(ld, lv)) - len(rooms)
    if not rooms:
        continue
    made = []
    for r in rooms:
        lp = tr.OfPoint(r.Location.Point)
        try:
            made.append((doc.Create.NewSpace(host_levels[lv], DB.UV(lp.X, lp.Y)), r))
        except Exception as ex:
            summary.append((lv, r.Number, "create failed: %s" % ("%s" % ex)[:50]))
    doc.Regenerate()
    ok, bad, off = 0, 0, 0
    for sp, r in made:
        if sp.Area <= 0:                         # not enclosed / redundant: remove it
            doc.Delete(sp.Id)
            bad += 1
            continue
        sp.Number = r.Number
        sp.get_Parameter(DB.BuiltInParameter.ROOM_NAME).Set(rname(r))
        a, b = M(M(sp.Area)), M(M(r.Area))
        if b > 0 and abs(a - b) / b > 0.05:
            off += 1
        ok += 1
    progress("%s: %d spaces" % (lv, ok), i + 1, len(want))
    print("%s: created %d | removed (no area) %d | rooms skipped by name %d | area differs >5%% from the room: %d" % (lv, ok, bad, skipped, off))
result = {"failed": summary}
