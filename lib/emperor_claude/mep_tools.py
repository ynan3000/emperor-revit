# -*- coding: utf-8 -*-
"""Emperor Claude Connector - token-saving and HVAC tools (Revit side).

project memory   one compact, per-project file with the model facts + the user's standards and notes
summarize        counts / sums grouped by parameters instead of long element lists
model_check      open connectors, elements without a system, terminals without flow
size_ducts       size ducts from their airflow and a target velocity (preview by default)
tag_view         Smart Tag through Claude
add_insulation   Smart Insulation through Claude
Every function returns (http_status, dict). IronPython 2.7 compatible.
"""
import os
import json
import math
import time

from pyrevit import DB, HOST_APP

from emperor_claude import settings


def _core():
    from emperor_claude import core
    return core


def _doc():
    return HOST_APP.doc


def _flag(body, key, default):
    v = body.get(key, default)
    if isinstance(v, (str, type(u''))):
        return v.strip().lower() in ('1', 'true', 'yes')
    return bool(v)


# ============================================================================ project memory
def _memory_dir():
    folder = os.path.join(settings.settings_dir(), 'projects')
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except OSError:
            pass
    return folder


def memory_path(doc):
    from emperor_mep.common import project_key
    return os.path.join(_memory_dir(), project_key(doc) + '.json')


def _load_memory(doc):
    try:
        with open(memory_path(doc), 'rb') as f:
            return json.loads(f.read().decode('utf-8-sig'))
    except Exception:
        return {}


def _save_memory(doc, data):
    data['updated'] = time.strftime('%Y-%m-%d %H:%M')
    with open(memory_path(doc), 'wb') as f:
        f.write(json.dumps(data, indent=1, ensure_ascii=False).encode('utf-8'))


def _names(doc, cls):
    c = _core()
    return sorted(c._name(t) for t in DB.FilteredElementCollector(doc).OfClass(cls))


def _snapshot(doc):
    """Compact model facts. Lists of names only - no ids, no nested objects."""
    from Autodesk.Revit.DB import Mechanical, Plumbing
    c = _core()
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.ProjectElevation)
    links = []
    for row in c._links()[1].get('links', []):
        links.append(u'%s (%s, %s inst.)' % (row.get('name'), row.get('status'), row.get('instance_count')))
    sheet_views = set(c._eid_int(vp.ViewId) for vp in DB.FilteredElementCollector(doc).OfClass(DB.Viewport))
    plans = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan):
        if v.IsTemplate:
            continue
        tpl = u''
        try:
            if c._eid_int(v.ViewTemplateId) != -1:
                tpl = c._name(doc.GetElement(v.ViewTemplateId))
        except Exception:
            pass
        plans.append(u'%s | %s | %s%s' % (v.Name, v.GenLevel.Name if v.GenLevel else u'-', tpl or u'no template',
                                          u' | on sheet' if c._eid_int(v.Id) in sheet_views else u''))
    plans.sort()
    terminals = sorted(set(
        u'%s : %s' % (getattr(s, 'FamilyName', u''), c._name(s))
        for s in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_DuctTerminal).WhereElementIsElementType()))
    snap = {
        'levels': [[l.Name, round(l.ProjectElevation * 0.3048, 3)] for l in levels],
        'links': links,
        'duct_types': _names(doc, Mechanical.DuctType),
        'duct_systems': _names(doc, Mechanical.MechanicalSystemType),
        'duct_insulation': _names(doc, Mechanical.DuctInsulationType),
        'pipe_types': _names(doc, Plumbing.PipeType),
        'pipe_systems': _names(doc, Plumbing.PipingSystemType),
        'pipe_insulation': _names(doc, Plumbing.PipeInsulationType),
        'air_terminal_types': terminals[:60],
        'plan_views': plans[:60],
        'plan_view_count': len(plans),
        'spaces': len(list(DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType())),
    }
    return snap


def memory(request=None):
    """Get / update the project memory. Actions: get (default), refresh, set, unset, note, clear_notes."""
    doc = _doc()
    if doc is None:
        return 409, {'error': 'No Revit project is open.'}
    body = request if isinstance(request, dict) else {}
    action = (body.get('action') or 'get').strip().lower()
    mem = _load_memory(doc)
    mem.setdefault('standards', {})
    mem.setdefault('notes', [])
    changed = []
    if action == 'set':
        key = (body.get('key') or u'').strip()
        if not key:
            return 400, {'error': "'key' is required, e.g. 'supply duct type'."}
        mem['standards'][key] = body.get('value')
    elif action == 'unset':
        mem['standards'].pop((body.get('key') or u'').strip(), None)
    elif action == 'note':
        text = (u'%s' % (body.get('note') or u'')).strip().replace(u'\n', u' ')
        if text:
            mem['notes'].append(text)
            mem['notes'] = mem['notes'][-80:]
    elif action == 'clear_notes':
        mem['notes'] = []

    old = mem.get('model') or {}
    if action == 'refresh' or not old or body.get('_refresh_model', True):
        new = _snapshot(doc)
        if old:
            changed = [k for k in new if new.get(k) != old.get(k)]
        mem['model'] = new
    c = _core()
    proj = c._project()[1]
    mem['project'] = {'name': proj.get('project_name') or proj.get('title'), 'number': proj.get('project_number'),
                      'file': os.path.basename(proj.get('path') or u'') or None}
    _save_memory(doc, mem)
    out = dict(mem)
    out['changed_since_last_visit'] = changed
    out['memory_file'] = os.path.basename(memory_path(doc))
    if not mem['standards']:
        out['hint'] = ("No standards saved yet. When the user tells you a project rule (duct type for supply, "
                       "ceiling height, naming), save it with project_memory action=set so the next chat knows it.")
    return 200, out


def brief(request=None):
    """session_brief = project memory + the live state (active view, access switches, scripts)."""
    body = request if isinstance(request, dict) else {}
    if body.get('append_note'):
        memory({'action': 'note', 'note': body.get('append_note'), '_refresh_model': False})
    if body.get('replace_notes') is not None:
        doc = _doc()
        if doc is not None:
            mem = _load_memory(doc)
            mem['notes'] = [l.strip(u'- ').strip() for l in (u'%s' % body['replace_notes']).splitlines() if l.strip()]
            _save_memory(doc, mem)
    status, out = memory({'action': 'get'})
    if status != 200:
        return status, out
    c = _core()
    doc = _doc()
    cfg = settings.load()
    out['active_view'] = doc.ActiveView.Name if doc.ActiveView else None
    try:
        from emperor_claude import standards as _st
        line = _st.brief_line(doc)
        out['company_standards'] = line or ('Not learned yet for this company - call learn_standards once, '
                                            'then follow it when naming or creating anything.')
    except Exception:
        pass
    out['write_access'] = bool(cfg.get('allow_write'))
    out['scripting_access'] = bool(cfg.get('allow_scripts'))
    try:
        out['scripts'] = [r['name'] for r in c._list_scripts()[1]['scripts']]
    except Exception:
        out['scripts'] = []
    legacy = os.path.join(settings.settings_dir(), 'project_notes.md')
    if os.path.isfile(legacy) and not out.get('notes'):
        try:
            out['older_shared_notes'] = c._read_text(legacy)[-1500:]
        except Exception:
            pass
    return 200, out


# ============================================================================ element filters
def _elements(doc, body, cat_id=None, bics=None):
    """Elements by category with optional level / active-view / ids filters."""
    c = _core()
    view = doc.ActiveView if _flag(body, 'in_active_view', False) else None
    ids = body.get('element_ids')
    out = []
    if ids:
        for n in ids[:5000]:
            e = c._get_element(doc, n)
            if e is not None:
                out.append(e)
    else:
        cats = [cat_id] if cat_id is not None else []
        for b in bics or []:
            cats.append(DB.ElementId(b))
        for cid in cats:
            col = DB.FilteredElementCollector(doc, view.Id) if view is not None else DB.FilteredElementCollector(doc)
            out.extend(list(col.OfCategoryId(cid).WhereElementIsNotElementType()))
    level = (body.get('level') or u'').strip().lower()
    if level:
        keep = []
        for e in out:
            if _level_name(doc, e).lower() == level:
                keep.append(e)
        out = keep
    return out


def _level_name(doc, e):
    try:
        lid = e.LevelId
        if lid is not None and _core()._eid_int(lid) != -1:
            return doc.GetElement(lid).Name
    except Exception:
        pass
    for bip in (DB.BuiltInParameter.RBS_START_LEVEL_PARAM, DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM):
        try:
            p = e.get_Parameter(bip)
            if p is not None and p.HasValue:
                lv = doc.GetElement(p.AsElementId())
                if lv is not None:
                    return lv.Name
        except Exception:
            pass
    return u''


def _display_number(doc, p):
    """A double parameter in the project's display units (e.g. m, mm, L/s)."""
    v = p.AsDouble()
    try:
        spec = p.Definition.GetDataType()
        unit = doc.GetUnits().GetFormatOptions(spec).GetUnitTypeId()
        return DB.UnitUtils.ConvertFromInternalUnits(v, unit)
    except Exception:
        return v


# ============================================================================ summarize
def summarize(request):
    doc = _doc()
    if doc is None:
        return 409, {'error': 'No Revit project is open.'}
    c = _core()
    body = request if isinstance(request, dict) else {}
    cat, sugg = c._find_category(doc, body.get('category') or u'')
    if cat is None and not body.get('element_ids'):
        return 400, {'error': 'Category not found. Close matches: %s' % sugg}
    group_by = body.get('group_by') or ['Family and Type']
    sums = body.get('sum') or []
    elems = _elements(doc, body, cat.Id if cat is not None else None)
    groups = {}
    for e in elems:
        key = []
        for g in group_by:
            if g.lower() == 'level':
                key.append(_level_name(doc, e))
            else:
                key.append(u'%s' % (c._param_value(c._lookup(doc, e, g)) or u'-'))
        key = tuple(key)
        row = groups.setdefault(key, {'count': 0, 'sums': [0.0] * len(sums)})
        row['count'] += 1
        for i, s in enumerate(sums):
            p = c._lookup(doc, e, s)
            if p is not None and p.StorageType == DB.StorageType.Double and p.HasValue:
                row['sums'][i] += _display_number(doc, p)
    rows = []
    for key, row in sorted(groups.items(), key=lambda kv: -kv[1]['count'])[:200]:
        rows.append(list(key) + [row['count']] + [round(x, 3) for x in row['sums']])
    return 200, {'category': cat.Name if cat is not None else None, 'elements': len(elems), 'groups': len(groups),
                 'columns': list(group_by) + ['count'] + ['sum ' + s for s in sums], 'rows': rows}


# ============================================================================ model check
_CHECK_CATS = [
    ('Ducts', DB.BuiltInCategory.OST_DuctCurves), ('Flex Ducts', DB.BuiltInCategory.OST_FlexDuctCurves),
    ('Duct Fittings', DB.BuiltInCategory.OST_DuctFitting), ('Duct Accessories', DB.BuiltInCategory.OST_DuctAccessory),
    ('Air Terminals', DB.BuiltInCategory.OST_DuctTerminal), ('Mechanical Equipment', DB.BuiltInCategory.OST_MechanicalEquipment),
    ('Pipes', DB.BuiltInCategory.OST_PipeCurves), ('Flex Pipes', DB.BuiltInCategory.OST_FlexPipeCurves),
    ('Pipe Fittings', DB.BuiltInCategory.OST_PipeFitting), ('Pipe Accessories', DB.BuiltInCategory.OST_PipeAccessory),
    ('Plumbing Fixtures', DB.BuiltInCategory.OST_PlumbingFixtures),
]


def model_check(request):
    doc = _doc()
    if doc is None:
        return 409, {'error': 'No Revit project is open.'}
    from emperor_mep.common import connectors_of
    c = _core()
    body = request if isinstance(request, dict) else {}
    cap = max(5, min(int(body.get('max_ids') or 25), 200))
    issues = {}

    def add(kind, label, e):
        d = issues.setdefault(kind, {})
        row = d.setdefault(label, {'count': 0, 'ids': []})
        row['count'] += 1
        if len(row['ids']) < cap:
            row['ids'].append(c._eid_int(e.Id))

    phys = set([DB.ConnectorType.End, DB.ConnectorType.Curve])
    checked = 0
    for label, bic in _CHECK_CATS:
        for e in _elements(doc, body, None, [bic]):
            checked += 1
            conns = connectors_of(e)
            open_end = False
            for cn in conns:
                try:
                    if cn.ConnectorType in phys and cn.Domain in (DB.Domain.DomainHvac, DB.Domain.DomainPiping) \
                            and not cn.IsConnected:
                        open_end = True
                        break
                except Exception:
                    pass
            if open_end and label not in ('Mechanical Equipment', 'Plumbing Fixtures'):
                add('open_connectors', label, e)
            if label in ('Ducts', 'Pipes', 'Flex Ducts', 'Flex Pipes'):
                try:
                    if e.MEPSystem is None:
                        add('no_system', label, e)
                except Exception:
                    pass
            if label == 'Air Terminals':
                no_sys = True
                for cn in conns:
                    try:
                        if cn.MEPSystem is not None:
                            no_sys = False
                    except Exception:
                        pass
                if no_sys:
                    add('terminal_without_system', label, e)
                try:
                    p = e.get_Parameter(DB.BuiltInParameter.RBS_DUCT_FLOW_PARAM)
                    if p is not None and p.HasValue and abs(p.AsDouble()) < 1e-9:
                        add('terminal_zero_flow', label, e)
                except Exception:
                    pass
    summary = dict((k, dict((lbl, v['count']) for lbl, v in d.items())) for k, d in issues.items())
    return 200, {'checked_elements': checked, 'summary': summary, 'issues': issues,
                 'note': 'Ids are capped at max_ids per check. Use view_snapshot(element_ids=...) to look at them.'}


# ============================================================================ duct sizing
def size_ducts(request):
    doc = _doc()
    if doc is None:
        return 409, {'error': 'No Revit project is open.'}
    c = _core()
    body = request if isinstance(request, dict) else {}
    dry = _flag(body, 'dry_run', True)
    if not dry:
        guard = c._write_guard()
        if guard:
            return guard
    v = float(body.get('velocity_ms') or 5.0)
    step = float(body.get('step_mm') or 50.0)
    min_mm = float(body.get('min_mm') or 100.0)
    fixed_h = body.get('height_mm')
    system = (body.get('system_name') or u'').strip().lower()
    ducts = [e for e in _elements(doc, body, None, [DB.BuiltInCategory.OST_DuctCurves])
             if isinstance(e, DB.MEPCurve)]
    plan, skipped = [], {'no_flow': 0, 'other_system': 0, 'unchanged': 0}
    for d in ducts:
        if system:
            try:
                sname = c._name(doc.GetElement(d.get_Parameter(DB.BuiltInParameter.RBS_DUCT_SYSTEM_TYPE_PARAM).AsElementId()))
            except Exception:
                sname = u''
            if (sname or u'').lower() != system:
                skipped['other_system'] += 1
                continue
        p = d.get_Parameter(DB.BuiltInParameter.RBS_DUCT_FLOW_PARAM)
        q = p.AsDouble() * 0.028316846592 if (p is not None and p.HasValue) else 0.0   # m3/s
        if q <= 1e-6:
            skipped['no_flow'] += 1
            continue
        pd = d.get_Parameter(DB.BuiltInParameter.RBS_CURVE_DIAMETER_PARAM)
        round_duct = pd is not None and pd.HasValue and pd.AsDouble() > 0 and not pd.IsReadOnly
        if round_duct:
            dia = math.sqrt(4.0 * q / (math.pi * v)) * 1000.0
            new = max(min_mm, math.ceil(dia / step) * step)
            old = round(pd.AsDouble() * 304.8)
            if abs(new - old) < 0.5:
                skipped['unchanged'] += 1
                continue
            plan.append([c._eid_int(d.Id), round(q * 1000, 1), u'%d' % old, u'%d' % new, ('d', new)])
        else:
            pw = d.get_Parameter(DB.BuiltInParameter.RBS_CURVE_WIDTH_PARAM)
            ph = d.get_Parameter(DB.BuiltInParameter.RBS_CURVE_HEIGHT_PARAM)
            if pw is None or ph is None:
                continue
            h = float(fixed_h) if fixed_h else ph.AsDouble() * 304.8
            w = max(min_mm, math.ceil((q / (v * h / 1000.0)) * 1000.0 / step) * step)
            old = u'%dx%d' % (round(pw.AsDouble() * 304.8), round(ph.AsDouble() * 304.8))
            new = u'%dx%d' % (w, h)
            if old == new:
                skipped['unchanged'] += 1
                continue
            plan.append([c._eid_int(d.Id), round(q * 1000, 1), old, new, ('wh', w, h)])
    out = {'velocity_ms': v, 'ducts_checked': len(ducts), 'to_change': len(plan), 'skipped': skipped,
           'columns': ['id', 'flow_l_s', 'old_size', 'new_size'], 'rows': [r[:4] for r in plan[:300]]}
    if dry or not plan:
        out['dry_run'] = dry
        if dry:
            out['note'] = 'Preview only. Show it to the user; call again with dry_run=false to apply (one undo step).'
        return 200, out
    t, sink = c._begin(doc, 'Emperor Claude: size ducts')
    failed = 0
    try:
        for row in plan:
            d = doc.GetElement(c._make_eid(row[0]))
            try:
                if row[4][0] == 'd':
                    d.get_Parameter(DB.BuiltInParameter.RBS_CURVE_DIAMETER_PARAM).Set(row[4][1] / 304.8)
                else:
                    d.get_Parameter(DB.BuiltInParameter.RBS_CURVE_WIDTH_PARAM).Set(row[4][1] / 304.8)
                    d.get_Parameter(DB.BuiltInParameter.RBS_CURVE_HEIGHT_PARAM).Set(row[4][2] / 304.8)
            except Exception:
                failed += 1
        c._commit(t, sink)
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
        raise
    out['applied'] = len(plan) - failed
    out['failed'] = failed
    out['revit_messages'] = c._dedupe(sink)
    return 200, out


# ============================================================================ tagging / insulation
def tag_view(request):
    doc = _doc()
    if doc is None:
        return 409, {'error': 'No Revit project is open.'}
    c = _core()
    guard = c._write_guard()
    if guard:
        return guard
    from emperor_mep import tagging
    from emperor_mep.common import type_label
    body = request if isinstance(request, dict) else {}
    view = doc.ActiveView
    if body.get('view_name'):
        view = None
        for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
            if not v.IsTemplate and v.Name == body.get('view_name'):
                view = v
                break
        if view is None:
            return 404, {'error': "No view named '%s'." % body.get('view_name')}
    keys = body.get('categories') or ['ducts', 'pipes', 'terminals', 'equipment']
    types = body.get('tag_types') or {}
    rules, missing = [], []
    for k in keys:
        if k not in tagging.CATEGORY_INDEX:
            missing.append(k)
            continue
        rule = {'key': k, 'orientation': body.get('orientation') or 'auto'}
        want = (types.get(k) or u'').lower()
        if want:
            for s in tagging.tag_types(doc, k):
                if want in type_label(s).lower():
                    rule['tag_type_id'] = s.Id
                    break
        rules.append(rule)
    if missing:
        return 400, {'error': 'Unknown categories %s. Use: %s' % (missing, [x[0] for x in tagging.CATEGORIES])}
    t, sink = c._begin(doc, 'Emperor Claude: Smart Tag')
    try:
        report = tagging.run(doc, view, rules, skip_tagged=_flag(body, 'skip_tagged', True),
                             leader=_flag(body, 'leader', False), avoid_overlap=_flag(body, 'avoid_overlap', True),
                             min_length_mm=float(body.get('min_length_mm') or 1000), offset_mm=float(body.get('offset_mm') or 2),
                             skip_zero_flow=_flag(body, 'skip_zero_flow', True), place_anyway=_flag(body, 'place_anyway', False),
                             always_horizontal=_flag(body, 'always_horizontal', False),
                             use_learned=_flag(body, 'use_learned', True),
                             ids=[c._make_eid(i) for i in body.get('element_ids')] if body.get('element_ids') else None)
        c._commit(t, sink)
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
        raise
    report.pop('new_tag_ids', None)
    report['view'] = view.Name
    return 200, report


def add_insulation(request):
    doc = _doc()
    if doc is None:
        return 409, {'error': 'No Revit project is open.'}
    c = _core()
    from emperor_mep import insulation
    body = request if isinstance(request, dict) else {}
    dry = _flag(body, 'dry_run', True)
    if not dry:
        guard = c._write_guard()
        if guard:
            return guard
    rules = body.get('rules') or []
    if not rules:
        return 400, {'error': "'rules' is required: [{kind: duct|pipe, system, insulation, thickness}]."}
    parts = body.get('parts') or ['curves', 'fittings']
    view = doc.ActiveView if (body.get('scope') == 'view') else None
    ids = [c._make_eid(i) for i in body.get('element_ids')] if body.get('element_ids') else None
    mode = body.get('mode') or 'update'
    if dry:
        report = insulation.run(doc, rules, mode, parts, view, ids, dry_run=True)
        report['dry_run'] = True
        report['note'] = 'Preview only. Call again with dry_run=false to apply (one undo step).'
        return 200, report
    t, sink = c._begin(doc, 'Emperor Claude: Smart Insulation')
    try:
        report = insulation.run(doc, rules, mode, parts, view, ids)
        c._commit(t, sink)
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
        raise
    report['revit_messages'] = c._dedupe(sink)
    return 200, report


def standards(request=None):
    from emperor_claude import standards as _st
    return _st.learn(request)


ROUTES = {
    '/standards': standards,
    '/memory': memory,
    '/summary': summarize,
    '/check': model_check,
    '/size_ducts': size_ducts,
    '/tag': tag_view,
    '/insulate': add_insulation,
}
