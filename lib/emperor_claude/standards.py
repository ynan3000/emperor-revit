# -*- coding: utf-8 -*-
"""Emperor Claude Connector - Learn Standards (company profile).

Reads the open model once and learns how this company names and builds things: filter prefix and
separator, system types and abbreviations, sheet number pattern, view / view template naming, duct /
pipe types in use, tag types, text styles, shared parameters, levels. The result is a COMPANY PROFILE
kept only on this PC (%APPDATA%\\Emperor\\standards\\<company>.json), keyed by the organisation in
Project Information, and it grows with every project of that company. Nothing of it is shipped with
Emperor or the public skill.

learn(request)  action = learn (default) | get | set | unset
Returns (http_status, dict). IronPython 2.7 compatible.
"""
import os
import re
import json
import time

from pyrevit import DB, HOST_APP

from emperor_claude import settings

SEPARATORS = ['_', '-', ' ', '.']
MAX_LIST = 12


def _doc():
    return HOST_APP.doc


def _u(v):
    try:
        return u'%s' % v if v is not None else u''
    except Exception:
        return u''


def _name(e):
    """Element name - also for ElementTypes, whose .Name is hidden in IronPython."""
    if e is None:
        return u''
    for get in (lambda: e.Name, lambda: DB.Element.Name.__get__(e), lambda: DB.Element.Name.GetValue(e)):
        try:
            v = _u(get())
            if v:
                return v
        except Exception:
            pass
    for bip in (DB.BuiltInParameter.ALL_MODEL_TYPE_NAME, DB.BuiltInParameter.SYMBOL_NAME_PARAM):
        try:
            p = e.get_Parameter(bip)
            if p is not None and p.AsString():
                return _u(p.AsString())
        except Exception:
            pass
    return u''


def _dir():
    folder = os.path.join(settings.settings_dir(), 'standards')
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except OSError:
            pass
    return folder


def company_of(doc):
    """Company name from Project Information (organisation, then client)."""
    pi = doc.ProjectInformation
    for getter in (lambda: pi.OrganizationName, lambda: pi.OrganizationDescription, lambda: pi.ClientName,
                   lambda: pi.Author):
        try:
            v = _u(getter()).strip()
            if v and v.lower() not in ('owner', 'organization name', 'client name', 'author', 'enter address here'):
                return v
        except Exception:
            pass
    return u'My company'


def _key(company):
    k = re.sub(r'[^A-Za-z0-9]+', '_', company).strip('_')
    return k or 'default'


def profile_path(doc):
    return os.path.join(_dir(), _key(company_of(doc)) + '.json')


def _load(path):
    try:
        with open(path, 'rb') as f:
            return json.loads(f.read().decode('utf-8-sig'))
    except Exception:
        return {}


def _save(path, data):
    data['updated'] = time.strftime('%Y-%m-%d %H:%M')
    with open(path, 'wb') as f:
        f.write(json.dumps(data, indent=1, ensure_ascii=False).encode('utf-8'))


# ---------------------------------------------------------------- pattern helpers
def _count(items):
    out = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def _top(counts, n=MAX_LIST):
    return [k for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def prefix_rule(names):
    """Most common short prefix + separator, e.g. ('ABC', '_', 0.8). None when there is no clear one."""
    found = []
    for n in names:
        n = _u(n).strip()
        best = None
        for sep in SEPARATORS:
            i = n.find(sep)
            if 0 < i <= 8 and (best is None or i < best[0]):
                best = (i, sep)
        if best:
            found.append((n[:best[0]], best[1]))
    if not found or not names:
        return None
    counts = _count(found)
    (pre, sep), hits = sorted(counts.items(), key=lambda kv: -kv[1])[0]
    share = float(hits) / len(names)
    if hits < 2 or share < 0.3:
        return None
    return {'prefix': pre, 'separator': sep, 'share': round(share, 2)}


def case_style(names):
    names = [n for n in names if re.search('[A-Za-z]', n)]
    if not names:
        return None
    up = sum(1 for n in names if n == n.upper())
    if up >= 0.7 * len(names):
        return 'UPPER CASE'
    title = sum(1 for n in names if n == n.title())
    if title >= 0.6 * len(names):
        return 'Title Case'
    return 'Mixed'


def number_pattern(values):
    """Sheet-number style pattern: fixed parts kept, changing letters -> A, digits -> 9 (e.g. B99-HV-999-AA)."""
    toks = [re.split(r'([-_. ])', _u(v).strip()) for v in values if _u(v).strip()]
    if not toks:
        return None
    by_len = {}
    for t in toks:
        by_len.setdefault(len(t), []).append(t)
    group = sorted(by_len.values(), key=lambda g: -len(g))[0]
    out = []
    for i in range(len(group[0])):
        col = [t[i] for t in group]
        if len(set(col)) == 1:
            out.append(col[0])
        elif len(set(len(c) for c in col)) == 1:
            chars = []
            for j in range(len(col[0])):
                pos = set(c[j] for c in col)
                if len(pos) == 1:
                    chars.append(col[0][j])
                elif all(ch.isdigit() for ch in pos):
                    chars.append('#')
                elif all(ch.isalpha() for ch in pos):
                    chars.append('A')
                else:
                    chars.append('?')
            out.append(''.join(chars))
        else:
            out.append('*')
    return {'pattern': u''.join(out), 'legend': '# digit, A letter, ? digit or letter, * varies',
            'share': round(float(len(group)) / len(toks), 2)}


# ---------------------------------------------------------------- reading the model
def _collect(doc, cls):
    try:
        return list(DB.FilteredElementCollector(doc).OfClass(cls))
    except Exception:
        return []


def _type_counts(doc, cls):
    counts = {}
    for e in _collect(doc, cls):
        try:
            t = doc.GetElement(e.GetTypeId())
            n = _name(t) if t is not None else u'?'
            counts[n] = counts.get(n, 0) + 1
        except Exception:
            pass
    return counts


def read_model(doc):
    data = {}
    # filters
    filters = [_name(f) for f in _collect(doc, DB.ParameterFilterElement)]
    data['filters'] = {'count': len(filters), 'rule': prefix_rule(filters), 'examples': sorted(filters)[:MAX_LIST]}
    # system types
    systems = []
    for cls in (getattr(DB.Mechanical, 'MechanicalSystemType', None), getattr(DB.Plumbing, 'PipingSystemType', None)):
        if cls is None:
            continue
        for st in _collect(doc, cls):
            try:
                p = st.get_Parameter(DB.BuiltInParameter.RBS_SYSTEM_ABBREVIATION_PARAM)
                ab = _u(p.AsString()) if p is not None else u''
            except Exception:
                ab = u''
            systems.append({'name': _name(st), 'abbreviation': ab, 'kind': 'duct' if 'Mechanical' in cls.__name__ else 'pipe'})
    data['system_types'] = systems[:40]
    # views and templates
    views = [v for v in _collect(doc, DB.View)]
    templates = sorted(_name(v) for v in views if v.IsTemplate)
    data['view_templates'] = {'rule': prefix_rule(templates), 'names': templates[:MAX_LIST]}
    plans = [_name(v) for v in views if not v.IsTemplate and v.ViewType in (DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan)]
    data['plan_views'] = {'count': len(plans), 'case': case_style(plans), 'rule': prefix_rule(plans), 'examples': sorted(plans)[:8]}
    # sheets
    sheets = _collect(doc, DB.ViewSheet)
    numbers = [_u(s.SheetNumber) for s in sheets]
    data['sheets'] = {'count': len(sheets), 'number': number_pattern(numbers), 'name_case': case_style([_name(s) for s in sheets]),
                      'examples': sorted(numbers)[:6]}
    # types in use
    data['duct_types'] = _top(_type_counts(doc, DB.Mechanical.Duct), 8)
    data['pipe_types'] = _top(_type_counts(doc, DB.Plumbing.Pipe), 8)
    tags = {}
    for t in _collect(doc, DB.IndependentTag):
        try:
            ty = doc.GetElement(t.GetTypeId())
            fam = _u(ty.FamilyName) if ty is not None else u''
            n = (fam + u': ' + _name(ty)) if fam else _name(ty)
            tags[n] = tags.get(n, 0) + 1
        except Exception:
            pass
    data['tag_types'] = _top(tags, 10)
    data['text_types'] = sorted(_name(t) for t in _collect(doc, DB.TextNoteType))[:MAX_LIST]
    shared = sorted(_name(p) for p in _collect(doc, DB.SharedParameterElement))
    data['shared_parameters'] = {'count': len(shared), 'examples': shared[:30]}
    levels = sorted(_collect(doc, DB.Level), key=lambda l: l.Elevation)
    data['levels'] = {'case': case_style([_name(l) for l in levels]), 'names': [_name(l) for l in levels][:MAX_LIST]}
    return data


# ---------------------------------------------------------------- summary
def summary(profile):
    """A few short lines Claude can follow - this is what goes into session_brief."""
    if not profile:
        return u''
    lines = [u'Company standards: %s (learned from %d project(s)).' % (profile.get('company'), len(profile.get('projects', {})))]
    learned = profile.get('learned') or {}
    f = (learned.get('filters') or {}).get('rule')
    if f:
        lines.append(u'Filters: prefix "%s" + "%s" (e.g. %s%sSupply Air Duct).' % (f['prefix'], f['separator'], f['prefix'], f['separator']))
    vt = (learned.get('view_templates') or {}).get('rule')
    if vt:
        lines.append(u'View templates: prefix "%s" + "%s".' % (vt['prefix'], vt['separator']))
    pv = learned.get('plan_views') or {}
    if pv.get('examples'):
        lines.append(u'Plan views: %s, e.g. "%s".' % (pv.get('case') or 'mixed case', pv['examples'][0]))
    sh = (learned.get('sheets') or {}).get('number')
    if sh:
        lines.append(u'Sheet numbers: %s  (# digit, A letter, * varies), e.g. %s.' % (
            sh['pattern'], ((learned.get('sheets') or {}).get('examples') or [u''])[0]))
    sy = learned.get('system_types') or []
    if sy:
        lines.append(u'Systems: ' + u', '.join(u'%s (%s)' % (s['name'], s['abbreviation']) if s.get('abbreviation') else s['name']
                                               for s in sy[:10]) + u'.')
    if learned.get('duct_types'):
        lines.append(u'Duct types in use: ' + u', '.join(learned['duct_types'][:4]) + u'.')
    if learned.get('pipe_types'):
        lines.append(u'Pipe types in use: ' + u', '.join(learned['pipe_types'][:4]) + u'.')
    if learned.get('tag_types'):
        lines.append(u'Tags in use: ' + u', '.join(learned['tag_types'][:5]) + u'.')
    for k, v in sorted((profile.get('rules') or {}).items()):
        lines.append(u'Rule - %s: %s' % (k, v))
    return u'\n'.join(lines)


def _merge(old, new):
    """Union of the lists of earlier projects and this one; the rules are re-learned from the union."""
    if not old:
        return new
    out = dict(new)
    for key in ('duct_types', 'pipe_types', 'tag_types', 'text_types'):
        seen = list(new.get(key) or [])
        for x in old.get(key) or []:
            if x not in seen:
                seen.append(x)
        out[key] = seen[:MAX_LIST]
    names = {}
    for s in (old.get('system_types') or []) + (new.get('system_types') or []):
        names[s['name']] = s
    out['system_types'] = list(names.values())[:40]
    return out


def learn(request=None):
    body = request if isinstance(request, dict) else {}
    doc = _doc()
    if doc is None:
        return 409, {'error': 'No Revit project is open.'}
    action = (body.get('action') or 'learn').lower()
    path = profile_path(doc)
    profile = _load(path)
    profile.setdefault('company', company_of(doc))
    profile.setdefault('projects', {})
    profile.setdefault('rules', {})
    if action == 'set':
        key = _u(body.get('key')).strip()
        if not key:
            return 400, {'error': 'key is required for action=set.'}
        profile['rules'][key] = body.get('value')
        _save(path, profile)
        return 200, {'saved': key, 'summary': summary(profile)}
    if action == 'unset':
        profile['rules'].pop(_u(body.get('key')).strip(), None)
        _save(path, profile)
        return 200, {'summary': summary(profile)}
    if action == 'get':
        if not profile.get('learned'):
            return 200, {'company': profile['company'], 'summary': u'',
                         'hint': 'Nothing learned for this company yet - call learn_standards (action=learn).'}
        return 200, {'company': profile['company'], 'summary': summary(profile), 'file': os.path.basename(path)}
    data = read_model(doc)
    profile['learned'] = _merge(profile.get('learned'), data)
    try:
        title = _u(doc.Title)
    except Exception:
        title = u'project'
    profile['projects'][title] = time.strftime('%Y-%m-%d')
    _save(path, profile)
    out = {'company': profile['company'], 'summary': summary(profile), 'file': os.path.basename(path)}
    if body.get('details'):
        out['learned'] = data
    return 200, out


def brief_line(doc):
    """Short company-standards text for session_brief ('' when nothing is learned yet)."""
    try:
        return summary(_load(profile_path(doc)))
    except Exception:
        return u''
