# -*- coding: ascii -*-
# Emperor Exporter - batch export of sheets and views.
# Tabs: Selection > Formats > Create.  Formats: PDF, DWG, DXF, DGN, DWF, DWFx, NWC, IFC, Images.
# Export option controls are generated from the option classes of the INSTALLED Revit API
# (reflection), so every writable bool / enum / text / number option is available and a
# property that does not exist in your Revit version is simply not shown.
from emperor_common import *
import Autodesk.Revit.DB as _RDB
from System.Windows import GridLength

FORMATS = [
    ('PDF', 'pdf', 'Portable document - one file per sheet/view, or one combined file'),
    ('DWG', 'dwg', 'AutoCAD drawing - export setups, xrefs, all DWG options'),
    ('DXF', 'dwg', 'AutoCAD exchange format'),
    ('DGN', 'dgn', 'MicroStation design file'),
    ('DWF', 'dwf', 'Autodesk Design Web Format'),
    ('DWFx', 'dwf', 'Design Web Format (XPS based)'),
    ('NWC', 'nwc', 'Navisworks cache - whole model or one 3D view'),
    ('IFC', 'ifc', 'Industry Foundation Classes - whole model or one 3D view'),
    ('Images', 'image_export', 'PNG / JPEG / TIFF / BMP pictures of sheets or views'),
]
FORMAT_NAMES = [f[0] for f in FORMATS]
MODEL_FORMATS = ['NWC', 'IFC']
OPT_CLASS = {'PDF': 'PDFExportOptions', 'DWG': 'DWGExportOptions', 'DXF': 'DXFExportOptions', 'DGN': 'DGNExportOptions',
             'DWF': 'DWFExportOptions', 'DWFx': 'DWFXExportOptions', 'NWC': 'NavisworksExportOptions', 'IFC': 'IFCExportOptions',
             'Images': 'ImageExportOptions'}
EXT = {'PDF': '.pdf', 'DWG': '.dwg', 'DXF': '.dxf', 'DGN': '.dgn', 'DWF': '.dwf', 'DWFx': '.dwfx', 'NWC': '.nwc', 'IFC': '.ifc'}
# properties handled by curated controls or by the exporter itself - never auto-generated
SKIP_PROPS = {
    'ALL': ['IsValidObject', 'ViewId', 'FilterViewId', 'FileName', 'FilePath', 'ViewName'],
    'PDF': ['Combine', 'OriginOffsetX', 'OriginOffsetY'],
    'DWG': ['MergedViews', 'HatchBackgroundColor'],
    'DXF': ['MergedViews', 'HatchBackgroundColor'],
    'NWC': ['ExportScope'],
    'Images': ['ExportRange'],
}
DEFAULT_OVERRIDES = {
    'PDF': {'HideScopeBoxes': True, 'HideReferencePlane': True, 'HideCropBoundaries': True, 'HideUnreferencedViewTags': True},
}
DEFAULT_RULE = '{SheetNumber}_{SheetName}_{Revision}'
DEFAULT_VIEW_RULE = '{ViewName}'
POLICIES = ['Add number if file exists', 'Overwrite existing files', 'Skip existing files']
SCHEDULE_UNSUPPORTED = ['DWG', 'DXF', 'DGN', 'Images']


OPTION_HELP = {
    # ---- PDF
    'AlwaysUseRaster': 'Print everything as a picture (raster). Bigger files, text cannot be selected; only for views with heavy shading.',
    'ColorDepth': 'Color = as on screen. GrayScale = shades of grey. BlackLine = every line black (clean construction drawings).',
    'ExportQuality': 'Resolution for the parts that are printed as pictures (shading, images). 300 DPI is normal, 600 for fine detail.',
    'HideCropBoundaries': 'Do not print the crop region frames of the views.',
    'HideReferencePlane': 'Do not print reference planes (the green dashed working lines).',
    'HideScopeBoxes': 'Do not print scope boxes.',
    'HideUnreferencedViewTags': 'Do not print section / elevation / callout marks that point to views not placed on any sheet.',
    'MaskCoincidentLines': 'Where two lines lie on top of each other, print only the one in front (cleaner, like on screen).',
    'PaperFormat': 'Paper size. Default = the size of the sheet (title block). Pick a size only to force one paper for all.',
    'PaperOrientation': 'Portrait, Landscape, or Auto (follows the sheet shape).',
    'PaperPlacement': 'Where the drawing sits on the paper: centred, lower-left corner (uses the offsets above), or inside margins.',
    'RasterQuality': 'Quality of the picture parts (shading, images, transparency). Higher = sharper but bigger file.',
    'ReplaceHalftoneWithThinLines': 'Print halftone elements (links, underlays) as thin lines instead of grey.',
    'StopOnError': 'Stop the whole export at the first problem instead of skipping the item and carrying on.',
    'ViewLinksInBlue': 'Print the links between views (sheet hyperlinks) in blue, like Revit shows them.',
    'ZoomPercentage': 'Print scale in percent when Zoom Type is "Zoom" (100 = real size).',
    'ZoomType': 'FitToPage = shrink / grow to the paper. Zoom = print at the percentage above.',
    # ---- DWG / DXF / DGN
    'ACAPreference': 'How Revit elements are written for AutoCAD Architecture: Object = as AutoCAD objects (keeps element data), Geometry = plain lines and solids (opens anywhere).',
    'Colors': 'IndexColors = the 255 AutoCAD colours (best for plot styles / CTB). TrueColor = exact RGB colours from Revit. TrueColorPerView = RGB colours as each view shows them.',
    'ExportOfSolids': '3D solids as Polymesh (surface mesh, opens everywhere) or ACIS (true solids, editable in AutoCAD 3D).',
    'ExportingAreas': 'Also export area and room boundaries as closed polylines (useful for area plans).',
    'FileVersion': 'AutoCAD / MicroStation version of the file. Default = the newest this Revit writes; pick an older one for older software.',
    'HatchPatternsFileName': 'Optional .pat file to map Revit fill patterns to AutoCAD hatch patterns. Empty = Revit default.',
    'HideScopeBox': 'Do not export scope boxes.',
    'HideUnreferenceViewTags': 'Do not export section / elevation / callout marks that point to views not placed on any sheet.',
    'LayerMapping': 'Layer standard: a name like "AIA", "ISO13567", "CP83", "BS1192", or the path of your own layer table (.txt). Empty = Revit default.',
    'LinetypesFileName': 'Optional .lin file to map Revit line patterns to AutoCAD linetypes. Empty = Revit default.',
    'LineScaling': 'How dashed lines are scaled: ViewScale (as in the view), ModelSpace (LTSCALE = view scale) or PaperSpace (PSLTSCALE = 1).',
    'MarkNonplotLayers': 'Put the layers whose names end with the suffix below on "do not plot".',
    'NonplotSuffix': 'Layer-name ending that marks a layer as non-plotting, e.g. -NPLT.',
    'PreserveCoincidentLines': 'Keep lines that lie on top of each other (normally only the front one is kept).',
    'PropOverrides': 'Graphic overrides of the views: ByEntity = colour / weight set on each object, ByLayer = keep layer properties and drop overrides, NewLayer = put overridden elements on extra layers.',
    'SharedCoords': 'Use the shared (site) coordinates instead of the project internal origin - needed to overlay with survey / other consultants.',
    'TargetUnit': 'Drawing unit of the DWG (1 unit = 1 mm, 1 m ...). Default = the project length unit.',
    'TextTreatment': 'Exact = text looks exactly as in Revit (may be split into pieces). Approximate = one editable text object per note.',
    'UseHatchBackgroundColor': 'Give hatches a solid background colour (for filled regions with a background).',
    'MergedViews': 'One file per sheet with all its views merged, instead of a main file plus one file per view.',
    'SeedName': 'MicroStation seed file (.dgn) that sets units and settings of the new file. Empty = Revit default seed.',
    'WorkingUnits': 'Use the working units of the seed file (MicroStation master / sub units).',
    # ---- DWF / DWFx
    'CropBoxVisible': 'Show the crop region frames of the views.',
    'ExportObjectData': 'Include element properties so they can be read in Design Review / Navisworks.',
    'ExportTexture': 'Include material textures (3D views). Bigger files.',
    'ImageFormat': 'Lossless = exact pictures, bigger files. Lossy = smaller JPEG-like pictures.',
    'ImageQuality': 'Resolution of the picture parts: Low, Medium, High (or the Revit default).',
    'PortraitLayout': 'Portrait paper instead of landscape.',
    # ---- NWC
    'ConvertElementProperties': 'Write Revit parameters as Navisworks properties (needed for clash rules and search sets).',
    'ConvertLights': 'Export light sources.',
    'ConvertLinkedCADFormats': 'Also export CAD files linked in Revit (DWG / DGN underlays).',
    'Coordinates': 'Internal = project origin. Shared = site coordinates (use this to line up with other consultants).',
    'DivideFileIntoLevels': 'Group the elements by level in the Navisworks selection tree.',
    'ExportElementIds': 'Keep the Revit element ID on each object (lets you find a clash back in Revit).',
    'ExportLinks': 'Also export the linked Revit models into the same NWC.',
    'ExportParts': 'Export parts instead of the original elements where parts were created.',
    'ExportRoomAsAttribute': 'Add the room each element is in as a property.',
    'ExportRoomGeometry': 'Export rooms as 3D volumes.',
    'ExportUrls': 'Export URL parameters as links.',
    'FacetingFactor': 'Detail of curved surfaces (1 = default). Higher = smoother pipes / ducts, bigger file.',
    'FindMissingMaterials': 'Try to find material textures that are not where Revit expects them.',
    'Parameters': 'Which parameters to export: None, Elements (instance) or All (instance and type).',
    # ---- IFC
    'ExportBaseQuantities': 'Add base quantities (lengths, areas, volumes) to the elements - needed for quantity take-off.',
    'FamilyMappingFile': 'Optional text file that maps Revit categories to IFC classes. Empty = Revit default mapping.',
    'SpaceBoundaryLevel': 'Room / space boundaries for energy analysis: 0 = none, 1 = first level, 2 = second level (detailed).',
    'WallAndColumnSplitting': 'Split walls and columns at each level (one IFC object per storey).',
    # ---- Images
    'FitDirection': 'The pixel size below applies to the width (Horizontal) or the height (Vertical).',
    'HLRandWFViewsFileType': 'File type for plans, sections and wireframe views: PNG is sharp and small, JPEG for photos, BMP / TARGA uncompressed.',
    'ImageResolution': 'Picture resolution (DPI). 150 for screens, 300 for printing.',
    'PixelSize': 'Size of the picture in pixels along the Fit Direction.',
    'ShadowViewsFileType': 'File type for shaded / realistic views.',
    'ShouldCreateWebSite': 'Also create a small HTML page that shows the pictures.',
    'Zoom': 'Zoom percent when Zoom Type is "Zoom".',
}
OPTION_HELP_BY_FORMAT = {
    ('DWF', 'ExportingAreas'): 'Also export room and area boundaries.', ('DWFx', 'ExportingAreas'): 'Also export room and area boundaries.',
    ('DWF', 'MergedViews'): 'All views in one file.', ('DWFx', 'MergedViews'): 'All views in one file.',
    ('DWF', 'StopOnError'): 'Stop the whole export at the first problem.', ('DWFx', 'StopOnError'): 'Stop the whole export at the first problem.',
    ('IFC', 'FileVersion'): 'IFC schema: IFC2x3 Coordination View is the most widely accepted for coordination; IFC4 is newer; COBie for facility handover. Default = the IFC exporter default.',
    ('DGN', 'FileVersion'): 'MicroStation file version: V8 (current) or V7 (old MicroStation).',
    ('Images', 'ZoomType'): 'FitToPage = fit the picture to the pixel size below. Zoom = use the zoom percent.',
}


def _option_help(fmt, name):
    return OPTION_HELP_BY_FORMAT.get((fmt, name)) or OPTION_HELP.get(name, '')



# ================================================================ option reflection

_SPEC_CACHE = {}


def _opt_class(fmt):
    return globals().get(OPT_CLASS.get(fmt, ''))


def _camel_label(name):
    text = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name)
    text = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', text)
    return text


def _specs(fmt):
    """Writable bool/enum/text/number properties of the options class of this format (from the installed Revit)."""
    if fmt in _SPEC_CACHE:
        return _SPEC_CACHE[fmt]
    result = []
    cls = _opt_class(fmt)
    if cls is not None:
        try:
            o = cls()
            skip = set(SKIP_PROPS['ALL'] + SKIP_PROPS.get(fmt, []))
            t_bool = clr.GetClrType(System.Boolean)
            t_str = clr.GetClrType(System.String)
            t_int = clr.GetClrType(System.Int32)
            t_dbl = clr.GetClrType(System.Double)
            for pi in o.GetType().GetProperties():
                try:
                    name = pi.Name
                    if name in skip or not (pi.CanRead and pi.CanWrite):
                        continue
                    pt = pi.PropertyType
                    default = pi.GetValue(o, None)
                    if pt == t_bool:
                        kind, names = 'bool', None
                    elif pt.IsEnum:
                        kind, names = 'enum', [_u(n) for n in System.Enum.GetNames(pt)]
                    elif pt == t_str:
                        kind, names = 'text', None
                    elif pt == t_int or pt == t_dbl:
                        kind, names = 'number', None
                    else:
                        continue
                    default = DEFAULT_OVERRIDES.get(fmt, {}).get(name, default)
                    result.append({'name': name, 'kind': kind, 'ptype': pt, 'enum': names, 'default': default})
                except Exception as ex:
                    _log('spec {0}.{1}: {2}'.format(fmt, getattr(pi, 'Name', '?'), ex))
        except Exception as ex:
            _log('options class {0} unavailable: {1}'.format(fmt, ex))
    result.sort(key=lambda x: x['name'])
    _SPEC_CACHE[fmt] = result
    return result


def _apply_specs(o, fmt, cfg, problems):
    for sp in _specs(fmt):
        key = 'opt.{0}.{1}'.format(fmt, sp['name'])
        if key not in cfg:
            continue
        val = cfg[key]
        try:
            pi = o.GetType().GetProperty(sp['name'])
            if sp['kind'] == 'bool':
                v = bool(val)
            elif sp['kind'] == 'enum':
                if val in (None, ''):
                    continue
                v = System.Enum.Parse(sp['ptype'], _u(val))
            elif sp['kind'] == 'text':
                v = _u(val)
            else:
                txt = _u(val).strip().replace(',', '.')
                if txt == '':
                    continue
                v = int(float(txt)) if sp['ptype'] == clr.GetClrType(System.Int32) else float(txt)
            pi.SetValue(o, v, None)
        except Exception as ex:
            problems.append('{0}.{1}: {2}'.format(fmt, sp['name'], ex))


def _enum_names_of(enum_type):
    try:
        return [_u(n) for n in System.Enum.GetNames(clr.GetClrType(enum_type))]
    except:
        return []


def _set_enum(o, prop, enum_type, name):
    try:
        pi = o.GetType().GetProperty(prop)
        pi.SetValue(o, System.Enum.Parse(pi.PropertyType, _u(name)), None)
        return True
    except:
        return False


# ================================================================ items / naming

def _doc_title(doc):
    t = _u(doc.Title)
    return t[:-4] if t.lower().endswith('.rvt') else t


def _current_rev_param(sheet, bip):
    try:
        p = sheet.get_Parameter(bip)
        if p is not None:
            return _u(p.AsString()).strip()
    except:
        pass
    return ''


def _current_revision(doc, sheet):
    return _current_rev_param(sheet, BuiltInParameter.SHEET_CURRENT_REVISION)


def _collect_sheets(doc):
    result = []
    for s in FilteredElementCollector(doc).OfClass(ViewSheet).ToElements():
        try:
            if s.IsPlaceholder:
                continue
        except:
            pass
        result.append(s)
    result.sort(key=lambda s: _u(s.SheetNumber))
    return result


def _collect_views(doc):
    skip = [ViewType.ProjectBrowser, ViewType.SystemBrowser, ViewType.Internal, ViewType.DrawingSheet]
    result = []
    for v in FilteredElementCollector(doc).OfClass(View).ToElements():
        try:
            if v.IsTemplate or isinstance(v, ViewSheet) or v.ViewType in skip:
                continue
            if not v.CanBePrinted:
                continue
            result.append(v)
        except:
            pass
    result.sort(key=lambda v: (_view_type_label(v), _u(v.Name).lower()))
    return result


def _collect_3d_views(doc):
    result = []
    for v in FilteredElementCollector(doc).OfClass(View3D).ToElements():
        try:
            if not v.IsTemplate:
                result.append(v)
        except:
            pass
    result.sort(key=lambda v: _u(v.Name).lower())
    return result


def _token_value(doc, elem, token):
    key = _u(token).strip()
    low = key.lower()
    is_sheet = elem is not None and isinstance(elem, ViewSheet)
    if low == 'sheetnumber':
        return _u(elem.SheetNumber) if is_sheet else ''
    if low == 'sheetname':
        return _u(elem.Name) if is_sheet else ''
    if low == 'viewname':
        return _u(elem.Name) if elem is not None else ''
    if low == 'viewtype':
        return _view_type_label(elem) if elem is not None else ''
    if low == 'revision':
        return _current_revision(doc, elem) if is_sheet else ''
    if low == 'revisiondescription':
        return _current_rev_param(elem, BuiltInParameter.SHEET_CURRENT_REVISION_DESCRIPTION) if is_sheet else ''
    if low == 'revisiondate':
        return _current_rev_param(elem, BuiltInParameter.SHEET_CURRENT_REVISION_DATE) if is_sheet else ''
    if low == 'projectname':
        return _u(getattr(doc.ProjectInformation, 'Name', ''))
    if low == 'projectnumber':
        return _u(getattr(doc.ProjectInformation, 'Number', ''))
    if low == 'documenttitle':
        return _doc_title(doc)
    if low == 'date':
        return time.strftime('%Y-%m-%d')
    if low == 'time':
        return time.strftime('%H-%M-%S')
    if low == 'year':
        return time.strftime('%Y')
    if low == 'month':
        return time.strftime('%m')
    if low == 'day':
        return time.strftime('%d')
    if low == 'username':
        return _u(os.environ.get('USERNAME', ''))
    for holder in (elem, doc.ProjectInformation):
        try:
            if holder is not None:
                p = holder.LookupParameter(key)
                if p is not None:
                    return _param_to_text(p)
        except:
            pass
    return ''


def _tidy(text):
    text = _safe_filename(text)
    text = re.sub(r'\s*_+\s*', '_', text)
    return text.strip(' _.-')


# ---- rule tokens:  {Name|prefix|suffix|digits|start|step}
#   Name     : a sheet / view / Project Information parameter, or one of the built-in names
#   #        : a running count (start, step, digits), counted per format in the order of the queue
#   Format   : the format name (PDF, DWG ...)     FormatNo : its number among the ticked formats
#   prefix / suffix are only written when the value is not empty; digits pads numbers (2 -> 01)
_TOKEN_RE = re.compile(r'\{([^{}]+)\}')


def _token_fields(body):
    parts = _u(body).split('|')
    parts += [''] * (6 - len(parts))
    return parts[:6]


def _num(text, default):
    try:
        return int(_u(text).strip())
    except Exception:
        return default


def _render_token(doc, elem, body, ctx):
    name, pre, suf, digits, start, step = _token_fields(body)
    low = name.strip().lower()
    ctx = ctx or {}
    if low == '#':
        v = _u(_num(start, 1) + ctx.get('index', 0) * _num(step, 1))
    elif low == 'format':
        v = _u(ctx.get('fmt', 'PDF'))
    elif low == 'formatno':
        v = _u(ctx.get('fmt_index', 0) + _num(start, 1))
    else:
        v = _u(_token_value(doc, elem, name))
    if digits and v.isdigit():
        v = v.zfill(_num(digits, 0))
    return (pre + v + suf) if v != '' else ''


def _expand_text(doc, elem, rule, ctx=None):
    return _TOKEN_RE.sub(lambda m: _render_token(doc, elem, m.group(1), ctx), _u(rule))


def _expand_name(doc, elem, rule, fallback='Export', ctx=None):
    text = _tidy(_expand_text(doc, elem, rule, ctx))
    if not text or text == 'Export':
        text = _tidy(_u(elem.Name)) if elem is not None else fallback
    return text or fallback


def _expand_subfolder(doc, elem, rule, ctx=None):
    parts = []
    for part in re.split(r'[\\/]+', _expand_text(doc, elem, rule, ctx)):
        t = _tidy(part)
        if t and t != 'Export':
            parts.append(t)
    return os.path.join(*parts) if parts else ''


def _parse_rule(rule):
    """Rule text -> rows for the builder table."""
    rows, pos, text = [], 0, _u(rule)
    for m in _TOKEN_RE.finditer(text):
        if m.start() > pos:
            rows.append({'kind': 'Text', 'value': text[pos:m.start()]})
        name, pre, suf, digits, start, step = _token_fields(m.group(1))
        kind = 'Count' if name.strip() == '#' else 'Field'
        rows.append({'kind': kind, 'value': '#' if kind == 'Count' else name, 'pre': pre, 'suf': suf,
                     'digits': digits, 'start': start, 'step': step})
        pos = m.end()
    if pos < len(text):
        rows.append({'kind': 'Text', 'value': text[pos:]})
    return rows


def _rows_to_rule(rows):
    out = []
    for r in rows:
        if r['kind'] == 'Text':
            out.append(_u(r.get('value', '')).replace('{', '').replace('}', ''))
            continue
        name = '#' if r['kind'] == 'Count' else _u(r.get('value', '')).strip()
        if not name:
            continue
        parts = [name] + [_u(r.get(k, '')).replace('|', '').replace('{', '').replace('}', '')
                          for k in ('pre', 'suf', 'digits', 'start', 'step')]
        while len(parts) > 1 and parts[-1] == '':
            parts.pop()
        out.append('{' + '|'.join(parts) + '}')
    return ''.join(out)


def _token_list(doc, elem):
    tokens = ['SheetNumber', 'SheetName', 'Revision', 'RevisionDescription', 'RevisionDate'] if isinstance(elem, ViewSheet) else ['ViewName', 'ViewType']
    tokens += ['ProjectName', 'ProjectNumber', 'DocumentTitle', 'Date', 'Time', 'Year', 'Month', 'Day', 'UserName']
    names = set()
    for holder in (elem, doc.ProjectInformation):
        try:
            for p in holder.Parameters:
                try:
                    if p.Definition is not None:
                        names.add(_u(p.Definition.Name))
                except:
                    pass
        except:
            pass
    return tokens + sorted(list(names), key=lambda x: x.lower())


def _naming_dialog(owner, doc, sample, rule, title='File Name Builder', extra_fields=None, ctx_list=None,
                   folder=False):
    """Table builder for a naming rule. One row per part: Field (a parameter), Count (running number)
    or Text. Prefix / Suffix are written only when the field has a value; Digits pads numbers (01).
    Returns the rule text, or None when cancelled."""
    rows = _parse_rule(rule)
    fields = list(extra_fields or []) + _token_list(doc, sample)
    ctx_list = ctx_list or [{'index': 0}, {'index': 1}, {'index': 2}]
    win = Window()
    win.Title = title
    win.Width = 980
    win.Height = 620
    win.MinWidth = 820
    win.WindowStartupLocation = WindowStartupLocation.CenterOwner
    win.Background = _brush('#F8F8F8')
    try:
        th = _theme()
        if th is not None:
            win.Resources.MergedDictionaries.Add(th)
    except Exception:
        pass
    _glow(win)
    try:
        win.Owner = owner
    except Exception:
        pass
    root = DockPanel()
    head = StackPanel()
    head.Margin = Thickness(12, 10, 12, 4)
    head.Children.Add(_text(title, 16, RED, True))
    head.Children.Add(_text('One row per part, from left to right. Field = a sheet / view / Project Information parameter. '
                            'Count = a running number (start, step, digits). Text = fixed text or a separator'
                            + (' (use \\ for a sub-folder).' if folder else '.')
                            + ' Prefix and suffix are only written when the field has a value. Digits pads numbers: 2 makes 1 into 01.',
                            11.5, GRAY, False, True))
    DockPanel.SetDock(head, System.Windows.Controls.Dock.Top)
    root.Children.Add(head)

    foot = StackPanel()
    foot.Margin = Thickness(12, 4, 12, 10)
    DockPanel.SetDock(foot, System.Windows.Controls.Dock.Bottom)
    root.Children.Add(foot)
    adds = WrapPanel()
    foot.Children.Add(adds)
    preview = _text('', 13, RED, True, True)
    preview.Margin = Thickness(2, 8, 2, 4)
    foot.Children.Add(preview)
    btns = StackPanel()
    btns.Orientation = Orientation.Horizontal
    btns.HorizontalAlignment = HorizontalAlignment.Right
    foot.Children.Add(btns)

    table_border = Border()
    table_border.BorderBrush = _brush(BORDER)
    table_border.BorderThickness = Thickness(1)
    table_border.CornerRadius = System.Windows.CornerRadius(6)
    table_border.Background = _brush(WHITE)
    table_border.Margin = Thickness(12, 4, 12, 4)
    sv = ScrollViewer()
    sv.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    table = StackPanel()
    sv.Content = table
    table_border.Child = sv
    root.Children.Add(table_border)

    COLS = [('', 30), ('Type', 70), ('Field / text', 250), ('Prefix', 90), ('Suffix', 90), ('Digits', 62), ('Start', 62), ('Step', 62), ('', 120)]

    def grid_row(height=34):
        g = Grid()
        g.Height = height
        for _, w in COLS:
            c = ColumnDefinition()
            c.Width = GridLength(w)
            g.ColumnDefinitions.Add(c)
        return g

    def put(g, col, el):
        Grid.SetColumn(el, col)
        el.VerticalAlignment = VerticalAlignment.Center
        g.Children.Add(el)

    def update_preview():
        try:
            rule_now = _rows_to_rule(rows)
            if folder:
                samples = [_expand_subfolder(doc, sample, rule_now, c) or '(no folder)' for c in ctx_list]
            else:
                samples = [_expand_name(doc, sample, rule_now, 'Export', c) for c in ctx_list]
            preview.Text = 'Preview:   ' + '     |     '.join(samples)
        except Exception as ex:
            preview.Text = 'Preview unavailable: {0}'.format(ex)

    def rebuild():
        table.Children.Clear()
        hdr = grid_row(30)
        hdr.Background = _brush(LIGHT)
        for i, (name, _) in enumerate(COLS):
            if name:
                put(hdr, i, _text(name, 11.5, RED, True))
        table.Children.Add(hdr)
        if not rows:
            table.Children.Add(_text('   Empty - add a field, a count or some text below.', 12, GRAY))
        for idx, r in enumerate(rows):
            g = grid_row()
            g.Background = _brush(WHITE if idx % 2 == 0 else '#FBF6F7')
            put(g, 0, _text(' {0}'.format(idx + 1), 11, GRAY))
            put(g, 1, _text(r['kind'], 12, INK, True))
            if r['kind'] == 'Field':
                names = list(fields)
                if r.get('value') and r['value'] not in names:
                    names.insert(0, r['value'])
                ctl = _combo(names, names.index(r['value']) if r.get('value') in names else 0, 244)
                if not r.get('value') and names:
                    r['value'] = names[0]
                ctl.SelectionChanged += _safe_handler((lambda rr, cc: (lambda: (rr.__setitem__('value', _u(cc.SelectedItem)), update_preview())))(r, ctl))
                put(g, 2, ctl)
            elif r['kind'] == 'Text':
                ctl = _textbox(r.get('value', ''), 244, 28)
                ctl.TextChanged += _safe_handler((lambda rr, cc: (lambda: (rr.__setitem__('value', _u(cc.Text)), update_preview())))(r, ctl))
                put(g, 2, ctl)
            else:
                put(g, 2, _text('  running number', 12, GRAY))
            col = 3
            for key, enabled in (('pre', r['kind'] != 'Text'), ('suf', r['kind'] != 'Text'), ('digits', r['kind'] != 'Text'),
                                 ('start', r['kind'] == 'Count' or r.get('value', '').lower() == 'formatno'),
                                 ('step', r['kind'] == 'Count')):
                if enabled:
                    tb = _textbox(r.get(key, ''), 84 if key in ('pre', 'suf') else 56, 28)
                    tb.TextChanged += _safe_handler((lambda rr, kk, cc: (lambda: (rr.__setitem__(kk, _u(cc.Text)), update_preview())))(r, key, tb))
                    put(g, col, tb)
                col += 1
            tools = StackPanel()
            tools.Orientation = Orientation.Horizontal
            tools.Children.Add(_button(u'\u2191', None, (lambda i: (lambda: move(i, -1)))(idx), False, 34))
            tools.Children.Add(_button(u'\u2193', None, (lambda i: (lambda: move(i, 1)))(idx), False, 34))
            tools.Children.Add(_button(u'\u2715', None, (lambda i: (lambda: remove(i)))(idx), False, 34))
            put(g, 8, tools)
            table.Children.Add(g)
        update_preview()

    def move(i, d):
        j = i + d
        if 0 <= j < len(rows):
            rows[i], rows[j] = rows[j], rows[i]
            rebuild()

    def remove(i):
        if 0 <= i < len(rows):
            rows.pop(i)
            rebuild()

    def add(kind, value=''):
        r = {'kind': kind, 'value': value, 'pre': '', 'suf': '', 'digits': '', 'start': '', 'step': ''}
        if kind == 'Count':
            r.update({'value': '#', 'start': '1', 'step': '1', 'digits': '2'})
        rows.append(r)
        rebuild()

    adds.Children.Add(_button('Add Field', 'apply', lambda: add('Field'), True))
    adds.Children.Add(_button('Add Count', 'apply', lambda: add('Count')))
    adds.Children.Add(_button('Add Text', 'rename', lambda: add('Text')))
    for sep in (['\\'] if folder else []) + ['_', '-', '.', ' ']:
        adds.Children.Add(_button(u'"{0}"'.format(sep), None, (lambda x: (lambda: add('Text', x)))(sep), False, 44))
    adds.Children.Add(_button('Clear', 'clear', lambda: (rows.__delitem__(slice(None)), rebuild())))
    result = {'v': None}

    def ok():
        result['v'] = _rows_to_rule(rows)
        win.Close()
    btns.Children.Add(_button('OK', None, ok, True, 90))
    btns.Children.Add(_button('Cancel', None, lambda: win.Close(), False, 90))
    win.Content = root
    rebuild()
    win.ShowDialog()
    return result['v']


# ================================================================ file helpers

def _id_list(elements):
    from System.Collections.Generic import List as GenericList
    ids = GenericList[ElementId]()
    for e in elements:
        ids.Add(e.Id)
    return ids


def _clear_dir(path):
    try:
        for f in os.listdir(path):
            try:
                os.remove(os.path.join(path, f))
            except:
                pass
    except:
        pass


def _fit_name(folder, name, ext):
    # keep the full path under the Windows limit
    room = 245 - len(folder) - len(ext) - 6
    if room < 12:
        raise Exception('The export folder path is too long.')
    return name[:room].rstrip(' ._-') or name[:room]


def _resolve_target(folder, name, ext, policy):
    """Returns (name, skip). Applies the 'file exists' policy."""
    name = _fit_name(folder, name, ext)
    path = os.path.join(folder, name + ext)
    if not os.path.exists(path):
        return name, False
    if _u(policy).startswith('Overwrite'):
        try:
            File.Delete(path)
        except Exception:
            raise Exception('Cannot overwrite {0} (is it open in another program?).'.format(os.path.basename(path)))
        return name, False
    if _u(policy).startswith('Skip'):
        return name, True
    n = 1
    while os.path.exists(os.path.join(folder, '{0} ({1}){2}'.format(name, n, ext))):
        n += 1
    return '{0} ({1})'.format(name, n), False


def _verify_output(folder, name, ext):
    path = os.path.join(folder, name + ext)
    if os.path.exists(path):
        return path
    try:
        for f in os.listdir(folder):
            if f.lower().startswith(name.lower()) and f.lower().endswith(ext.lower()):
                return os.path.join(folder, f)
    except:
        pass
    raise Exception('Revit reported success but no {0} file was found.'.format(ext))


# ================================================================ exporters

def _need_class(fmt):
    cls = _opt_class(fmt)
    if cls is None:
        raise Exception('{0} export is not available in this Revit version.'.format(fmt))
    return cls


def _build_options(doc, fmt, cfg, problems):
    cls = _need_class(fmt)
    o = None
    if fmt in ('DWG', 'DXF'):
        setup = _u(cfg.get(fmt + '.setup', '<Default>'))
        override = bool(cfg.get(fmt + '.override', False))
        xref = bool(cfg.get(fmt + '.xref', False))
        if setup and setup != '<Default>':
            try:
                o = cls.GetPredefinedOptions(doc, setup)
            except Exception as ex:
                problems.append('{0}: export setup "{1}" could not be loaded ({2}); default settings used.'.format(fmt, setup, ex))
                o = None
        if o is None:
            o = cls()
            _apply_specs(o, fmt, cfg, problems)
            try:
                o.MergedViews = not xref       # no setup: one merged file unless xrefs were requested
            except:
                pass
        else:
            if override:
                _apply_specs(o, fmt, cfg, problems)
            try:
                o.MergedViews = not xref       # the xref checkbox always wins: unticked = never any xrefs, even if the setup has them
            except:
                pass
        return o
    o = cls()
    _apply_specs(o, fmt, cfg, problems)
    return o


def _export_pdf(doc, job, folder, cfg, policy, problems):
    _need_class('PDF')
    items = job['items']

    def options(combine):
        o = _build_options(doc, 'PDF', cfg, problems)
        o.Combine = combine
        try:
            ox = float(_u(cfg.get('PDF.offset_x', '0')).replace(',', '.') or 0)
            oy = float(_u(cfg.get('PDF.offset_y', '0')).replace(',', '.') or 0)
            if ox or oy:
                o.OriginOffsetX = ox / 304.8
                o.OriginOffsetY = oy / 304.8
        except Exception as ex:
            problems.append('PDF offsets ignored: {0}'.format(ex))
        return o
    if job.get('combine'):
        name, skip = _resolve_target(folder, job['name'], '.pdf', policy)
        if skip:
            return None
        o = options(True)
        o.FileName = name
        if not doc.Export(folder, _id_list(items), o):
            raise Exception('Revit returned False for the combined PDF.')
        return _verify_output(folder, name, '.pdf')
    name, skip = _resolve_target(folder, job['name'], '.pdf', policy)
    if skip:
        return None
    temp_root = os.path.join(folder, '_EK_tmp_pdf')
    temp_dir = os.path.join(temp_root, str(_element_id(items[0])))
    if not os.path.isdir(temp_dir):
        os.makedirs(temp_dir)
    try:
        _clear_dir(temp_dir)
        ok = doc.Export(temp_dir, _id_list(items[:1]), options(False))
        pdfs = [os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.lower().endswith('.pdf')]
        if not ok or not pdfs:
            raise Exception('Revit did not produce a PDF.')
        target = os.path.join(folder, name + '.pdf')
        File.Move(pdfs[0], target)
        return target
    finally:
        _clear_dir(temp_dir)
        for d in (temp_dir, temp_root):
            try:
                os.rmdir(d)
            except:
                pass


def _views_of_item(doc, item):
    """The views whose content ends up in the file: the view itself, or every view placed on a sheet."""
    views = []
    try:
        if isinstance(item, ViewSheet):
            for vp_id in item.GetAllViewports():
                vp = doc.GetElement(vp_id)
                v = doc.GetElement(vp.ViewId) if vp is not None else None
                if v is not None:
                    views.append(v)
            views.append(item)
        else:
            views.append(item)
    except Exception as ex:
        _log('Could not list views of an item: {0}'.format(ex))
    return views


def _hide_links_temporarily(doc, item):
    """Hides every Revit link instance in the exported views. Must be called inside a transaction that is rolled back."""
    link_ids = [l.Id for l in FilteredElementCollector(doc).OfClass(RevitLinkInstance)]
    if not link_ids:
        return 0
    from System.Collections.Generic import List as GenericList
    ids = GenericList[ElementId]()
    for i in link_ids:
        ids.Add(i)
    count = 0
    for v in _views_of_item(doc, item):
        try:
            v.HideElements(ids)
            count += 1
        except Exception as ex:
            _log('Links could not be hidden in view {0}: {1}'.format(_element_name(v), ex))
    return count


def _dwg_snapshot(folder):
    """Every .dwg of a folder with its time and size - to see which files one export wrote."""
    snap = {}
    try:
        for f in os.listdir(folder):
            if f.lower().endswith('.dwg'):
                p = os.path.join(folder, f)
                try:
                    snap[p] = (os.path.getmtime(p), os.path.getsize(p))
                except Exception:
                    pass
    except Exception:
        pass
    return snap


def _bind_images_as_ole(folder, before, out, problems):
    """DWG option "Bind images as OLE": the pictures go inside the exported file(s), the image files are removed."""
    try:
        after = _dwg_snapshot(folder)
        files = [p for p in sorted(after) if before.get(p) != after[p]]
        if out not in files:
            files.insert(0, out)
        import emperor_dwg_ole
        emperor_dwg_ole.bind_files(files, problems)
    except Exception as ex:
        problems.append('Bind images as OLE failed ({0}); the files were left as Revit exported them.'.format(ex))
        _log('Bind images as OLE failed: {0}\n{1}'.format(ex, traceback.format_exc()))


def _export_cad(doc, job, folder, cfg, policy, fmt, problems):
    ext = EXT[fmt]
    o = _build_options(doc, fmt, cfg, problems)
    name, skip = _resolve_target(folder, job['name'], ext, policy)
    if skip:
        return None
    bind_ole = fmt == 'DWG' and bool(cfg.get('DWG.ole', False))
    dwg_before = _dwg_snapshot(folder) if bind_ole else None
    ids = _id_list(job['items'][:1])
    xref = bool(cfg.get(fmt + '.xref', False))
    with_links = bool(cfg.get(fmt + '.xref_links', False))
    ok = False
    if xref and not with_links:
        # Only the views on the sheet become xrefs. Linked Revit models are hidden for the
        # duration of the export (the change is rolled back, the model is not touched).
        t = Transaction(doc, 'Emperor Exporter - temporary link hiding')
        try:
            t.Start()
            _hide_links_temporarily(doc, job['items'][0])
            ok = doc.Export(folder, name, ids, o)
        except Exception as ex:
            problems.append('{0}: links could not be excluded ({1}); exported without hiding them.'.format(fmt, ex))
            ok = None
        finally:
            try:
                if t.HasStarted():
                    t.RollBack()
            except Exception as ex:
                _log('Rollback failed: {0}'.format(ex))
        if ok is None:
            ok = doc.Export(folder, name, ids, o)
    else:
        ok = doc.Export(folder, name, ids, o)
    if not ok:
        raise Exception('Revit returned False for the {0} export.'.format(fmt))
    out = _verify_output(folder, name, ext)
    if bind_ole:
        _bind_images_as_ole(folder, dwg_before, out, problems)
    return out


def _export_dwf(doc, job, folder, cfg, policy, fmt, problems):
    ext = EXT[fmt]
    o = _build_options(doc, fmt, cfg, problems)
    vs = ViewSet()
    for e in job['items'][:1]:
        vs.Insert(e)
    name, skip = _resolve_target(folder, job['name'], ext, policy)
    if skip:
        return None
    if not doc.Export(folder, name, vs, o):
        raise Exception('Revit returned False for the {0} export.'.format(fmt))
    return _verify_output(folder, name, ext)


def _export_images(doc, job, folder, cfg, policy, problems):
    item = job['items'][0]
    o = _build_options(doc, 'Images', cfg, problems)
    o.ExportRange = ExportRange.SetOfViews
    temp_root = os.path.join(folder, '_EK_tmp_img')
    temp_dir = os.path.join(temp_root, str(_element_id(item)))
    if not os.path.isdir(temp_dir):
        os.makedirs(temp_dir)
    try:
        _clear_dir(temp_dir)
        o.FilePath = os.path.join(temp_dir, 'ek_export')
        o.SetViewsAndSheets(_id_list([item]))
        doc.ExportImage(o)
        files = [os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'))]
        if not files:
            raise Exception('Revit did not create an image.')
        ext = os.path.splitext(files[0])[1] or '.png'
        name, skip = _resolve_target(folder, job['name'], ext, policy)
        if skip:
            return None
        target = os.path.join(folder, name + ext)
        File.Move(files[0], target)
        return target
    finally:
        _clear_dir(temp_dir)
        for d in (temp_dir, temp_root):
            try:
                os.rmdir(d)
            except:
                pass


def _export_ifc(doc, job, folder, cfg, policy, problems):
    o = _build_options(doc, 'IFC', cfg, problems)
    # curated / free-form IFC exporter options (AddOption)
    extras = []
    for key in ('ExportInternalRevitPropertySets', 'ExportIFCCommonPropertySets', 'Export2DElements', 'ExportPartsAsBuildingElements',
                'ExportBoundingBox', 'ExportLinkedFiles', 'ExportSchedulesAsPsets', 'ExportRoomsInView', 'IncludeSiteElevation',
                'UseActiveViewGeometry', 'ExportUserDefinedPsets'):
        k = 'IFC.add.' + key
        if k in cfg:
            extras.append((key, 'true' if cfg[k] else 'false'))
    for line in _u(cfg.get('IFC.custom', '')).replace('\r', '\n').split('\n'):
        if '=' in line:
            a, b = line.split('=', 1)
            if a.strip():
                extras.append((a.strip(), b.strip()))
    for a, b in extras:
        try:
            o.AddOption(a, b)
        except Exception as ex:
            problems.append('IFC option {0}: {1}'.format(a, ex))
    view = job.get('view3d')
    if view is not None:
        try:
            o.FilterViewId = view.Id
        except Exception as ex:
            problems.append('IFC 3D view filter: {0}'.format(ex))
    name, skip = _resolve_target(folder, job['name'], '.ifc', policy)
    if skip:
        return None

    def run(use_tx):
        tx = None
        if use_tx:
            tx = Transaction(doc, 'Emperor Exporter - IFC')
            tx.Start()
        try:
            return doc.Export(folder, name, o)
        finally:
            if tx is not None:
                try:
                    tx.RollBack()
                except:
                    pass
    try:
        ok = run(True)           # IFC export may write GUID parameters, so Revit wants a transaction (rolled back afterwards)
    except Exception:
        ok = run(False)
    if not ok:
        raise Exception('Revit returned False for the IFC export.')
    return _verify_output(folder, name, '.ifc')


def _export_nwc(doc, job, folder, cfg, policy, problems):
    try:
        if not OptionalFunctionalityUtils.IsNavisworksExporterAvailable():
            raise Exception('missing')
    except Exception:
        raise Exception('The Navisworks NWC exporter is not installed or not compatible with this Revit version.')
    o = _build_options(doc, 'NWC', cfg, problems)
    view = job.get('view3d')
    if view is not None:
        _set_enum(o, 'ExportScope', NavisworksExportScope, 'View')
        try:
            o.ViewId = view.Id
        except Exception as ex:
            problems.append('NWC 3D view: {0}'.format(ex))
    else:
        _set_enum(o, 'ExportScope', NavisworksExportScope, 'Model')
    name, skip = _resolve_target(folder, job['name'], '.nwc', policy)
    if skip:
        return None
    if not doc.Export(folder, name, o):
        raise Exception('Revit returned False for the NWC export.')
    return _verify_output(folder, name, '.nwc')


# ================================================================ print filter (black lines for PDF)
#
# PDF  : the views on the exported sheets get the "Emperor Export" filter (every MEP category, black
#        projection + cut lines). Any other enabled filter that colours lines is drawn black as well, so
#        the result is black whatever the filter order is. An existing "PRINT" filter is switched on.
#        Drafting views and legends (no filters there) get black category overrides for their lines,
#        detail items, annotations and legend components, and the text / dimension types used on the
#        exported sheets are made black - coloured notes print black too.
# other: "PRINT" and "Emperor Export" are switched OFF in those views, so DWG / DWF / images keep the
#        system colours (DWG layers stay meaningful).
# Every change is made in a TransactionGroup that is ROLLED BACK after the file is written: views,
# view templates and other sheets are never really changed. Only the filter itself is kept in the
# model (created once if it does not exist yet).

PRINT_FILTER = 'Emperor Export'
BLACK_FILTERS = ('PRINT', 'Emperor Export')
_PRINT_CATS = ['OST_DuctCurves', 'OST_DuctFitting', 'OST_DuctAccessory', 'OST_DuctInsulations', 'OST_DuctLinings',
               'OST_PlaceHolderDucts', 'OST_DuctSystem', 'OST_FlexDuctCurves', 'OST_DuctTerminal',
               'OST_PipeCurves', 'OST_PipeFitting', 'OST_PipeAccessory', 'OST_PipeInsulations', 'OST_PlaceHolderPipes',
               'OST_PipingSystem', 'OST_FlexPipeCurves', 'OST_MechanicalEquipment', 'OST_MechanicalControlDevices',
               'OST_MedicalEquipment', 'OST_PlumbingFixtures', 'OST_PlumbingEquipment', 'OST_Sprinklers']


def _filter_by_name(doc, name):
    for f in FilteredElementCollector(doc).OfClass(ParameterFilterElement):
        if _u(f.Name).strip().lower() == name.lower():
            return f
    return None


def ensure_print_filter(doc):
    """The 'Emperor Export' filter (created once, kept in the model). Returns (filter, created)."""
    f = _filter_by_name(doc, PRINT_FILTER)
    if f is not None:
        return f, False
    from System.Collections.Generic import List as GenericList
    allowed = set()
    try:
        allowed = set(_id_value(i) for i in ParameterFilterUtilities.GetAllFilterableCategories())
    except Exception:
        pass
    cats = GenericList[ElementId]()
    for name in _PRINT_CATS:
        bic = getattr(BuiltInCategory, name, None)
        if bic is None:
            continue
        cid = ElementId(bic)
        if allowed and _id_value(cid) not in allowed:
            continue
        cats.Add(cid)
    t = Transaction(doc, 'Emperor Exporter - create "Emperor Export" filter')
    t.Start()
    try:
        f = ParameterFilterElement.Create(doc, PRINT_FILTER, cats)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return f, True


def _black():
    return _RDB.Color(0, 0, 0)


def _black_overrides(base=None):
    o = OverrideGraphicSettings(base) if base is not None else OverrideGraphicSettings()
    o.SetProjectionLineColor(_black())
    o.SetCutLineColor(_black())
    return o


def _filter_target(doc, view):
    """The view whose filters really apply: its template when the template controls V/G filters."""
    try:
        tid = view.ViewTemplateId
        if tid is not None and _id_value(tid) > 0:
            tmpl = doc.GetElement(tid)
            if tmpl is not None:
                free = [_id_value(i) for i in tmpl.GetNonControlledTemplateParameterIds()]
                if int(BuiltInParameter.VIS_GRAPHICS_FILTERS) not in free:
                    return tmpl
    except Exception:
        pass
    return view


def _graphic_views(doc, items):
    """Views shown on the exported sheets (or the exported views), each template once."""
    out, seen = [], set()
    for item in items:
        for v in _views_of_item(doc, item):
            if isinstance(v, ViewSheet):
                continue
            try:
                if _u(v.ViewType) in ('Legend', 'DraftingView', 'Schedule', 'ColumnSchedule', 'PanelSchedule', 'Report', 'Rendering', 'Walkthrough'):
                    continue
            except Exception:
                pass
            try:
                if not v.AreGraphicsOverridesAllowed():
                    continue
            except Exception:
                pass
            target = _filter_target(doc, v)
            k = _id_value(target.Id)
            if k not in seen:
                seen.add(k)
                out.append(target)
    return out


# drafting views and legends: categories drawn black (with the MEP categories, for legend components)
_ANNO_CATS = ['OST_Lines', 'OST_DetailComponents', 'OST_GenericAnnotation', 'OST_InsulationLines', 'OST_RepeatingDetailLines',
              'OST_DetailComponentTags', 'OST_GenericModel', 'OST_Doors', 'OST_Windows', 'OST_Walls', 'OST_Floors',
              'OST_Ceilings', 'OST_ElectricalEquipment', 'OST_ElectricalFixtures', 'OST_LightingFixtures']
_FLAT_VIEWS = ('Legend', 'DraftingView')


def _template_target(doc, view, bip_name):
    """The view whose setting really applies: its template when the template controls that part."""
    try:
        tid = view.ViewTemplateId
        if tid is not None and _id_value(tid) > 0:
            tmpl = doc.GetElement(tid)
            bip = getattr(BuiltInParameter, bip_name, None)
            if tmpl is not None and bip is not None:
                free = [_id_value(i) for i in tmpl.GetNonControlledTemplateParameterIds()]
                if int(bip) not in free:
                    return tmpl
    except Exception:
        pass
    return view


def _black_flat_views(doc, items, problems):
    """Drafting views and legends on the exported sheets: black lines through category overrides."""
    changed, seen = 0, set()
    for item in items:
        for v in _views_of_item(doc, item):
            try:
                if _u(v.ViewType) not in _FLAT_VIEWS or not v.AreGraphicsOverridesAllowed():
                    continue
            except Exception:
                continue
            for bip_name, names in (('VIS_GRAPHICS_ANNOTATION', _ANNO_CATS), ('VIS_GRAPHICS_MODEL', _PRINT_CATS)):
                target = _template_target(doc, v, bip_name)
                for name in names:
                    bic = getattr(BuiltInCategory, name, None)
                    if bic is None:
                        continue
                    key = (_id_value(target.Id), name)
                    if key in seen:
                        continue
                    seen.add(key)
                    cid = ElementId(bic)
                    try:
                        target.SetCategoryOverrides(cid, _black_overrides(target.GetCategoryOverrides(cid)))
                    except Exception:
                        continue          # category not in this view type - nothing to colour
                    # a coloured override on a sub-category (a line style) wins over its category: black too
                    try:
                        cat = doc.Settings.Categories.get_Item(bic)
                        for sub in (cat.SubCategories if cat is not None else []):
                            o = target.GetCategoryOverrides(sub.Id)
                            if o.ProjectionLineColor.IsValid or o.CutLineColor.IsValid:
                                target.SetCategoryOverrides(sub.Id, _black_overrides(o))
                    except Exception:
                        pass
            changed += 1
    return changed


def _black_text_types(doc, items, problems):
    """Text note and dimension types used on the exported sheets: colour black (undone after the export)."""
    from Autodesk.Revit.DB import TextNote, Dimension
    type_ids = set()
    views = []
    for item in items:
        views.extend(_views_of_item(doc, item))
    for v in views:
        for cls in (TextNote, Dimension):
            try:
                for e in FilteredElementCollector(doc, v.Id).OfClass(cls):
                    type_ids.add(_id_value(e.GetTypeId()))
            except Exception:
                pass
    changed = 0
    for tid in type_ids:
        t = doc.GetElement(_eid(tid))
        if t is None:
            continue
        try:
            p = t.get_Parameter(BuiltInParameter.LINE_COLOR)
            if p is not None and not p.IsReadOnly and p.AsInteger() != 0:
                p.Set(0)
                changed += 1
        except Exception as ex:
            problems.append('Text colour not made black for "{0}": {1}'.format(_element_name(t), ex))
    return changed


def _eid(value):
    """ElementId from an int on every Revit version."""
    try:
        return ElementId(System.Int64(value))
    except Exception:
        return ElementId(int(value))


def _apply_print_mode(doc, items, black, filter_elem, problems):
    """Inside an open transaction: black lines on (PDF) or the black filters off (other formats)."""
    changed = 0
    black_ids = set(_id_value(f.Id) for f in [_filter_by_name(doc, n) for n in BLACK_FILTERS] if f is not None)
    for v in _graphic_views(doc, items):
        try:
            applied = list(v.GetFilters())
            if black:
                fid = filter_elem.Id
                if fid not in applied:
                    v.AddFilter(fid)
                v.SetFilterOverrides(fid, _black_overrides())
                v.SetFilterVisibility(fid, True)
                try:
                    v.SetIsFilterEnabled(fid, True)
                except Exception:
                    pass
                for other in applied:          # coloured filters draw black too (filter order does not matter)
                    try:
                        if not v.GetIsFilterEnabled(other) or not v.GetFilterVisibility(other):
                            continue
                    except Exception:
                        pass
                    o = v.GetFilterOverrides(other)
                    try:
                        coloured = o.ProjectionLineColor.IsValid or o.CutLineColor.IsValid
                    except Exception:
                        coloured = False
                    if coloured or _id_value(other) in black_ids:
                        v.SetFilterOverrides(other, _black_overrides(o))
            else:
                for other in applied:
                    if _id_value(other) in black_ids:
                        try:
                            v.SetIsFilterEnabled(other, False)
                        except Exception:
                            v.SetFilterVisibility(other, True)
                            v.SetFilterOverrides(other, OverrideGraphicSettings())
            changed += 1
        except Exception as ex:
            problems.append('Print filter not applied in "{0}": {1}'.format(_element_name(v), ex))
    if black:
        try:
            changed += _black_flat_views(doc, items, problems)
        except Exception as ex:
            problems.append('Drafting views / legends not made black: {0}'.format(ex))
        try:
            _black_text_types(doc, items, problems)
        except Exception as ex:
            problems.append('Text colours not made black: {0}'.format(ex))
    return changed


def run_with_print_mode(doc, items, fmt, cfg, problems, export_call):
    """Run export_call() with the black-lines filter on (PDF) or off (other formats) in the views of
    the exported sheets only; every change is rolled back afterwards."""
    if not cfg.get('print_filter') or not items:
        return export_call()
    black = (fmt == 'PDF')
    filter_elem = None
    if black:
        try:
            filter_elem, created = ensure_print_filter(doc)
            if created:
                problems.append('Filter "{0}" was created in the model (black lines for PDF).'.format(PRINT_FILTER))
        except Exception as ex:
            problems.append('Print filter could not be created: {0} - exported without it.'.format(ex))
            return export_call()
    group = TransactionGroup(doc, 'Emperor Exporter - temporary print graphics')
    group.Start()
    try:
        t = Transaction(doc, 'Emperor Exporter - print graphics')
        t.Start()
        try:
            _apply_print_mode(doc, items, black, filter_elem, problems)
            t.Commit()
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            problems.append('Print graphics not applied: {0}'.format(ex))
        return export_call()
    finally:
        try:
            group.RollBack()              # views and templates exactly as they were
        except Exception as ex:
            _log('Print graphics rollback failed: {0}'.format(ex))


DEFAULT_FMT_FOLDER = '{FormatNo||. |2}{Format}'          # 01. PDF, 02. DWG ...
_LEGACY_FMT_FOLDER = {'PDF': '{Format}', '1. PDF': '{FormatNo||. }{Format}', '01 - PDF': '{FormatNo|| - |2}{Format}',
                      '1_PDF': '{FormatNo||_}{Format}', 'PDF (1)': '{Format}{FormatNo| (|)}'}
DATE_FOLDERS = ['No date folder', 'Date  (2026-11-03)', 'Date and time  (2026-11-03 1530)']
FOLDER_ORDERS = ['Format folder, then sub-folder', 'Sub-folder, then format folder']


def _fmt_folder_rule(value):
    value = _u(value).strip()
    return _LEGACY_FMT_FOLDER.get(value, value) or DEFAULT_FMT_FOLDER


def _format_folder(doc, fmt, ticked, rule):
    ctx = {'fmt': fmt, 'fmt_index': ticked.index(fmt) if fmt in ticked else 0, 'index': 0}
    return _expand_name(doc, None, _fmt_folder_rule(rule), fmt, ctx)


def _date_stamp(choice):
    choice = _u(choice)
    if choice.startswith('Date and time'):
        return time.strftime('%Y-%m-%d %H%M')
    if choice.startswith('Date'):
        return time.strftime('%Y-%m-%d')
    return ''


def _job_folder(root, fmt, ticked, sub, cfg):
    """root \\ [date] \\ [format folder] \\ [sub-folder]   (or sub-folder before the format folder)."""
    parts = []
    stamp = cfg.get('_stamp', '')
    if stamp:
        parts.append(stamp)
    fmt_dir = _format_folder(cfg.get('_doc'), fmt, ticked, cfg.get('fmt_folder')) if cfg.get('split') else ''
    if _u(cfg.get('folder_order', '')).startswith('Sub-folder'):
        parts += [x for x in (sub, fmt_dir) if x]
    else:
        parts += [x for x in (fmt_dir, sub) if x]
    return os.path.join(root, *parts) if parts else root


def _clean_root(path):
    """Old profiles used variables (%UserName%-%Y-...) in the path: drop those parts."""
    path = _u(path).strip()
    if '%' not in path:
        return path
    keep = [p for p in re.split(r'[\\/]', path) if '%' not in p]
    out = '\\'.join(keep)
    if len(keep) == 1 and out.endswith(':'):
        out += '\\'
    return out


# ================================================================ UI helpers

def _get_ctl(c):
    if isinstance(c, (CheckBox, RadioButton)):
        return bool(c.IsChecked)
    if isinstance(c, ComboBox):
        return _u(c.SelectedItem) if c.SelectedItem is not None else ''
    if isinstance(c, TextBox):
        return _u(c.Text)
    return None


def _set_ctl(c, v):
    try:
        if isinstance(c, (CheckBox, RadioButton)):
            c.IsChecked = bool(v)
        elif isinstance(c, ComboBox):
            for i in range(c.Items.Count):
                if _u(c.Items[i]) == _u(v):
                    c.SelectedIndex = i
                    return
        elif isinstance(c, TextBox):
            c.Text = _u(v)
    except:
        pass


def _dwg_setups(doc):
    for fn in (lambda: BaseExportOptions.GetPredefinedSetupNames(doc), lambda: DWGExportOptions.GetPredefinedSetupNames(doc)):
        try:
            return [_u(x) for x in fn()]
        except:
            pass
    return []


def _card(title, body_width=None):
    """A bordered section: returns (border, stack)."""
    b = Border()
    b.BorderBrush = _brush(BORDER)
    b.BorderThickness = Thickness(1)
    b.CornerRadius = System.Windows.CornerRadius(6)
    b.Background = _brush('#FCFAFA')
    b.Padding = Thickness(10, 8, 10, 8)
    b.Margin = Thickness(2, 4, 2, 4)
    sp = StackPanel()
    if title:
        sp.Children.Add(_text(title, 13, RED, True))
    b.Child = sp
    return b, sp


# ================================================================ main window

def launch_exporter(revit_ctx):
    doc = _doc(revit_ctx)
    uidoc = _uidoc(revit_ctx)
    if doc is None or doc.IsFamilyDocument:
        _show_message('Open a project document before using Emperor Exporter.', error=True)
        return
    win, toolbar, content, status, footer = _make_window('Emperor Exporter', 'Project: {0}.  Selection > Formats > Create.'.format(_doc_title(doc)), 1060, 700)
    st = {'mode': 'Sheets', 'items': {}, 'tables': {}, 'jobs': [], 'cancel': False, 'running': False, 'extra': {'Sheets': [], 'Views': []},
          'rule': {'Sheets': DEFAULT_RULE, 'Views': DEFAULT_VIEW_RULE}, 'last_report': '', 'last_root': ''}
    reg = {}
    defaults = {}
    fmt_keys = dict([(f, []) for f in FORMAT_NAMES])
    views3d = _collect_3d_views(doc)
    views3d_names = [_u(v.Name) for v in views3d]
    views3d_by_name = dict([(_u(v.Name), v) for v in views3d])

    def R(key, ctl, fmt=None):
        reg[key] = ctl
        defaults[key] = _get_ctl(ctl)
        if fmt:
            fmt_keys[fmt].append(key)
        return ctl

    tabs = _tabs()
    content.Children.Add(tabs)

    # ============================================================ 1. Selection
    sel_root = DockPanel()
    sel_top = StackPanel()
    DockPanel.SetDock(sel_top, System.Windows.Controls.Dock.Top)
    sel_root.Children.Add(sel_top)
    rb_sheets = _radio('Sheets', 'ex_mode', True, lambda: switch_mode('Sheets'))
    rb_views = _radio('Views', 'ex_mode', False, lambda: switch_mode('Views'))
    open_only = _checkbox('Opened only', False, lambda: apply_filters())
    search_box = _textbox('', 220)
    search_box.ToolTip = 'Search by number / name'
    type_combo = _combo(['All view types'], 0, 190)
    sel_top.Children.Add(_row(rb_sheets, rb_views, open_only, _label('Search', 52), search_box, type_combo,
                              _button('Columns...', 'settings', lambda: choose_columns())))
    set_combo = _combo(['(my sets)'], 0, 170)
    rset_combo = _combo(['(Revit sheet sets)'], 0, 200)
    sel_top.Children.Add(_row(_label('Sets', 36), set_combo, _button('Save Set', 'apply', lambda: save_set()), _button('Delete Set', 'clear', lambda: delete_set()),
                              rset_combo,
                              _button('Check Selected', 'select_all', lambda: check_selected(True)),
                              _button('Uncheck Selected', 'clear', lambda: check_selected(False)),
                              _button('Check All Visible', 'select_all', lambda: select_all(True)),
                              _button('Uncheck All', 'clear', lambda: select_all(False))))
    sel_top.Children.Add(_text('Tip: click a row, then Ctrl+click or Shift+click to highlight several rows. Press Space (or use Check Selected) to tick/untick all highlighted rows at once.', 11, GRAY, False, True))
    summary_text = _text('', 12, RED, True)
    sel_top.Children.Add(summary_text)

    rule_card, rule_stack = _card('File name rule (for the selected mode)')
    DockPanel.SetDock(rule_card, System.Windows.Controls.Dock.Bottom)
    sel_root.Children.Add(rule_card)
    rule_box = _textbox(DEFAULT_RULE, 600)
    rule_stack.Children.Add(_row(rule_box, _button('Build...', 'rename', lambda: build_rule())))
    rule_preview = _text('', 11, GRAY, False, True)
    rule_stack.Children.Add(rule_preview)

    grid_host = Grid()
    sel_root.Children.Add(grid_host)
    _add_tab(tabs, '1  Selection', sel_root)

    def columns_for(mode):
        extra = [(c, System.String) for c in st['extra'][mode]]
        if mode == 'Sheets':
            return [('Export', System.Boolean), ('Number', System.String), ('Name', System.String), ('Revision', System.String)] + extra + [('Type', System.String), ('Id', System.String)]
        return [('Export', System.Boolean), ('Name', System.String), ('Type', System.String)] + extra + [('Id', System.String)]

    def mode_table(mode):
        if mode in st['tables']:
            return st['tables'][mode]
        cols = columns_for(mode)
        table = _new_datatable(cols, [])
        items = {}
        elems = _collect_sheets(doc) if mode == 'Sheets' else _collect_views(doc)
        table.BeginLoadData()
        try:
            for e in elems:
                eid = _element_id(e)
                items[eid] = e
                dr = table.NewRow()
                dr['Export'] = False
                dr['Id'] = str(eid)
                if mode == 'Sheets':
                    dr['Number'] = _u(e.SheetNumber)
                    dr['Name'] = _u(e.Name)
                    dr['Revision'] = _current_revision(doc, e)
                    dr['Type'] = 'Sheet'
                else:
                    dr['Name'] = _u(e.Name)
                    dr['Type'] = _view_type_label(e)
                for c in st['extra'][mode]:
                    try:
                        dr[c] = _param_to_text(e.LookupParameter(c))
                    except:
                        dr[c] = ''
                table.Rows.Add(dr)
        finally:
            table.EndLoadData()
        readonly = [c[0] for c in cols if c[0] != 'Export']
        grid = _make_grid(table, True, readonly, False, ['Id'])
        grid.Visibility = Visibility.Collapsed
        _enable_multi_check(grid, 'Export', apply_filters)
        grid_host.Children.Add(grid)
        st['tables'][mode] = (table, grid)
        st['items'][mode] = items
        return st['tables'][mode]

    def current():
        return mode_table(st['mode'])

    def switch_mode(mode):
        st['mode'] = mode
        for m, (t, g) in list(st['tables'].items()):
            g.Visibility = Visibility.Collapsed
        table, grid = mode_table(mode)
        grid.Visibility = Visibility.Visible
        type_combo.Visibility = Visibility.Visible if mode == 'Views' else Visibility.Collapsed
        if mode == 'Views' and type_combo.Items.Count <= 1:
            for k in sorted(set([_u(r['Type']) for r in table.Rows])):
                type_combo.Items.Add(k)
        rule_box.Text = st['rule'][mode]
        refresh_sets()
        apply_filters()

    def checked_ids(mode=None):
        mode = mode or st['mode']
        if mode not in st['tables']:
            return []
        table, grid = st['tables'][mode]
        return [int(_u(r['Id'])) for r in table.Rows if bool(r['Export'])]

    def checked_items(mode):
        if mode not in st['tables']:
            return []
        return [st['items'][mode][i] for i in checked_ids(mode) if i in st['items'][mode]]

    def update_summary():
        parts = []
        for m in ('Sheets', 'Views'):
            if m in st['tables']:
                parts.append('{0}: {1} ticked of {2}'.format(m, len(checked_ids(m)), st['tables'][m][0].Rows.Count))
        summary_text.Text = '   |   '.join(parts)

    def apply_filters():
        table, grid = current()
        parts = []
        needle = _u(search_box.Text).strip().replace("'", "''")
        for ch in ['[', ']', '*', '%']:
            needle = needle.replace(ch, '[' + ch + ']')
        if needle:
            parts.append(("(Number LIKE '%{0}%' OR Name LIKE '%{0}%')" if st['mode'] == 'Sheets' else "Name LIKE '%{0}%'").format(needle))
        if st['mode'] == 'Views' and type_combo.SelectedIndex > 0:
            parts.append("Type = '{0}'".format(_u(type_combo.SelectedItem).replace("'", "''")))
        if bool(open_only.IsChecked):
            ids = []
            try:
                for uv in uidoc.GetOpenUIViews():
                    ids.append(str(_id_value(uv.ViewId)))
            except:
                pass
            parts.append("Id IN ({0})".format(','.join(["'" + x + "'" for x in ids]) if ids else "'-1'"))
        table.DefaultView.RowFilter = ' AND '.join(parts)
        update_summary()
        _set_status(status, '{0}: showing {1} of {2}.'.format(st['mode'], table.DefaultView.Count, table.Rows.Count))

    search_box.TextChanged += _safe_handler(apply_filters)
    type_combo.SelectionChanged += _safe_handler(apply_filters)

    def check_selected(value):
        table, grid = current()
        rows = _selected_rows(grid)
        if not rows:
            _show_message('Highlight one or more rows first (click, then Ctrl/Shift+click).', error=True)
            return
        for drv in rows:
            drv['Export'] = bool(value)
        apply_filters()

    def select_all(value):
        table, grid = current()
        for drv in table.DefaultView:
            drv['Export'] = bool(value)
        apply_filters()

    def choose_columns():
        items = list(st['items'].get(st['mode'], {}).values())
        if not items:
            return
        names = set()
        try:
            for p in items[0].Parameters:
                try:
                    if p.Definition is not None:
                        names.add(_u(p.Definition.Name))
                except:
                    pass
        except:
            pass
        picked = _list_dialog(win, 'Columns', 'Extra parameter columns for the {0} list (useful for sorting and filtering):'.format(st['mode'].lower()),
                              sorted(list(names), key=lambda x: x.lower()), True, st['extra'][st['mode']])
        if picked is None:
            return
        mode = st['mode']
        keep = set(checked_ids(mode))
        st['extra'][mode] = picked
        table, grid = st['tables'].pop(mode)
        grid_host.Children.Remove(grid)
        st['items'].pop(mode, None)
        table2, grid2 = mode_table(mode)
        for r in table2.Rows:
            r['Export'] = int(_u(r['Id'])) in keep
        switch_mode(mode)

    # ---- my sets (saved per project)
    def sets_path():
        return os.path.join(_profiles_dir('EmperorExporter'), 'sets.json')

    def load_sets():
        return _load_json(sets_path(), {})

    def refresh_sets():
        data = load_sets().get(_u(doc.Title), {}).get(st['mode'], {})
        set_combo.Items.Clear()
        set_combo.Items.Add('(my sets)')
        for k in sorted(data.keys()):
            set_combo.Items.Add(k)
        set_combo.SelectedIndex = 0
        rset_combo.Items.Clear()
        rset_combo.Items.Add('(Revit sheet sets)')
        try:
            for vs in FilteredElementCollector(doc).OfClass(ViewSheetSet).ToElements():
                rset_combo.Items.Add(_u(vs.Name))
        except:
            pass
        rset_combo.SelectedIndex = 0

    def save_set():
        ids = checked_ids()
        if not ids:
            _show_message('Tick some rows first, then save them as a set.', error=True)
            return
        name = _input_dialog(win, 'Save Set', 'Name for the new set:')
        if not name or not name.strip():
            return
        data = load_sets()
        data.setdefault(_u(doc.Title), {}).setdefault(st['mode'], {})[name.strip()] = ids
        _save_json(sets_path(), data)
        refresh_sets()
        _set_status(status, 'Set saved: {0} ({1} items).'.format(name.strip(), len(ids)))

    def delete_set():
        name = _u(set_combo.SelectedItem) if set_combo.SelectedItem is not None else ''
        if not name or name == '(my sets)':
            return
        data = load_sets()
        try:
            del data[_u(doc.Title)][st['mode']][name]
            _save_json(sets_path(), data)
        except:
            pass
        refresh_sets()

    def tick_ids(ids):
        table, grid = current()
        ids = set(ids)
        for r in table.Rows:
            r['Export'] = int(_u(r['Id'])) in ids
        apply_filters()

    def apply_my_set():
        name = _u(set_combo.SelectedItem) if set_combo.SelectedItem is not None else ''
        if name and name != '(my sets)':
            tick_ids(load_sets().get(_u(doc.Title), {}).get(st['mode'], {}).get(name, []))

    def apply_revit_set():
        name = _u(rset_combo.SelectedItem) if rset_combo.SelectedItem is not None else ''
        if not name or name == '(Revit sheet sets)':
            return
        for vs in FilteredElementCollector(doc).OfClass(ViewSheetSet).ToElements():
            if _u(vs.Name) == name:
                ids = []
                try:
                    for v in vs.Views:
                        ids.append(_id_value(v.Id))
                except:
                    pass
                tick_ids(ids)
                _set_status(status, 'Revit set "{0}": {1} item(s) ticked in the current list.'.format(name, len(checked_ids())))
                return
    set_combo.SelectionChanged += _safe_handler(apply_my_set)
    rset_combo.SelectionChanged += _safe_handler(apply_revit_set)

    # ---- naming rule
    def sample_item():
        c = checked_items(st['mode'])
        if c:
            return c[0]
        items = st['items'].get(st['mode'], {})
        return list(items.values())[0] if items else None

    def update_rule_preview():
        st['rule'][st['mode']] = _u(rule_box.Text)
        s = sample_item()
        try:
            rule_preview.Text = ('Example: ' + _expand_name(doc, s, _u(rule_box.Text))) if s is not None else ''
        except Exception as ex:
            rule_preview.Text = 'Example unavailable: {0}'.format(ex)
    rule_box.TextChanged += _safe_handler(update_rule_preview)

    def build_rule():
        s = sample_item()
        if s is None:
            _show_message('There is nothing to preview the rule on.', error=True)
            return
        r = _naming_dialog(win, doc, s, _u(rule_box.Text))
        if r is not None:
            rule_box.Text = r

    # ============================================================ 2. Formats
    fmt_root = DockPanel()
    left = StackPanel()
    left.Width = 250
    left.Margin = Thickness(4)
    DockPanel.SetDock(left, System.Windows.Controls.Dock.Left)
    fmt_root.Children.Add(left)
    left.Children.Add(_text('Tick the formats to export', 13, RED, True))
    fmt_list = ListBox()
    fmt_list.Height = 330
    left.Children.Add(fmt_list)
    fmt_desc = _text('', 11, GRAY, False, True)
    left.Children.Add(fmt_desc)
    fmt_checks = {}
    for f, icon, desc in FORMATS:
        item = System.Windows.Controls.ListBoxItem()
        sp = StackPanel()
        sp.Orientation = Orientation.Horizontal
        cb = CheckBox()
        cb.IsChecked = (f == 'PDF')
        cb.Margin = Thickness(2, 6, 8, 2)
        fmt_checks[f] = cb
        sp.Children.Add(cb)
        sp.Children.Add(_image(icon, 20, 20))
        t = _text(f, 14, INK, True)
        t.VerticalAlignment = VerticalAlignment.Center
        sp.Children.Add(t)
        item.Content = sp
        item.Tag = f
        item.ToolTip = desc
        fmt_list.Items.Add(item)
    panel_host = Grid()
    fmt_root.Children.Add(panel_host)
    fmt_panels = {}

    def reset_format(f):
        for k in fmt_keys[f]:
            _set_ctl(reg[k], defaults[k])
        _set_status(status, '{0} options reset to defaults.'.format(f))

    def new_panel(f, icon, desc):
        sv = ScrollViewer()
        sv.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        sv.Visibility = Visibility.Collapsed
        sp = StackPanel()
        sp.Margin = Thickness(8)
        head = _row(_image(icon, 28, 28), _text(f + ' export settings', 17, RED, True), _button('Reset to defaults', 'refresh', (lambda ff: (lambda: reset_format(ff)))(f)))
        sp.Children.Add(head)
        sp.Children.Add(_text(desc, 11, GRAY, False, True))
        sv.Content = sp
        panel_host.Children.Add(sv)
        fmt_panels[f] = sv
        return sp

    def add_auto(panel, f):
        specs = _specs(f)
        if not specs:
            panel.Children.Add(_text('This Revit version exposes no further {0} options.'.format(f), 11, GRAY, False, True))
            return
        exp = Expander()
        exp.Header = 'All {0} options of this Revit version ({1})'.format(f, len(specs))
        exp.IsExpanded = True
        exp.FontFamily = FontFamily('Segoe UI')
        exp.FontWeight = FontWeights.Bold
        exp.Margin = Thickness(0, 6, 0, 0)
        wrap = StackPanel()
        wrap.Margin = Thickness(4)
        for sp_ in specs:
            key = 'opt.{0}.{1}'.format(f, sp_['name'])
            label = _camel_label(sp_['name'])
            tip = _option_help(f, sp_['name'])
            row = Grid()
            for w in (390, 1):
                cd = ColumnDefinition()
                cd.Width = GridLength(w, System.Windows.GridUnitType.Pixel if w > 1 else System.Windows.GridUnitType.Star)
                row.ColumnDefinitions.Add(cd)
            row.Margin = Thickness(0, 1, 0, 1)
            if sp_['kind'] == 'bool':
                ctl = _checkbox(label, bool(sp_['default']), None, 380)
                cell = ctl
            else:
                if sp_['kind'] == 'enum':
                    names = sp_['enum']
                    d = _u(sp_['default'])
                    ctl = _combo(names, names.index(d) if d in names else 0, 190)
                else:
                    ctl = _textbox('' if sp_['default'] is None else _u(sp_['default']), 190)
                cell = StackPanel()
                cell.Orientation = Orientation.Horizontal
                cell.Children.Add(_label(label, 190))
                cell.Children.Add(ctl)
            if tip:
                ctl.ToolTip = tip
            cell.VerticalAlignment = VerticalAlignment.Center
            row.Children.Add(cell)
            note = _text(tip, 11, GRAY, False, True)
            note.VerticalAlignment = VerticalAlignment.Center
            note.Margin = Thickness(8, 0, 4, 0)
            Grid.SetColumn(note, 1)
            row.Children.Add(note)
            R(key, ctl, f)
            wrap.Children.Add(row)
        exp.Content = wrap
        panel.Children.Add(exp)

    def curated_check(panel, key, text, default, f, tip=None):
        c = _checkbox(text, default)
        if tip:
            c.ToolTip = tip
        R(key, c, f)
        panel.Children.Add(c)
        return c

    def curated_text(panel, key, text, default, f, width=320, label_w=190):
        c = _textbox(default, width)
        R(key, c, f)
        panel.Children.Add(_row(_label(text, label_w), c))
        return c

    def curated_combo(panel, key, text, items, f, width=260, label_w=190):
        c = _combo(items, 0, width)
        R(key, c, f)
        panel.Children.Add(_row(_label(text, label_w), c))
        return c

    for f, icon, desc in FORMATS:
        p = new_panel(f, icon, desc)
        if f == 'PDF':
            card, cs = _card('File')
            curated_check(cs, 'PDF.combine', 'Combine all selected sheets/views into ONE PDF file', False, f)
            curated_text(cs, 'PDF.combined_name', 'Combined file name', '{DocumentTitle}_Combined', f)
            curated_text(cs, 'PDF.offset_x', 'Offset X (mm)', '0', f, 90)
            curated_text(cs, 'PDF.offset_y', 'Offset Y (mm)', '0', f, 90)
            cs.Children.Add(_text('Offsets apply when Paper Placement is "LowerLeft". Paper Format "Default" means "use sheet size".', 11, GRAY, False, True))
            p.Children.Add(card)
        elif f in ('DWG', 'DXF'):
            card, cs = _card('Export setup')
            curated_combo(cs, f + '.setup', 'Export setup', ['<Default>'] + _dwg_setups(doc), f, 320)
            curated_check(cs, f + '.override', 'Use the options below instead of the setup values (overrides the setup)', False, f)
            curated_check(cs, f + '.xref', 'Export views on sheets as external references (unticked = no xrefs at all)', False, f)
            curated_check(cs, f + '.xref_links', '   ...also export the linked Revit models as xrefs (off = only this project)', False, f)
            cs.Children.Add(_text('Ticked: each sheet becomes a main file plus one xref file per view on it, whatever the setup says. Linked Revit models are left out unless you tick the second box. Unticked: always ONE merged file per sheet with no external references, even if the chosen setup has xrefs switched on.', 11, GRAY, False, True))
            p.Children.Add(card)
            if f == 'DWG':
                card, cs = _card('Images')
                ole_box = curated_check(cs, 'DWG.ole', 'Bind images as OLE (pictures are stored inside the DWG - no separate image files)', False, f,
                                        'Title block logos and other pictures are embedded in the DWG, like a picture pasted in AutoCAD. AutoCAD is not needed.')
                ole_note = ('Revit exports every picture on a sheet as a separate image file that the DWG only links to. Ticked: after the export each picture '
                            'is put inside the DWG as an OLE object and the image files are deleted, so you deliver one file per sheet. The DWG gets bigger. '
                            'Pictures wider than 1600 px or higher than 1200 px are scaled down (AutoCAD shows bigger OLE pictures blank). Rotated pictures, and '
                            'pictures inside rotated blocks, stay linked and are listed in the notes. New option - check the first exports in AutoCAD.')
                try:
                    import emperor_dwg_ole
                    ole_ok, ole_why = emperor_dwg_ole.available()
                except Exception as ex:
                    ole_ok, ole_why = False, _u(ex)
                if not ole_ok:
                    ole_box.IsEnabled = False
                    ole_note = 'Not available here: ' + ole_why + '. ' + ole_note
                cs.Children.Add(_text(ole_note, 11, GRAY, False, True))
                p.Children.Add(card)
        elif f in MODEL_FORMATS:
            card, cs = _card('What to export')
            curated_combo(cs, f + '.source', 'Source', ['Whole model', 'Selected 3D view'], f, 220)
            curated_combo(cs, f + '.view', '3D view', views3d_names or ['(none)'], f, 320)
            curated_text(cs, f + '.name', 'File name', '{DocumentTitle}', f)
            cs.Children.Add(_text('The selected sheets/views are not used for {0}: it always exports the model (or the 3D view chosen above).'.format(f), 11, GRAY, False, True))
            p.Children.Add(card)
            if f == 'IFC':
                card2, c2 = _card('IFC exporter options')
                for key, text, d in [('ExportIFCCommonPropertySets', 'Export IFC common property sets', True), ('ExportInternalRevitPropertySets', 'Export internal Revit property sets', False),
                                     ('Export2DElements', 'Export 2D elements', False), ('ExportPartsAsBuildingElements', 'Export parts as building elements', False),
                                     ('ExportBoundingBox', 'Export bounding box', False), ('ExportLinkedFiles', 'Export linked files as separate IFC', False),
                                     ('ExportSchedulesAsPsets', 'Export schedules as property sets', False), ('ExportRoomsInView', 'Export rooms in 3D views', False),
                                     ('IncludeSiteElevation', 'Include site elevation in the site location', False), ('ExportUserDefinedPsets', 'Export user defined property sets', False)]:
                    curated_check(c2, 'IFC.add.' + key, text, d, f)
                c2.Children.Add(_text('Any other IFC exporter option (NAME=VALUE, one per line). Unknown names are ignored by Revit.', 11, GRAY, False, True))
                custom = TextBox()
                custom.AcceptsReturn = True
                custom.Height = 70
                custom.Width = 520
                custom.HorizontalAlignment = HorizontalAlignment.Left
                custom.FontFamily = FontFamily('Consolas')
                R('IFC.custom', custom, f)
                c2.Children.Add(custom)
                p.Children.Add(card2)
        add_auto(p, f)

    def show_format_panel():
        item = fmt_list.SelectedItem
        if item is None:
            return
        f = item.Tag
        for k, v in fmt_panels.items():
            v.Visibility = Visibility.Visible if k == f else Visibility.Collapsed
        fmt_desc.Text = [d for n, i, d in FORMATS if n == f][0]
    fmt_list.SelectionChanged += _safe_handler(show_format_panel)
    fmt_list.SelectedIndex = 0
    _add_tab(tabs, '2  Formats', fmt_root)

    # ============================================================ 3. Create
    cr_root = DockPanel()
    cr_top = StackPanel()
    DockPanel.SetDock(cr_top, System.Windows.Controls.Dock.Top)
    cr_root.Children.Add(cr_top)
    c1, s1 = _card('Export location')
    default_path = os.path.join(os.path.expanduser('~'), 'Documents', 'Emperor Exports')
    path_box = R('path', _textbox(default_path, 700))

    def browse():
        pth = _pick_folder('Choose export folder')
        if pth:
            path_box.Text = pth
    s1.Children.Add(_row(path_box, _button('Browse', 'folder', browse), _button('Open', 'folder', lambda: open_root())))
    policy_combo = R('policy', _combo(POLICIES, 0, 230))
    report_cb = R('report', _checkbox('Write export report (CSV)', True))
    open_cb = R('open', _checkbox('Open folder when finished', True))
    s1.Children.Add(_row(_label('If a file exists', 100), policy_combo, report_cb, open_cb))
    # ---- black print filter (New)
    print_cb = R('print_filter', _checkbox('Black lines in PDF  (filter "Emperor Export": ON for PDF, OFF for DWG and other formats)', True))
    print_cb.ToolTip = ('PDF: the views on the exported sheets print every duct, pipe, fitting, terminal and equipment with black lines '
                        '(the "Emperor Export" filter is created in the model if it is missing; "PRINT" is switched on too). '
                        'Drafting views and legends print their lines black, and coloured text and dimensions print black. '
                        'Pictures and coloured fills keep their colours.\n'
                        'DWG, DXF, DGN, DWF, images: "PRINT" and "Emperor Export" are switched off, so the system colours stay.\n'
                        'Only the exported sheets are affected and every change is undone after each file.')
    new_tag = _text('(New)', 12, RED2, True)
    new_tag.VerticalAlignment = VerticalAlignment.Center
    new_tag.Margin = Thickness(2, 0, 0, 0)
    s1.Children.Add(_row(print_cb, new_tag))
    cr_top.Children.Add(c1)

    # ---- folders
    c2, s2 = _card('Folders')
    split_cb = R('split', _checkbox('One folder per format', False))
    fmt_folder_box = R('fmt_folder', _textbox(DEFAULT_FMT_FOLDER, 210))
    fmt_folder_box.ToolTip = ('How the format folders are named - press Build... to edit it as a table. '
                              'FormatNo = the number of the format among the ticked ones (digits 2 = 01), Format = PDF, DWG ...')

    def ticked_formats():
        return [f for f in FORMAT_NAMES if bool(fmt_checks[f].IsChecked)] or ['PDF', 'DWG']

    def build_fmt_folder():
        ticked = ticked_formats()
        ctxs = [{'fmt': f, 'fmt_index': i, 'index': 0} for i, f in enumerate(ticked[:4])]
        r = _naming_dialog(win, doc, None, _fmt_folder_rule(fmt_folder_box.Text), 'Format Folder Builder',
                           ['Format', 'FormatNo'], ctxs)
        if r is not None:
            fmt_folder_box.Text = r
    date_combo = R('date_folder', _combo(DATE_FOLDERS, 0, 190))
    date_combo.ToolTip = 'Optional folder with the export date, so every export keeps its own folder.'
    s2.Children.Add(_row(split_cb, _label('Folder name', 82), fmt_folder_box, _button('Build...', 'rename', build_fmt_folder),
                         _label('Date folder', 78), date_combo))
    sub_box = R('sub_rule', _textbox('', 300))
    sub_box.ToolTip = ('Folder(s) per sheet / view from its parameters, for example  {Revision}  or  {Sheet Group}\\{Revision}. '
                       'Use \\ for nested folders. Empty = no sub-folder.')
    order_combo = R('folder_order', _combo(FOLDER_ORDERS, 0, 230))

    def build_sub_rule():
        smp = sample_item()
        if smp is None:
            _show_message('There is nothing to preview the rule on.', error=True)
            return
        r = _naming_dialog(win, doc, smp, _u(sub_box.Text), 'Sub-folder Builder', None, None, True)
        if r is not None:
            sub_box.Text = r
    s2.Children.Add(_row(_label('Sub-folder rule', 100), sub_box, _button('Build...', 'rename', build_sub_rule), _label('Order', 44), order_combo))
    folder_preview = _text('', 11, GRAY, False, True)
    s2.Children.Add(folder_preview)
    cr_top.Children.Add(c2)

    def update_folder_preview():
        try:
            ticked = ticked_formats()
            smp = sample_item()
            sub = _expand_subfolder(doc, smp, _u(sub_box.Text)) if smp is not None else ''
            rel = _job_folder('', ticked[0], ticked, sub, settings_light())
            root_name = os.path.basename(_u(path_box.Text).rstrip('\\/')) or 'Export folder'
            folder_preview.Text = 'Example: ' + os.path.join(root_name, rel) + os.sep
        except Exception as ex:
            folder_preview.Text = ''
            _log('folder preview: {0}'.format(ex))

    def settings_light():
        return {'_doc': doc, 'split': bool(split_cb.IsChecked), 'fmt_folder': _get_ctl(fmt_folder_box),
                'date_folder': _get_ctl(date_combo), 'folder_order': _get_ctl(order_combo), '_stamp': _date_stamp(_get_ctl(date_combo))}
    for ctl in (split_cb,):
        ctl.Checked += _safe_handler(update_folder_preview)
        ctl.Unchecked += _safe_handler(update_folder_preview)
    for ctl in (date_combo, order_combo):
        ctl.SelectionChanged += _safe_handler(update_folder_preview)
    for ctl in (sub_box, path_box, fmt_folder_box):
        ctl.TextChanged += _safe_handler(update_folder_preview)
    qbar = WrapPanel()
    cr_top.Children.Add(qbar)
    queue_info = _text('', 12, RED, True)
    cr_top.Children.Add(queue_info)
    progress = ProgressBar()
    progress.Height = 14
    progress.Minimum = 0
    progress.Maximum = 100
    progress.Margin = Thickness(4)
    DockPanel.SetDock(progress, System.Windows.Controls.Dock.Bottom)
    cr_root.Children.Add(progress)
    queue_host = Grid()
    cr_root.Children.Add(queue_host)
    q = {'table': None, 'grid': None}
    _add_tab(tabs, '3  Create', cr_root)

    def settings():
        d = {}
        for k, c in reg.items():
            v = _get_ctl(c)
            if k.startswith('IFC.add.') and v == defaults.get(k):
                continue            # only send IFC options the user changed
            d[k] = v
        d['formats'] = [f for f in FORMAT_NAMES if bool(fmt_checks[f].IsChecked)]
        d['rule_sheets'] = st['rule']['Sheets']
        d['rule_views'] = st['rule']['Views']
        return d

    def open_root():
        root = _expand_path(_clean_root(_u(path_box.Text))).strip()
        if root and os.path.isdir(root):
            os.startfile(root)
        else:
            _show_message('The export folder does not exist yet.', error=True)

    def build_queue():
        cfg = settings()
        jobs = []
        formats = cfg['formats']
        entries = [(e, st['rule']['Sheets']) for e in checked_items('Sheets')] + [(e, st['rule']['Views']) for e in checked_items('Views')]
        sub_rule = _u(cfg.get('sub_rule', ''))
        warnings = []
        for fmt in formats:
            if fmt in MODEL_FORMATS:
                view = None
                if _u(cfg.get(fmt + '.source')) == 'Selected 3D view':
                    view = views3d_by_name.get(_u(cfg.get(fmt + '.view')))
                    if view is None:
                        warnings.append('{0}: no 3D view chosen - whole model will be exported.'.format(fmt))
                name = _expand_name(doc, None, cfg.get(fmt + '.name') or '{DocumentTitle}', 'Model')
                if view is not None:
                    name = name + '_' + _tidy(_u(view.Name))
                jobs.append({'fmt': fmt, 'items': [], 'name': name, 'label': ('3D view: ' + _u(view.Name)) if view is not None else 'Whole model', 'sub': '', 'view3d': view})
            elif fmt == 'PDF' and cfg.get('PDF.combine') and entries:
                name = _expand_name(doc, None, cfg.get('PDF.combined_name') or '{DocumentTitle}_Combined', 'Combined')
                jobs.append({'fmt': fmt, 'items': [e[0] for e in entries], 'name': name, 'label': '{0} item(s) combined'.format(len(entries)), 'sub': '', 'combine': True})
            else:
                for n_, (elem, rule) in enumerate(entries):
                    ctx = {'index': n_, 'fmt': fmt, 'fmt_index': formats.index(fmt)}
                    j = {'fmt': fmt, 'items': [elem], 'name': _expand_name(doc, elem, rule, 'Export', ctx),
                         'sub': _expand_subfolder(doc, elem, sub_rule, ctx),
                         'label': (_u(elem.SheetNumber) + ' - ' + _u(elem.Name)) if isinstance(elem, ViewSheet) else _u(elem.Name)}
                    if isinstance(elem, ViewSchedule) and fmt in SCHEDULE_UNSUPPORTED:
                        j['skip_reason'] = 'schedules cannot be exported as {0}'.format(fmt)
                    jobs.append(j)
        if not formats:
            warnings.append('No format is ticked on the Formats tab.')
        if not entries and any([f not in MODEL_FORMATS for f in formats]):
            warnings.append('No sheets or views are ticked on the Selection tab.')
        seen = {}
        dups = 0
        for j in jobs:
            k = (j['fmt'], j['sub'].lower(), j['name'].lower())
            if k in seen:
                dups += 1
            seen[k] = True
        if dups:
            warnings.append('{0} job(s) share a file name with another job - add {{SheetNumber}} to the rule to keep them apart.'.format(dups))
        st['jobs'] = jobs
        table = _new_datatable([('Format', System.String), ('Item', System.String), ('File name', System.String), ('Subfolder', System.String), ('Status', System.String), ('Key', System.String)], [])
        table.BeginLoadData()
        for i, j in enumerate(jobs):
            dr = table.NewRow()
            dr['Format'] = j['fmt']
            dr['Item'] = j['label']
            dr['File name'] = j['name'] + EXT.get(j['fmt'], '')
            dr['Subfolder'] = j['sub']
            dr['Status'] = ('Skipped: ' + j['skip_reason']) if j.get('skip_reason') else 'Queued'
            dr['Key'] = str(i)
            table.Rows.Add(dr)
        table.EndLoadData()
        if q['grid'] is not None:
            queue_host.Children.Remove(q['grid'])
        grid = _make_grid(table, False, None, False, ['Key'])
        grid.SelectionMode = System.Windows.Controls.DataGridSelectionMode.Extended
        menu = ContextMenu()
        mi = MenuItem()
        mi.Header = 'Remove from queue'
        mi.Click += _safe_handler(remove_selected)
        menu.Items.Add(mi)
        grid.ContextMenu = menu
        queue_host.Children.Add(grid)
        q['table'] = table
        q['grid'] = grid
        progress.Value = 0
        counts = {}
        for j in jobs:
            counts[j['fmt']] = counts.get(j['fmt'], 0) + 1
        queue_info.Text = 'Queue: {0} job(s)  ({1})'.format(len(jobs), ', '.join(['{0} x {1}'.format(v, k) for k, v in sorted(counts.items())]) or 'empty')
        _set_status(status, ('; '.join(warnings)) if warnings else 'Queue ready. Press Create to start.', bool(warnings))

    def remove_selected():
        if q['grid'] is None:
            return
        keys = [_u(r['Key']) for r in _selected_rows(q['grid'])]
        for r in list(q['table'].Rows):
            if _u(r['Key']) in keys:
                q['table'].Rows.Remove(r)
        queue_info.Text = 'Queue: {0} job(s) remain.'.format(q['table'].Rows.Count)

    def run_export(only_failed=False):
        if st['running']:
            return
        if q['table'] is None or q['table'].Rows.Count == 0:
            _show_message('The export queue is empty. Tick sheets/views and formats first.', error=True)
            return
        cfg = settings()
        root = _expand_path(_clean_root(_u(path_box.Text))).strip()
        if not root:
            _show_message('Choose an export location.', error=True)
            return
        try:
            if not os.path.isdir(root):
                os.makedirs(root)
        except Exception as ex:
            _show_message('Cannot create the export folder: {0}'.format(ex), error=True)
            return
        try:
            _save_json(os.path.join(_profiles_dir('EmperorExporter'), 'last_used.json'), cfg)
        except:
            pass
        policy = _u(cfg.get('policy', POLICIES[0]))
        ticked = [f for f in FORMAT_NAMES if f in cfg.get('formats', [])]
        cfg['_stamp'] = _date_stamp(cfg.get('date_folder'))       # one date folder for the whole run
        cfg['_doc'] = doc
        rows = []
        for r in q['table'].Rows:
            s = _u(r['Status'])
            if s.startswith('Done') or s.startswith('Skipped'):
                continue
            if only_failed and not s.startswith('Failed'):
                continue
            rows.append(r)
        if not rows:
            _set_status(status, 'Nothing to run: every job is already done or skipped.')
            return
        st['running'] = True
        st['cancel'] = False
        cancel_btn.IsEnabled = True
        report = [['File', 'Format', 'Item', 'Path', 'Seconds', 'Status', 'Notes']]
        t_all = time.time()
        ok_n = 0
        fail_n = 0
        skip_n = 0
        progress.Maximum = len(rows)
        progress.Value = 0
        try:
            for n, r in enumerate(rows):
                if st['cancel']:
                    for rest in rows[n:]:
                        rest['Status'] = 'Cancelled'
                    break
                job = st['jobs'][int(_u(r['Key']))]
                fmt = job['fmt']
                folder = _job_folder(root, fmt, ticked, job.get('sub', ''), cfg)
                t0 = time.time()
                problems = []
                try:
                    if not os.path.isdir(folder):
                        os.makedirs(folder)
                    r['Status'] = 'Exporting...'
                    _set_status(status, 'Exporting {0}/{1}: {2}'.format(n + 1, len(rows), job['label']))
                    _doevents(win)
                    def dispatch(job=job, fmt=fmt, folder=folder, problems=problems):
                        if fmt == 'PDF':
                            return _export_pdf(doc, job, folder, cfg, policy, problems)
                        if fmt in ('DWG', 'DXF', 'DGN'):
                            return _export_cad(doc, job, folder, cfg, policy, fmt, problems)
                        if fmt in ('DWF', 'DWFx'):
                            return _export_dwf(doc, job, folder, cfg, policy, fmt, problems)
                        if fmt == 'Images':
                            return _export_images(doc, job, folder, cfg, policy, problems)
                        if fmt == 'IFC':
                            return _export_ifc(doc, job, folder, cfg, policy, problems)
                        if fmt == 'NWC':
                            return _export_nwc(doc, job, folder, cfg, policy, problems)
                        raise Exception('Unsupported format.')
                    out = run_with_print_mode(doc, job['items'], fmt, cfg, problems, dispatch)
                    if out is None:
                        r['Status'] = 'Skipped: file exists'
                        skip_n += 1
                        report.append([job['name'], fmt, job['label'], '', '{0:.1f}'.format(time.time() - t0), 'Skipped (file exists)', ''])
                    else:
                        r['Status'] = 'Done' + (' (with notes)' if problems else '')
                        ok_n += 1
                        report.append([job['name'], fmt, job['label'], out, '{0:.1f}'.format(time.time() - t0), 'Success', '; '.join(problems)])
                    for pr in problems:
                        _log('Exporter note: {0}'.format(pr))
                except Exception as ex:
                    r['Status'] = 'Failed: {0}'.format(ex)
                    fail_n += 1
                    _log('Exporter job failed: {0}\n{1}'.format(ex, traceback.format_exc()))
                    report.append([job['name'], fmt, job['label'], '', '{0:.1f}'.format(time.time() - t0), 'Failed: {0}'.format(ex), '; '.join(problems)])
                progress.Value = n + 1
                _doevents(win)
        finally:
            st['running'] = False
            cancel_btn.IsEnabled = False
        total = time.time() - t_all
        report.append(['TOTAL', '', '', root, '{0:.1f}'.format(total), '{0} ok / {1} failed / {2} skipped'.format(ok_n, fail_n, skip_n), time.strftime('%Y-%m-%d %H:%M:%S')])
        report_path = ''
        if bool(cfg.get('report', True)):
            try:
                report_path = os.path.join(root, 'EmperorExporter_ExportReport.csv')
                _write_csv(report_path, report)
            except Exception as ex:
                report_path = ''
                _log('Export report failed: {0}'.format(ex))
        st['last_report'] = report_path
        st['last_root'] = root
        msg = 'Export finished: {0} succeeded, {1} failed, {2} skipped in {3:.1f}s.{4}'.format(ok_n, fail_n, skip_n, total, ' (cancelled)' if st['cancel'] else '')
        _set_status(status, msg, fail_n > 0)
        _show_message(msg + (('\n\nReport: ' + report_path) if report_path else '') + ('\n\nFailed rows stay in the queue: fix the cause and press Retry Failed.' if fail_n else ''), error=fail_n > 0)
        if bool(cfg.get('open', True)) and ok_n > 0 and not fail_n:
            try:
                os.startfile(root)
            except:
                pass

    def open_report():
        if st['last_report'] and os.path.exists(st['last_report']):
            os.startfile(st['last_report'])
        else:
            _show_message('No report has been written yet.', error=True)

    cancel_btn = _button('Cancel Export', 'close', lambda: st.__setitem__('cancel', True))
    cancel_btn.IsEnabled = False
    qbar.Children.Add(_button('Rebuild Queue', 'refresh', build_queue))
    qbar.Children.Add(_button('Remove Selected', 'clear', remove_selected))
    qbar.Children.Add(_button('Retry Failed', 'refresh', lambda: run_export(True)))
    qbar.Children.Add(cancel_btn)
    qbar.Children.Add(_button('Open Report', 'report', open_report))

    # ============================================================ navigation / profiles
    def on_tab_changed(sender, args):
        try:
            if args.OriginalSource is not tabs:
                return
            idx = tabs.SelectedIndex
            back_btn.IsEnabled = idx > 0
            next_btn.IsEnabled = idx < 2
            if idx == 2 and not st['running']:
                build_queue()
                update_folder_preview()
        except Exception as ex:
            _log('tab change: {0}'.format(ex))
    tabs.SelectionChanged += on_tab_changed

    def go_back():
        tabs.SelectedIndex = max(0, tabs.SelectedIndex - 1)

    def go_next():
        tabs.SelectedIndex = min(2, tabs.SelectedIndex + 1)

    def create_clicked():
        if tabs.SelectedIndex != 2:
            tabs.SelectedIndex = 2
            return
        run_export(False)

    back_btn = _button('Back', None, go_back, False, 80)
    next_btn = _button('Next', None, go_next, False, 80)
    footer.Children.Add(back_btn)
    footer.Children.Add(next_btn)
    footer.Children.Add(_button('Create', 'export', create_clicked, True, 110))
    back_btn.IsEnabled = False

    pdir = _profiles_dir('EmperorExporter')
    profile_combo = _combo(['(profile)'], 0, 220)

    def list_profiles():
        keep = _u(profile_combo.SelectedItem) if profile_combo.SelectedItem is not None else ''
        profile_combo.Items.Clear()
        profile_combo.Items.Add('(profile)')
        for fn in sorted(os.listdir(pdir)):
            if fn.lower().endswith('.json') and fn.lower() not in ('sets.json', 'last_used.json'):
                profile_combo.Items.Add(os.path.splitext(fn)[0])
        _set_ctl(profile_combo, keep)
        if profile_combo.SelectedIndex < 0:
            profile_combo.SelectedIndex = 0

    def apply_settings(d):
        for k, c in reg.items():
            if k in d:
                _set_ctl(c, d[k])
        for f in FORMAT_NAMES:
            fmt_checks[f].IsChecked = f in d.get('formats', [])
        st['rule']['Sheets'] = d.get('rule_sheets', DEFAULT_RULE)
        st['rule']['Views'] = d.get('rule_views', DEFAULT_VIEW_RULE)
        rule_box.Text = st['rule'][st['mode']]
        path_box.Text = _clean_root(_u(path_box.Text)) or default_path
        fmt_folder_box.Text = _fmt_folder_rule(fmt_folder_box.Text)
        if 'print_filter' not in d:
            print_cb.IsChecked = True
        update_folder_preview()

    def save_profile():
        name = _input_dialog(win, 'Save Profile', 'Profile name (formats, every option, naming rules, folders and conflict policy are saved):')
        if not name or not name.strip():
            return
        safe = _safe_filename(name.strip())
        _save_json(os.path.join(pdir, safe + '.json'), settings())
        list_profiles()
        _set_ctl(profile_combo, safe)
        _set_status(status, 'Profile saved: {0}'.format(safe))

    def load_profile():
        name = _u(profile_combo.SelectedItem) if profile_combo.SelectedItem is not None else ''
        if not name or name == '(profile)':
            return
        d = _load_json(os.path.join(pdir, name + '.json'), None)
        if d:
            apply_settings(d)
            _set_status(status, 'Profile loaded: {0}'.format(name))

    def delete_profile():
        name = _u(profile_combo.SelectedItem) if profile_combo.SelectedItem is not None else ''
        if not name or name == '(profile)':
            return
        if _ask_yes_no('Delete profile "{0}"?'.format(name)):
            try:
                os.remove(os.path.join(pdir, name + '.json'))
            except:
                pass
            list_profiles()

    def refresh_all():
        keep = dict([(m, set(checked_ids(m))) for m in ('Sheets', 'Views')])
        st['tables'].clear()
        st['items'].clear()
        grid_host.Children.Clear()
        for m in ('Sheets', 'Views'):
            if keep[m]:
                t, g = mode_table(m)
                for r in t.Rows:
                    r['Export'] = int(_u(r['Id'])) in keep[m]
        switch_mode(st['mode'])

    profile_combo.SelectionChanged += _safe_handler(load_profile)
    toolbar.Children.Add(_label('Profile', 52))
    toolbar.Children.Add(profile_combo)
    toolbar.Children.Add(_button('Save Profile', 'profile_save', save_profile))
    toolbar.Children.Add(_button('Delete', 'clear', delete_profile))
    toolbar.Children.Add(_button('Reload Project Data', 'refresh', refresh_all))

    list_profiles()
    last = _load_json(os.path.join(pdir, 'last_used.json'), None)
    if last:
        try:
            apply_settings(last)
        except Exception as ex:
            _log('last_used restore failed: {0}'.format(ex))
    switch_mode('Sheets')
    update_rule_preview()
    win.ShowDialog()
