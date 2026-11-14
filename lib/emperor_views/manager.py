# -*- coding: ascii -*-
"""View Manager - create / rename plan views per level and assign view templates.

View name = <prefix><sep><level name><sep><suffix> (the separator only on a side that has a prefix /
suffix). Several view types can be handled in one run (floor plans, ceiling plans, structural plans).
For a level that already has a view of the wanted type the caller chooses what happens: skip it, rename
the existing view, or create one more view.

build_plan() only reads the model and returns a list of actions; apply_plan() carries them out.
The caller owns the transaction (apply_plan / assign_template do not start one).
IronPython 2.7 and CPython 3 compatible.
"""
from Autodesk.Revit import DB

from emperor_mep.common import eid_int, make_eid, name_of, is_invalid

# key, label, view family (of the view family type), view type (of the view)
KINDS = [
    ('floor', u'Floor Plan', DB.ViewFamily.FloorPlan, DB.ViewType.FloorPlan),
    ('ceiling', u'Ceiling Plan', DB.ViewFamily.CeilingPlan, DB.ViewType.CeilingPlan),
    ('structural', u'Structural Plan', DB.ViewFamily.StructuralPlan, DB.ViewType.EngineeringPlan),
]
KIND_LABEL = dict((k[0], k[1]) for k in KINDS)
_FAMILY = dict((k[0], k[2]) for k in KINDS)
_VIEWTYPE = dict((k[0], k[3]) for k in KINDS)

# views that can take a view template (used by "Template for views")
TEMPLATE_VIEW_TYPES = (
    DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan, DB.ViewType.EngineeringPlan, DB.ViewType.AreaPlan,
    DB.ViewType.Section, DB.ViewType.Elevation, DB.ViewType.Detail, DB.ViewType.ThreeD,
    DB.ViewType.DraftingView,
)
VIEW_TYPE_LABELS = {
    'FloorPlan': u'Floor Plan', 'CeilingPlan': u'Ceiling Plan', 'EngineeringPlan': u'Structural Plan',
    'AreaPlan': u'Area Plan', 'Section': u'Section', 'Elevation': u'Elevation', 'Detail': u'Detail View',
    'ThreeD': u'3D View', 'DraftingView': u'Drafting View',
}
BAD_NAME_CHARS = u'\\:{}[]|;<>?`~'

SKIP, RENAME, CREATE = 'skip', 'rename', 'create'
MODES = (SKIP, RENAME, CREATE)
DEFAULT_SEP = u'-'


# ---------------------------------------------------------------- reading the model
def levels(doc):
    """Levels, lowest first."""
    return sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda lv: lv.Elevation)


def view_family_types(doc, kind):
    """View family types of one kind (e.g. every 'Floor Plan' type), sorted by name."""
    fam = _FAMILY[kind]
    out = []
    for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
        try:
            if t.ViewFamily == fam:
                out.append(t)
        except Exception:
            pass
    return sorted(out, key=lambda t: name_of(t).lower())


def view_type_label(view):
    key = u'%s' % view.ViewType
    return VIEW_TYPE_LABELS.get(key, key)


def templates(doc, kind=None):
    """View templates, sorted by name. kind given: only templates of that plan type."""
    wanted = _VIEWTYPE.get(kind)
    out = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
        try:
            if not v.IsTemplate:
                continue
            if wanted is not None and v.ViewType != wanted:
                continue
            out.append(v)
        except Exception:
            pass
    return sorted(out, key=lambda v: v.Name.lower())


def plan_views(doc, kind):
    """Every plan view (not a template) of one kind."""
    wanted = _VIEWTYPE[kind]
    out = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan):
        try:
            if not v.IsTemplate and v.ViewType == wanted:
                out.append(v)
        except Exception:
            pass
    return out


def _is_dependent(view):
    try:
        return not is_invalid(view.GetPrimaryViewId())
    except Exception:
        return False


def _level_id(view):
    try:
        lv = view.GenLevel
        return eid_int(lv.Id) if lv is not None else None
    except Exception:
        return None


def template_views(doc):
    """Views that can take a view template, sorted by type then name."""
    out = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
        try:
            if v.IsTemplate or isinstance(v, DB.ViewSheet):
                continue
            if v.ViewType in TEMPLATE_VIEW_TYPES:
                out.append(v)
        except Exception:
            pass
    return sorted(out, key=lambda v: (view_type_label(v), v.Name.lower()))


def template_name(doc, view):
    try:
        if is_invalid(view.ViewTemplateId):
            return u''
        return name_of(doc.GetElement(view.ViewTemplateId))
    except Exception:
        return u''


# ---------------------------------------------------------------- names
def bad_chars(text):
    """Characters of text that Revit does not accept in a view name."""
    return u''.join(sorted(set(ch for ch in (u'%s' % (text or u'')) if ch in BAD_NAME_CHARS)))


def make_name(prefix, level_name, suffix, sep=u''):
    """prefix + sep + level name + sep + suffix. The separator is only used on a side that has text."""
    prefix = (u'%s' % (prefix or u'')).strip()
    suffix = (u'%s' % (suffix or u'')).strip()
    sep = u'%s' % (sep or u'')
    name = u'%s' % level_name
    if prefix:
        name = prefix + sep + name
    if suffix:
        name = name + sep + suffix
    return name.strip()


# ---------------------------------------------------------------- the plan
def build_plan(doc, level_ids, kinds, prefix=u'', suffix=u'', existing=SKIP, sep=u''):
    """What would happen. Reads only.

    level_ids : ints of the levels to handle
    kinds     : list of kind keys ('floor', 'ceiling', 'structural')
    existing  : SKIP / RENAME / CREATE - for a level that already has a view of that type
                (RENAME with several views of that type on the level: the level is skipped)
    sep       : separator between prefix / level name / suffix
    Returns a list of action dicts:
      {'kind', 'level', 'level_id', 'name', 'action', 'note', 'view_id', 'old_name'}
      action: 'create'   a new view is created
              'rename'   the view 'view_id' ('old_name') is renamed
              'ok'       a view with the wanted name already exists on that level - nothing to do
              'skip'     nothing is done (the note says why)
    """
    wanted_levels = set(int(i) for i in level_ids)
    lvls = [lv for lv in levels(doc) if eid_int(lv.Id) in wanted_levels]
    actions = []
    for kind in kinds:
        views = plan_views(doc, kind)
        used = set(v.Name for v in views)               # names are unique per view type
        by_level = {}
        for v in views:
            if not _is_dependent(v):
                by_level.setdefault(_level_id(v), []).append(v)
        for lv in lvls:
            lid = eid_int(lv.Id)
            name = make_name(prefix, lv.Name, suffix, sep)
            act = {'kind': kind, 'level': lv.Name, 'level_id': lid, 'name': name, 'action': 'skip',
                   'note': u'', 'view_id': None, 'old_name': u''}
            here = sorted(by_level.get(lid, []), key=lambda v: v.Name.lower())
            same = [v for v in here if v.Name == name]
            if not name:
                act['note'] = u'the name is empty'
            elif same:
                act['action'] = 'ok'
                act['view_id'] = eid_int(same[0].Id)
                act['note'] = u'already there'
            elif name in used:
                act['note'] = u'the name is already used by another %s' % KIND_LABEL[kind].lower()
            elif not here:
                act['action'] = 'create'
                used.add(name)
            elif existing == CREATE:
                act['action'] = 'create'
                act['note'] = u'one more view - the level already has: ' + u', '.join(v.Name for v in here[:4])
                used.add(name)
            elif existing == RENAME:
                if len(here) == 1:
                    act['action'] = 'rename'
                    act['view_id'] = eid_int(here[0].Id)
                    act['old_name'] = here[0].Name
                    used.discard(here[0].Name)
                    used.add(name)
                else:
                    act['note'] = (u'%d views of this type on the level (%s) - not renamed, it is not clear which one'
                                   % (len(here), u', '.join(v.Name for v in here[:4])))
            else:
                act['note'] = u'level already has: ' + u', '.join(v.Name for v in here[:4])
            actions.append(act)
    return actions


def apply_plan(doc, actions, settings):
    """Carry out the 'create' / 'rename' actions. Must run inside a transaction.

    settings: {kind: {'type_id': int, 'template_id': int or None}}
    Returns {'created': [view ids], 'renamed': n, 'templated': n, 'failed': [text], 'first': view or None}
    """
    report = {'created': [], 'renamed': 0, 'templated': 0, 'failed': [], 'first': None}
    for act in actions:
        kind = act['kind']
        label = u'%s "%s"' % (KIND_LABEL[kind], act['name'])
        try:
            if act['action'] == 'create':
                cfg = settings.get(kind) or {}
                if not cfg.get('type_id'):
                    report['failed'].append(u'%s: no view type chosen' % label)
                    continue
                view = DB.ViewPlan.Create(doc, make_eid(cfg['type_id']), make_eid(act['level_id']))
                try:
                    view.Name = act['name']
                except Exception as ex:
                    report['failed'].append(u'%s: created as "%s" - the name was refused (%s)'
                                            % (label, view.Name, ex))
                report['created'].append(eid_int(view.Id))
                if report['first'] is None:
                    report['first'] = view
                tid = cfg.get('template_id')
                if tid:
                    template = make_eid(tid)
                    if view.IsValidViewTemplate(template):
                        view.ViewTemplateId = template
                        report['templated'] += 1
                    else:
                        report['failed'].append(u'%s: the template does not fit this view type' % label)
            elif act['action'] == 'rename':
                view = doc.GetElement(make_eid(act['view_id']))
                if view is None:
                    report['failed'].append(u'%s: the view to rename no longer exists' % label)
                    continue
                view.Name = act['name']
                report['renamed'] += 1
        except Exception as ex:
            report['failed'].append(u'%s: %s' % (label, ex))
    return report


def assign_template(doc, view_ids, template_id):
    """Give the views a view template (template_id None = remove the template). Inside a transaction.
    Returns {'changed': n, 'same': n, 'unfit': [view names], 'failed': [text]}"""
    report = {'changed': 0, 'same': 0, 'unfit': [], 'failed': []}
    target = make_eid(template_id) if template_id else DB.ElementId.InvalidElementId
    for i in view_ids:
        view = doc.GetElement(make_eid(i))
        if view is None:
            continue
        try:
            if eid_int(view.ViewTemplateId) == eid_int(target):
                report['same'] += 1
                continue
            if template_id and not view.IsValidViewTemplate(target):
                report['unfit'].append(view.Name)
                continue
            view.ViewTemplateId = target
            report['changed'] += 1
        except Exception as ex:
            report['failed'].append(u'%s: %s' % (view.Name, ex))
    return report


def describe_plan(actions):
    """Short text of a plan, for the preview."""
    counts = {}
    for a in actions:
        counts[a['action']] = counts.get(a['action'], 0) + 1
    head = (u'Create: %d    Rename: %d    Already there: %d    Skip: %d'
            % (counts.get('create', 0), counts.get('rename', 0), counts.get('ok', 0), counts.get('skip', 0)))
    lines = [head, u'']
    for a in actions:
        kind = KIND_LABEL[a['kind']]
        if a['action'] == 'create':
            lines.append(u'+ %s  "%s"%s' % (kind, a['name'], (u'  - ' + a['note']) if a['note'] else u''))
        elif a['action'] == 'rename':
            lines.append(u'~ %s  "%s"  ->  "%s"' % (kind, a['old_name'], a['name']))
        elif a['action'] == 'ok':
            lines.append(u'= %s  "%s"  - already there' % (kind, a['name']))
        else:
            lines.append(u'- %s  %s  - skipped: %s' % (kind, a['level'], a['note']))
    return u'\n'.join(lines)
