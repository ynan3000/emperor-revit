# -*- coding: ascii -*-
"""Smart Insulation - add, update or remove pipe and duct insulation by system type.

A rule = one system type:
    {"kind": "duct" | "pipe", "system": "<system type name>", "insulation": "<insulation type name>",
     "thickness": "25"  or  "50:25, 150:40, 50"   (size <= 50 mm -> 25, <= 150 mm -> 40, else 50)}
Mode:  "add"     add where missing, leave existing insulation as it is
       "update"  add where missing AND set type / thickness of existing insulation
       "remove"  delete the insulation of the matching elements
The caller owns the transaction (run() does not start one).
"""
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Mechanical, Plumbing

from emperor_mep.common import (eid_int, name_of, mm_to_ft, ft_to_mm, bip_element_name, size_mm)

DUCT_CATS = {
    'curves': [DB.BuiltInCategory.OST_DuctCurves],
    'fittings': [DB.BuiltInCategory.OST_DuctFitting],
    'accessories': [DB.BuiltInCategory.OST_DuctAccessory],
    'flex': [DB.BuiltInCategory.OST_FlexDuctCurves],
}
PIPE_CATS = {
    'curves': [DB.BuiltInCategory.OST_PipeCurves],
    'fittings': [DB.BuiltInCategory.OST_PipeFitting],
    'accessories': [DB.BuiltInCategory.OST_PipeAccessory],
    'flex': [DB.BuiltInCategory.OST_FlexPipeCurves],
}


def insulation_types(doc, kind):
    cls = Mechanical.DuctInsulationType if kind == 'duct' else Plumbing.PipeInsulationType
    return sorted([t for t in DB.FilteredElementCollector(doc).OfClass(cls)], key=lambda t: name_of(t).lower())


def system_types(doc, kind):
    cls = Mechanical.MechanicalSystemType if kind == 'duct' else Plumbing.PipingSystemType
    return sorted([t for t in DB.FilteredElementCollector(doc).OfClass(cls)], key=lambda t: name_of(t).lower())


def parse_thickness(text):
    """'25' -> [(None, 25)];  '50:25, 150:40, 50' -> [(50, 25), (150, 40), (None, 50)]. Sizes and thicknesses in mm."""
    rules = []
    for part in (u'%s' % (text or u'')).replace(u';', u',').split(u','):
        part = part.strip().replace(u'<=', u'').replace(u'\u2264', u'')
        if not part:
            continue
        if u':' in part:
            a, b = part.split(u':', 1)
            rules.append((float(a.strip()), float(b.strip())))
        else:
            rules.append((None, float(part)))
    if not rules:
        raise ValueError('No thickness given.')
    return rules


def thickness_for(rules, size):
    for limit, thick in rules:
        if limit is None or size <= limit:
            return thick
    return rules[-1][1]


def _system_name(doc, e, kind):
    bip = DB.BuiltInParameter.RBS_DUCT_SYSTEM_TYPE_PARAM if kind == 'duct' else DB.BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM
    return bip_element_name(doc, e, bip)


def _collect(doc, kind, parts, view=None, ids=None):
    cats = DUCT_CATS if kind == 'duct' else PIPE_CATS
    wanted = []
    for part in parts:
        wanted.extend(cats.get(part, []))
    allowed = set(int(c) for c in wanted)
    out = []
    if ids:
        for i in ids:
            e = doc.GetElement(i)
            try:
                if e is not None and e.Category is not None and eid_int(e.Category.Id) in allowed:
                    out.append(e)
            except Exception:
                pass
        return out
    for bic in wanted:
        col = DB.FilteredElementCollector(doc, view.Id) if view is not None else DB.FilteredElementCollector(doc)
        out.extend(list(col.OfCategory(bic).WhereElementIsNotElementType()))
    return out


def existing_insulation(doc, e):
    try:
        ids = DB.InsulationLiningBase.GetInsulationIds(doc, e.Id)
        return [doc.GetElement(i) for i in ids if doc.GetElement(i) is not None]
    except Exception:
        return []


def run(doc, rules, mode='update', parts=('curves', 'fittings'), view=None, ids=None, dry_run=False):
    """Apply the rules. Returns a report dict. Must be called inside a transaction (unless dry_run)."""
    report = {'added': 0, 'updated': 0, 'removed': 0, 'unchanged': 0, 'skipped': 0,
              'failed': 0, 'errors': [], 'by_system': {}}
    for rule in rules:
        kind = rule.get('kind', 'pipe')
        system = (rule.get('system') or u'').strip().lower()
        if not system:
            continue
        ins_type = None
        if mode != 'remove':
            wanted = (rule.get('insulation') or u'').strip().lower()
            for t in insulation_types(doc, kind):
                if name_of(t).lower() == wanted:
                    ins_type = t
                    break
            if ins_type is None:
                report['errors'].append(u'Insulation type not found: %s' % rule.get('insulation'))
                continue
            try:
                th_rules = parse_thickness(rule.get('thickness'))
            except Exception as ex:
                report['errors'].append(u'Thickness for %s: %s' % (rule.get('system'), ex))
                continue
        stats = report['by_system'].setdefault(rule.get('system'), {'elements': 0, 'added': 0, 'updated': 0, 'removed': 0})
        creator = Mechanical.DuctInsulation.Create if kind == 'duct' else Plumbing.PipeInsulation.Create
        for e in _collect(doc, kind, parts, view, ids):
            if _system_name(doc, e, kind).lower() != system:
                continue
            stats['elements'] += 1
            current = existing_insulation(doc, e)
            try:
                if mode == 'remove':
                    if current:
                        if not dry_run:
                            for ins in current:
                                doc.Delete(ins.Id)
                        report['removed'] += 1
                        stats['removed'] += 1
                    else:
                        report['unchanged'] += 1
                    continue
                thick_mm = thickness_for(th_rules, size_mm(e))
                if not current:
                    if not dry_run:
                        creator(doc, e.Id, ins_type.Id, mm_to_ft(thick_mm))
                    report['added'] += 1
                    stats['added'] += 1
                elif mode == 'update':
                    changed = False
                    for ins in current:
                        if eid_int(ins.GetTypeId()) != eid_int(ins_type.Id):
                            if not dry_run:
                                ins.ChangeTypeId(ins_type.Id)
                            changed = True
                        if abs(ft_to_mm(ins.Thickness) - thick_mm) > 0.05:
                            if not dry_run:
                                ins.Thickness = mm_to_ft(thick_mm)
                            changed = True
                    if changed:
                        report['updated'] += 1
                        stats['updated'] += 1
                    else:
                        report['unchanged'] += 1
                else:
                    report['unchanged'] += 1
            except Exception as ex:
                report['failed'] += 1
                if len(report['errors']) < 12:
                    report['errors'].append(u'%s %s: %s' % (e.Category.Name if e.Category else '', eid_int(e.Id), ex))
    return report


def describe(report):
    lines = [u'Added: %d   Updated: %d   Removed: %d   Unchanged: %d   Failed: %d' % (
        report['added'], report['updated'], report['removed'], report['unchanged'], report['failed'])]
    for sysname, st in sorted(report['by_system'].items()):
        lines.append(u'  %s - %d elements: +%d added, %d updated, %d removed' % (
            sysname, st['elements'], st['added'], st['updated'], st['removed']))
    if report['errors']:
        lines.append(u'')
        lines.append(u'Problems:')
        lines.extend(u'  ' + x for x in report['errors'][:12])
    return u'\n'.join(lines)
