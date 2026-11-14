# -*- coding: ascii -*-
"""System Box - 3D view with a section box around a whole MEP system."""
from Autodesk.Revit import DB
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import revit, EXEC_PARAMS

import emperor_ui
from emperor_mep import boxes
from emperor_mep.common import begin, load_json, save_json

# Filter naming: system types without the prefix get "<prefix><separator><system type>" (e.g. ABC_Supply Air).
# No prefix saved yet: the prefix the model's filters already use is suggested.
# Change in %APPDATA%\Emperor\system_box.json
_cfg = load_json('system_box.json', {})
if not _cfg:
    _cfg = {'filter_prefix': '', 'separator': '_', 'hide_other_systems': True}
    save_json('system_box.json', _cfg)

TITLE = 'Emperor - System Box'
doc = revit.doc
uidoc = revit.uidoc


class _HasSystem(ISelectionFilter):
    def AllowElement(self, e):
        try:
            return bool(boxes.systems_of(e))
        except Exception:
            return False

    def AllowReference(self, ref, pt):
        return False


def main():
    element = None
    for i in uidoc.Selection.GetElementIds():
        e = doc.GetElement(i)
        if e is not None and boxes.systems_of(e):
            element = e
            break
    if element is None:
        try:
            ref = uidoc.Selection.PickObject(ObjectType.Element, _HasSystem(),
                                             'Pick a duct, pipe, fitting, terminal or equipment of the system')
        except Exception:
            return      # Esc
        element = doc.GetElement(ref.ElementId)
    systems = boxes.systems_of(element)
    if not systems:
        emperor_ui.alert('This element is not part of a duct or pipe system.', TITLE, warn=True)
        return
    if len(systems) > 1:
        labels = [boxes.system_label(s) for s in systems]
        picked = emperor_ui.choose(TITLE, labels, 'This element belongs to several systems. Box which ones?')
        if not picked:
            return
        systems = [systems[i] for i in picked]
    reuse = not EXEC_PARAMS.config_mode      # Shift+click: always a new view
    show_context = emperor_ui.alert(
        'Show the walls and the other architectural / structural elements (floors, ceilings, columns, framing, '
        'doors...) in the System Box view?\n\nYes = show them around the system\nNo = ducts, pipes and equipment only',
        TITLE, yes=True, no=True)
    hide = _cfg.get('hide_other_systems', True)
    prefix = _cfg.get('filter_prefix', '')
    sep = _cfg.get('separator', '_')
    if not prefix:                              # suggest the prefix the model's filters already use
        try:
            from Autodesk.Revit import DB as _DB
            from emperor_claude.standards import prefix_rule
            rule = prefix_rule([f.Name for f in _DB.FilteredElementCollector(doc).OfClass(_DB.ParameterFilterElement)])
            if rule:
                prefix, sep = rule['prefix'], rule['separator']
        except Exception:
            pass
    create_missing = rename = True
    if hide:
        plan = boxes.plan_system_filters(doc, systems, prefix)
        missing, unprefixed = plan['missing'], plan['unprefixed']
        if missing or unprefixed:
            lines = []
            if missing:
                lines.append(u'%d system type(s) have no filter that hides them yet (e.g. %s) - they will get one.'
                             % (len(missing), u', '.join(boxes.name_of(t) for t, _k in missing[:3])))
            if unprefixed:
                lines.append(u'%d existing system filter(s) do not start with the prefix (e.g. %s) - the prefix '
                             u'will be added to their names.' % (len(unprefixed), u', '.join(f.Name for f in unprefixed[:3])))
            lines.append(u'')
            lines.append(u'Prefix for the filter names (names become  <prefix>%s<system type>):' % sep)
            answer = emperor_ui.ask_text(TITLE + ' - filter prefix', u'\n'.join(lines), prefix)
            if answer is None:
                create_missing = rename = False        # cancelled: only use the filters that exist
            elif answer.strip():
                prefix = answer.strip()
                if prefix != _cfg.get('filter_prefix'):
                    _cfg['filter_prefix'] = prefix
                    save_json('system_box.json', _cfg)
    t, _warnings = begin(doc, 'Emperor - System Box')
    try:
        view, count, _report = boxes.make_system_box(
            doc, systems, margin_m=0.3, reuse=reuse, hide_others=hide, prefix=prefix, separator=sep,
            create_missing=create_missing, rename=rename, show_context=show_context)
        t.Commit()
    except Exception as ex:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        emperor_ui.alert('System Box could not be created.\n\n%s' % ex, TITLE, warn=True)
        return
    uidoc.ActiveView = view


try:
    main()
except Exception as ex:
    emperor_ui.alert('System Box stopped unexpectedly.\n\n%s' % ex, TITLE, warn=True)
