# -*- coding: ascii -*-
"""Crop to 3D - drag a rectangle in a plan view and get a 3D view of only that area."""
from Autodesk.Revit import DB
from Autodesk.Revit.UI.Selection import PickBoxStyle
from pyrevit import revit

import emperor_ui
from emperor_mep import boxes
from emperor_mep.common import begin

TITLE = 'Emperor - Crop to 3D'
doc = revit.doc
uidoc = revit.uidoc


def main():
    plan = doc.ActiveView
    if not isinstance(plan, DB.ViewPlan):
        emperor_ui.alert('Open a floor plan or ceiling plan first, then press Crop to 3D and drag a rectangle.',
                         TITLE, warn=True)
        return
    try:
        picked = uidoc.Selection.PickBox(PickBoxStyle.Enclosing, 'Drag a rectangle around the area to show in 3D')
    except Exception:
        return      # Esc
    box, info = boxes.crop_box_from_plan(doc, plan, picked.Min, picked.Max)
    t, _warnings = begin(doc, 'Emperor - Crop to 3D')
    try:
        name = boxes.unique_view_name(doc, u'Crop to 3D - %s' % plan.Name)
        view = boxes.make_view3d(doc, name, box, reuse=False)
        try:
            view.LookupParameter('Comments') and view.LookupParameter('Comments').Set(
                u'From %s - top: %s' % (plan.Name, info.get('top_from', '')))
        except Exception:
            pass
        t.Commit()
    except Exception as ex:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        emperor_ui.alert('The 3D view could not be created.\n\n%s' % ex, TITLE, warn=True)
        return
    uidoc.ActiveView = view


try:
    main()
except Exception as ex:
    emperor_ui.alert('Crop to 3D stopped unexpectedly.\n\n%s' % ex, TITLE, warn=True)
