# -*- coding: utf-8 -*-
"""Import Excel print area(s) into Revit drafting view(s), via a panel.

The panel lets you:
  - browse for one or more .xlsx files
  - create a new drafting view per file (named after the file, or with a
    name/prefix you type), OR
  - update a single existing drafting view from one Excel file

Reproduces, as closely as the Revit API allows: cell background fill, font
size/bold/italic/color (-> a matching TextNoteType), merged cells (drawn as
one region, text centered), and embedded images.

THIS VERSION RUNS ON IRONPYTHON (pyRevit's default engine) - deliberately.
An earlier version needed pyRevit's CPython engine for `openpyxl`, but that
engine failed to initialize in some setups (a pythonnet-level error
unrelated to this script). Rather than depend on that engine at all, this
version reads .xlsx files itself: an .xlsx is just a zip archive of XML
parts, so it's parsed directly with .NET's own System.IO.Compression and
System.Xml.Linq - both built into the .NET Framework, nothing to install.

Resolves both explicit RGB colors and theme-based colors (including tint
shading), and applies basic number formatting (date serials -> readable
dates, floating-point display noise trimmed) using the workbook's styles.
"""

import os
import re
import colorsys
import datetime as _dt
import tempfile
import traceback

from pyrevit import revit, DB, script

logger = script.get_logger()

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Collections")
clr.AddReference("System.Xml.Linq")
try:
    clr.AddReference("System.IO.Compression.FileSystem")
except Exception:
    pass
try:
    clr.AddReference("System.IO.Compression")
except Exception:
    pass

from System.Windows.Markup import XamlReader
from System.Windows import Visibility, MessageBox, MessageBoxButton, MessageBoxImage
from Microsoft.Win32 import OpenFileDialog
from System.Collections.Generic import List
from System.Xml.Linq import XDocument, XNamespace
from System.IO.Compression import ZipFile
from System.IO import MemoryStream, StreamReader, File as DotNetFile

doc = revit.doc


def alert(msg, title="Excel to Drafting"):
    try:
        import emperor_ui
        emperor_ui.alert(msg, title)
    except Exception:
        MessageBox.Show(msg, title, MessageBoxButton.OK, MessageBoxImage.Information)


def alert_error(msg, title="Excel to Drafting"):
    try:
        import emperor_ui
        emperor_ui.alert(msg, title, warn=True)
    except Exception:
        MessageBox.Show(msg, title, MessageBoxButton.OK, MessageBoxImage.Warning)


_CRASH_LOG_PATH = None


def _save_crash_log(text):
    global _CRASH_LOG_PATH
    candidates = []
    try:
        candidates.append(os.path.join(os.path.expanduser("~"), "Desktop",
                                        "ExcelToDrafting_error.log"))
    except Exception:
        pass
    candidates.append(os.path.join(tempfile.gettempdir(), "ExcelToDrafting_error.log"))
    for path in candidates:
        try:
            with open(path, "w") as f:
                f.write(text)
            _CRASH_LOG_PATH = path
            return path
        except Exception:
            continue
    return None


def _show_crash(tb_text, log_path):
    try:
        from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons
        td = TaskDialog("Excel to Drafting - Error")
        td.MainInstruction = "The import hit an unexpected error and stopped."
        last_line = tb_text.strip().splitlines()[-1] if tb_text.strip() else "Unknown error"
        content = last_line
        if log_path:
            content += "\n\nFull details saved to:\n{0}\n\nPlease copy that file's content back to Claude.".format(log_path)
        td.MainContent = content
        td.ExpandedContent = tb_text[:4000]
        td.CommonButtons = TaskDialogCommonButtons.Ok
        td.Show()
    except Exception:
        try:
            alert_error(tb_text[:1500])
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CONFIG - adjust these if the result comes out too big / too small
# ---------------------------------------------------------------------------
FEET_PER_COLWIDTH_UNIT = 0.0066   # ~7px + 5px padding per unit at 96dpi, converted to feet
FEET_PER_POINT = 1.0 / 864.0      # 1 pt = 1/72 in = 1/(72*12) ft - previously divided by 72
                                   # only, which made every row/font 12x too big and was the
                                   # cause of text overlapping across cells
DEFAULT_COL_WIDTH_UNITS = 8.43
DEFAULT_ROW_HEIGHT_PT = 15.0
TEXT_MARGIN_FT = 0.001
MIN_TEXT_SIZE_FT = 0.006
# Revit's TextNoteType "Text Size" behaves like cap-height, not the full
# em/point size Word/Excel use for font size - verified empirically (a
# string measured 1.46x wider in Revit than the same point size in Excel).
# Scaling the nominal point size down compensates.
TEXT_SIZE_FACTOR = 0.685
EMU_PER_FOOT = 914400.0 * 12.0

NS_MAIN = XNamespace.Get("http://schemas.openxmlformats.org/spreadsheetml/2006/main")
NS_PKGREL = XNamespace.Get("http://schemas.openxmlformats.org/package/2006/relationships")
NS_R = XNamespace.Get("http://schemas.openxmlformats.org/officeDocument/2006/relationships")
NS_XDR = XNamespace.Get("http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing")
NS_A = XNamespace.Get("http://schemas.openxmlformats.org/drawingml/2006/main")

_CELL_REF_RE = re.compile(r"^\$?([A-Za-z]+)\$?(\d+)$")


def col_letter_to_index(letters):
    idx = 0
    for ch in letters.upper():
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx


def parse_cell_ref(ref):
    m = _CELL_REF_RE.match(str(ref))
    if not m:
        return None
    return col_letter_to_index(m.group(1)), int(m.group(2))


def parse_range_ref(ref):
    parts = str(ref).replace("$", "").split(":")
    c0, r0 = parse_cell_ref(parts[0])
    if len(parts) == 2:
        c1, r1 = parse_cell_ref(parts[1])
    else:
        c1, r1 = c0, r0
    return (min(r0, r1), max(r0, r1), min(c0, c1), max(c0, c1))


# ---------------------------------------------------------------------------
# Minimal .xlsx (OOXML) reader - zip + XML only, no third-party libraries
# ---------------------------------------------------------------------------
def _read_entry_text(archive, name):
    entry = archive.GetEntry(name)
    if entry is None:
        return None
    stream = entry.Open()
    try:
        reader = StreamReader(stream)
        return reader.ReadToEnd()
    finally:
        stream.Close()


def _read_entry_bytes(archive, name):
    entry = archive.GetEntry(name)
    if entry is None:
        return None
    stream = entry.Open()
    try:
        ms = MemoryStream()
        stream.CopyTo(ms)
        return ms.ToArray()
    finally:
        stream.Close()


def _rels_path_for(part_path):
    if "/" in part_path:
        d, f = part_path.rsplit("/", 1)
        return d + "/_rels/" + f + ".rels"
    return "_rels/" + part_path + ".rels"


def _resolve_relative(base_part, target):
    if target.startswith("/"):
        return target.lstrip("/")
    base_dir = base_part.rsplit("/", 1)[0] if "/" in base_part else ""
    combined = (base_dir + "/" + target) if base_dir else target
    parts = []
    for seg in combined.split("/"):
        if seg == "..":
            if parts:
                parts.pop()
        elif seg == "." or seg == "":
            continue
        else:
            parts.append(seg)
    return "/".join(parts)


def _parse_rels(archive, part_path):
    """Returns {relId: resolved_target_path} for the given part's .rels file."""
    rels_xml = _read_entry_text(archive, _rels_path_for(part_path))
    mapping = {}
    if not rels_xml:
        return mapping
    rdoc = XDocument.Parse(rels_xml)
    for rel in rdoc.Root.Elements(NS_PKGREL + "Relationship"):
        rid = rel.Attribute("Id").Value
        target = rel.Attribute("Target").Value
        mode_attr = rel.Attribute("TargetMode")
        if mode_attr is not None and str(mode_attr.Value) == "External":
            continue
        mapping[rid] = _resolve_relative(part_path, target)
    return mapping


# Legacy indexed color palette (ECMA-376 Part 4, 18.8.27) - still used by
# older/legacy-styled workbooks via <color indexed="N"/>. aRGB strings;
# only the last 6 hex chars (RGB) are used.
_LEGACY_COLOR_INDEX = (
    '00000000', '00FFFFFF', '00FF0000', '0000FF00', '000000FF',
    '00FFFF00', '00FF00FF', '0000FFFF', '00000000', '00FFFFFF',
    '00FF0000', '0000FF00', '000000FF', '00FFFF00', '00FF00FF',
    '0000FFFF', '00800000', '00008000', '00000080', '00808000',
    '00800080', '00008080', '00C0C0C0', '00808080', '009999FF',
    '00993366', '00FFFFCC', '00CCFFFF', '00660066', '00FF8080',
    '000066CC', '00CCCCFF', '00000080', '00FF00FF', '00FFFF00',
    '0000FFFF', '00800080', '00800000', '00008080', '000000FF',
    '0000CCFF', '00CCFFFF', '00CCFFCC', '00FFFF99', '0099CCFF',
    '00FF99CC', '00CC99FF', '00FFCC99', '003366FF', '0033CCCC',
    '0099CC00', '00FFCC00', '00FF9900', '00FF6600', '00666699',
    '00969696', '00003366', '00339966', '00003300', '00333300',
    '00993300', '00993366', '00333399', '00333333',
)


# Excel's theme="N" index order in styles.xml (confirmed against multiple
# independent implementations): 0=lt1(bg1), 1=dk1(tx1), 2=lt2(bg2),
# 3=dk2(tx2), 4-9=accent1-6, 10=hlink, 11=folHlink. Note the 0/1 swap
# relative to the <clrScheme> declaration order (dk1, lt1, ...).
_THEME_SLOT_ORDER = ["lt1", "dk1", "lt2", "dk2",
                      "accent1", "accent2", "accent3", "accent4", "accent5", "accent6",
                      "hlink", "folHlink"]


def _find_rel_by_type(archive, part_path, type_suffix):
    rels_xml = _read_entry_text(archive, _rels_path_for(part_path))
    if not rels_xml:
        return None
    rdoc = XDocument.Parse(rels_xml)
    for rel in rdoc.Root.Elements(NS_PKGREL + "Relationship"):
        type_attr = rel.Attribute("Type")
        if type_attr is not None and str(type_attr.Value).endswith(type_suffix):
            return _resolve_relative(part_path, rel.Attribute("Target").Value)
    return None


def _parse_theme_colors(archive):
    """Returns a 12-entry list of hex RGB strings (or None), in the
    _THEME_SLOT_ORDER index order that styles.xml's theme="N" uses."""
    theme_part = _find_rel_by_type(archive, "xl/workbook.xml", "/theme") or "xl/theme/theme1.xml"
    theme_xml = _read_entry_text(archive, theme_part)
    if not theme_xml:
        return [None] * 12
    tdoc = XDocument.Parse(theme_xml)
    theme_els = tdoc.Root.Element(NS_A + "themeElements")
    if theme_els is None:
        return [None] * 12
    clr_scheme = theme_els.Element(NS_A + "clrScheme")
    if clr_scheme is None:
        return [None] * 12

    def read_slot(tag):
        el = clr_scheme.Element(NS_A + tag)
        if el is None:
            return None
        srgb = el.Element(NS_A + "srgbClr")
        if srgb is not None and srgb.Attribute("val") is not None:
            return str(srgb.Attribute("val").Value)
        sysc = el.Element(NS_A + "sysClr")
        if sysc is not None:
            last = sysc.Attribute("lastClr")
            if last is not None:
                return str(last.Value)
            val = sysc.Attribute("val")
            if val is not None:
                return "000000" if str(val.Value) == "windowText" else "FFFFFF"
        return None

    return [read_slot(tag) for tag in _THEME_SLOT_ORDER]


def apply_tint(hexcolor, tint):
    """OOXML tint shading (ECMA-376): darkens/lightens a color by adjusting
    its HSL lightness, keeping hue/saturation. tint in [-1, 1]."""
    if not hexcolor or not tint:
        return hexcolor
    try:
        r = int(hexcolor[0:2], 16) / 255.0
        g = int(hexcolor[2:4], 16) / 255.0
        b = int(hexcolor[4:6], 16) / 255.0
    except (ValueError, IndexError):
        return hexcolor
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if tint < 0:
        l = l * (1.0 + tint)
    else:
        l = l * (1.0 - tint) + tint
    l = max(0.0, min(1.0, l))
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return "%02X%02X%02X" % (int(round(r2 * 255)), int(round(g2 * 255)), int(round(b2 * 255)))


def _resolve_color_el(color_el, theme_colors):
    """Reads an OOXML <color> element: explicit rgb wins, then legacy
    indexed palette, then theme+tint."""
    if color_el is None:
        return None
    rgb_attr = color_el.Attribute("rgb")
    if rgb_attr is not None:
        return str(rgb_attr.Value)
    indexed_attr = color_el.Attribute("indexed")
    if indexed_attr is not None:
        try:
            iidx = int(str(indexed_attr.Value))
        except ValueError:
            iidx = None
        if iidx is not None and 0 <= iidx < len(_LEGACY_COLOR_INDEX):
            return _LEGACY_COLOR_INDEX[iidx][-6:]
        return None
    theme_attr = color_el.Attribute("theme")
    if theme_attr is not None:
        try:
            tidx = int(str(theme_attr.Value))
        except ValueError:
            return None
        base = theme_colors[tidx] if 0 <= tidx < len(theme_colors) else None
        if not base:
            return None
        tint = None
        tint_attr = color_el.Attribute("tint")
        if tint_attr is not None:
            try:
                tint = float(str(tint_attr.Value))
            except ValueError:
                tint = None
        return apply_tint(base, tint) if tint else base
    return None


# Built-in Excel numFmtId values that represent a date and/or time.
_BUILTIN_DATE_FMT_IDS = set([14, 15, 16, 17, 18, 19, 20, 21, 22,
                              27, 28, 29, 30, 31, 32, 33, 34, 35, 36,
                              45, 46, 47, 50, 51, 52, 53, 54, 55, 56, 57, 58])
_QUOTED_LITERAL_RE = re.compile(r'"[^"]*"')
_DATE_TOKEN_RE = re.compile(r'[ymdhs]{2,}')


def _is_date_format(numfmt_id, custom_numfmts):
    if numfmt_id in _BUILTIN_DATE_FMT_IDS:
        return True
    code = custom_numfmts.get(numfmt_id)
    if not code:
        return False
    stripped = _QUOTED_LITERAL_RE.sub("", code.lower())
    if "general" in stripped or "@" in stripped:
        return False
    return bool(_DATE_TOKEN_RE.search(stripped))


_EXCEL_EPOCH = _dt.datetime(1899, 12, 30)


def _excel_serial_to_date_str(serial):
    try:
        d = _EXCEL_EPOCH + _dt.timedelta(days=float(serial))
        if d.time() == _dt.time(0, 0, 0):
            return d.strftime("%m/%d/%Y")
        return d.strftime("%m/%d/%Y %H:%M")
    except Exception:
        return str(serial)


# Built-in (non-date) numeric formats worth honoring.
_BUILTIN_NUMFMT = {1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00", 9: "0%", 10: "0.00%",
                   37: "#,##0", 38: "#,##0", 39: "#,##0.00", 40: "#,##0.00"}


def _format_number_by_code(value, code):
    """Renders a number using the digit/decimal/thousands/percent parts of an
    Excel number-format code (first section only). Returns None if the code
    isn't a plain numeric format (e.g. General, text, scientific)."""
    section = _QUOTED_LITERAL_RE.sub("", code.split(";")[0])
    if "general" in section.lower() or "e+" in section.lower() or "@" in section:
        return None
    if not any(ch in section for ch in "0#?"):
        return None
    m = re.search(r"\.([0#?]+)", section)
    decimals = len(m.group(1)) if m else 0
    int_part = section.split(".")[0]
    thousands = "," in int_part
    percent = "%" in section
    v = float(value) * (100.0 if percent else 1.0)
    # Excel rounds half away from zero
    factor = 10 ** decimals
    v = (1 if v >= 0 else -1) * int(abs(v) * factor + 0.5 + 1e-9) / float(factor)
    fmt = "{0:,.%df}" if thousands else "{0:.%df}"
    text = (fmt % decimals).format(v)
    return text + ("%" if percent else "")


def format_cell_value(value, numfmt_id, custom_numfmts):
    """Applies the cell's number format: date serials become readable dates,
    numbers honor their decimal places / thousands separator / percent, and
    General-format floats have binary-floating-point noise trimmed the way
    Excel displays them. Text and booleans are left untouched."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if _is_date_format(numfmt_id, custom_numfmts):
            return _excel_serial_to_date_str(value)
        code = custom_numfmts.get(numfmt_id) or _BUILTIN_NUMFMT.get(numfmt_id)
        if code:
            try:
                rendered = _format_number_by_code(value, code)
            except Exception:
                rendered = None
            if rendered is not None:
                return rendered
        if isinstance(value, float):
            trimmed = float("%.10g" % value)
            return int(trimmed) if trimmed == int(trimmed) else trimmed
        return value
    return value


def read_xlsx(path):
    """Returns a dict describing the active sheet: print area, merges,
    column widths, row heights, cells (value + resolved font/fill), and
    images (extracted to temp files with anchor info)."""
    archive = ZipFile.OpenRead(path)
    try:
        wb_xml = _read_entry_text(archive, "xl/workbook.xml")
        wb_doc = XDocument.Parse(wb_xml)
        wb_rels = _parse_rels(archive, "xl/workbook.xml")

        sheets_el = wb_doc.Root.Element(NS_MAIN + "sheets")
        sheet_list = []
        for sh in sheets_el.Elements(NS_MAIN + "sheet"):
            name = sh.Attribute("name").Value
            rid = sh.Attribute(NS_R + "id").Value
            sheet_list.append((name, rid))
        if not sheet_list:
            raise ValueError("Workbook has no sheets: {0}".format(path))

        active_idx = 0
        bv_el = wb_doc.Root.Element(NS_MAIN + "bookViews")
        if bv_el is not None:
            wv = bv_el.Element(NS_MAIN + "workbookView")
            if wv is not None:
                at = wv.Attribute("activeTab")
                if at is not None:
                    try:
                        active_idx = int(str(at.Value))
                    except ValueError:
                        active_idx = 0
        if active_idx >= len(sheet_list):
            active_idx = 0
        active_name, active_rid = sheet_list[active_idx]
        sheet_part = wb_rels.get(active_rid)
        if not sheet_part:
            raise ValueError("Could not resolve the active sheet's part path in {0}".format(path))

        print_area_raw = None
        dn_el = wb_doc.Root.Element(NS_MAIN + "definedNames")
        if dn_el is not None:
            for dn in dn_el.Elements(NS_MAIN + "definedName"):
                if dn.Attribute("name") is not None and str(dn.Attribute("name").Value) == "_xlnm.Print_Area":
                    lsid = dn.Attribute("localSheetId")
                    idx = int(str(lsid.Value)) if lsid is not None else None
                    if idx == active_idx or idx is None:
                        print_area_raw = dn.Value
                        break

        # --- shared strings ---
        shared_strings = []
        ss_xml = _read_entry_text(archive, "xl/sharedStrings.xml")
        if ss_xml:
            ss_doc = XDocument.Parse(ss_xml)
            for si in ss_doc.Root.Elements(NS_MAIN + "si"):
                texts = [t.Value for t in si.Descendants(NS_MAIN + "t")]
                shared_strings.append("".join(texts))

        # --- theme colors (for theme="N" / tint resolution below) ---
        theme_colors = _parse_theme_colors(archive)

        # --- styles ---
        fonts, fills, borders, cellXfs = [], [], [], []
        custom_numfmts = {}
        styles_xml = _read_entry_text(archive, "xl/styles.xml")
        if styles_xml:
            sdoc = XDocument.Parse(styles_xml)
            numfmts_el = sdoc.Root.Element(NS_MAIN + "numFmts")
            if numfmts_el is not None:
                for nf in numfmts_el.Elements(NS_MAIN + "numFmt"):
                    try:
                        nfid = int(str(nf.Attribute("numFmtId").Value))
                        custom_numfmts[nfid] = str(nf.Attribute("formatCode").Value)
                    except (ValueError, AttributeError):
                        pass
            fonts_el = sdoc.Root.Element(NS_MAIN + "fonts")
            if fonts_el is not None:
                for f in fonts_el.Elements(NS_MAIN + "font"):
                    sz_el = f.Element(NS_MAIN + "sz")
                    size = float(str(sz_el.Attribute("val").Value)) if sz_el is not None else 11.0
                    bold = f.Element(NS_MAIN + "b") is not None
                    italic = f.Element(NS_MAIN + "i") is not None
                    color = _resolve_color_el(f.Element(NS_MAIN + "color"), theme_colors)
                    name_el = f.Element(NS_MAIN + "name")
                    fname = str(name_el.Attribute("val").Value) if (name_el is not None and name_el.Attribute("val") is not None) else None
                    fonts.append({"size": size, "bold": bold, "italic": italic, "color": color, "name": fname})
            fills_el = sdoc.Root.Element(NS_MAIN + "fills")
            if fills_el is not None:
                for fl in fills_el.Elements(NS_MAIN + "fill"):
                    pf = fl.Element(NS_MAIN + "patternFill")
                    fill_color = None
                    if pf is not None and pf.Attribute("patternType") is not None:
                        if str(pf.Attribute("patternType").Value) == "solid":
                            fill_color = _resolve_color_el(pf.Element(NS_MAIN + "fgColor"), theme_colors)
                    fills.append(fill_color)
            borders_el = sdoc.Root.Element(NS_MAIN + "borders")
            if borders_el is not None:
                for b in borders_el.Elements(NS_MAIN + "border"):
                    def _side(tag):
                        el = b.Element(NS_MAIN + tag)
                        if el is None or el.Attribute("style") is None:
                            return None
                        style_name = str(el.Attribute("style").Value)
                        color_hex = _resolve_color_el(el.Element(NS_MAIN + "color"), theme_colors)
                        return (style_name, color_hex)
                    borders.append({
                        "left": _side("left"), "right": _side("right"),
                        "top": _side("top"), "bottom": _side("bottom"),
                    })
            xfs_el = sdoc.Root.Element(NS_MAIN + "cellXfs")
            if xfs_el is not None:
                for xf in xfs_el.Elements(NS_MAIN + "xf"):
                    fid = int(str(xf.Attribute("fontId").Value)) if xf.Attribute("fontId") is not None else 0
                    flid = int(str(xf.Attribute("fillId").Value)) if xf.Attribute("fillId") is not None else 0
                    nfid = int(str(xf.Attribute("numFmtId").Value)) if xf.Attribute("numFmtId") is not None else 0
                    bid = int(str(xf.Attribute("borderId").Value)) if xf.Attribute("borderId") is not None else 0
                    align_el = xf.Element(NS_MAIN + "alignment")
                    wrap_text = False
                    horiz = None
                    vert = None
                    reading_order = 0
                    if align_el is not None:
                        wrap_attr = align_el.Attribute("wrapText")
                        wrap_text = wrap_attr is not None and str(wrap_attr.Value) in ("1", "true")
                        h_attr = align_el.Attribute("horizontal")
                        horiz = str(h_attr.Value) if h_attr is not None else None
                        v_attr = align_el.Attribute("vertical")
                        vert = str(v_attr.Value) if v_attr is not None else None
                        ro_attr = align_el.Attribute("readingOrder")
                        # 0 = context-dependent (follow sheet default), 1 = LTR, 2 = RTL
                        reading_order = int(str(ro_attr.Value)) if ro_attr is not None else 0
                    cellXfs.append({"fontId": fid, "fillId": flid, "numFmtId": nfid, "borderId": bid,
                                     "wrapText": wrap_text, "horizontal": horiz, "vertical": vert,
                                     "readingOrder": reading_order})
        if not fonts:
            fonts = [{"size": 11.0, "bold": False, "italic": False, "color": None, "name": None}]
        if not fills:
            fills = [None]
        if not borders:
            borders = [{"left": None, "right": None, "top": None, "bottom": None}]
        if not cellXfs:
            cellXfs = [{"fontId": 0, "fillId": 0, "numFmtId": 0, "borderId": 0,
                        "wrapText": False, "horizontal": None, "vertical": None, "readingOrder": 0}]

        def style_for(idx):
            xf = cellXfs[idx] if 0 <= idx < len(cellXfs) else cellXfs[0]
            font = fonts[xf["fontId"]] if 0 <= xf["fontId"] < len(fonts) else fonts[0]
            fill = fills[xf["fillId"]] if 0 <= xf["fillId"] < len(fills) else fills[0]
            bid = xf.get("borderId", 0)
            border = borders[bid] if 0 <= bid < len(borders) else borders[0]
            align = {"wrapText": xf.get("wrapText", False), "horizontal": xf.get("horizontal"),
                      "vertical": xf.get("vertical"), "readingOrder": xf.get("readingOrder", 0)}
            return font, fill, xf.get("numFmtId", 0), border, align

        # --- sheet data ---
        sheet_xml = _read_entry_text(archive, sheet_part)
        sdoc2 = XDocument.Parse(sheet_xml)
        root = sdoc2.Root

        is_rtl = False
        sheet_views_el = root.Element(NS_MAIN + "sheetViews")
        if sheet_views_el is not None:
            sv = sheet_views_el.Element(NS_MAIN + "sheetView")
            if sv is not None:
                rtl_attr = sv.Attribute("rightToLeft")
                is_rtl = rtl_attr is not None and str(rtl_attr.Value) in ("1", "true")

        # Excel sheet-level defaults matter when individual dimensions are
        # omitted. Hidden rows/columns should not be rendered either.
        default_col_width = DEFAULT_COL_WIDTH_UNITS
        default_row_height_pt = DEFAULT_ROW_HEIGHT_PT
        sheet_format_el = root.Element(NS_MAIN + "sheetFormatPr")
        if sheet_format_el is not None:
            dcw_attr = sheet_format_el.Attribute("defaultColWidth")
            drh_attr = sheet_format_el.Attribute("defaultRowHeight")
            if dcw_attr is not None:
                try:
                    default_col_width = float(str(dcw_attr.Value))
                except ValueError:
                    pass
            if drh_attr is not None:
                try:
                    default_row_height_pt = float(str(drh_attr.Value))
                except ValueError:
                    pass

        col_widths = {}
        hidden_cols = set()
        cols_el = root.Element(NS_MAIN + "cols")
        if cols_el is not None:
            for c in cols_el.Elements(NS_MAIN + "col"):
                cmin_attr = c.Attribute("min")
                cmax_attr = c.Attribute("max")
                if cmin_attr is None or cmax_attr is None:
                    continue
                cmin = int(str(cmin_attr.Value))
                cmax = int(str(cmax_attr.Value))
                hidden_attr = c.Attribute("hidden")
                is_hidden = hidden_attr is not None and str(hidden_attr.Value) in ("1", "true")
                w_attr = c.Attribute("width")
                w = default_col_width
                if w_attr is not None:
                    try:
                        w = float(str(w_attr.Value))
                    except ValueError:
                        w = default_col_width
                for ci in range(cmin, min(cmax, cmin + 500) + 1):
                    col_widths[ci] = w
                    if is_hidden:
                        hidden_cols.add(ci)

        row_heights = {}
        hidden_rows = set()
        cells = {}
        max_row_seen, max_col_seen = 1, 1
        sd_el = root.Element(NS_MAIN + "sheetData")
        if sd_el is not None:
            for row_el in sd_el.Elements(NS_MAIN + "row"):
                row_idx = int(str(row_el.Attribute("r").Value))
                ht_attr = row_el.Attribute("ht")
                if ht_attr is not None:
                    try:
                        row_heights[row_idx] = float(str(ht_attr.Value))
                    except ValueError:
                        pass
                hidden_attr = row_el.Attribute("hidden")
                if hidden_attr is not None and str(hidden_attr.Value) in ("1", "true"):
                    hidden_rows.add(row_idx)
                for c_el in row_el.Elements(NS_MAIN + "c"):
                    ref_attr = c_el.Attribute("r")
                    if ref_attr is None:
                        continue
                    parsed = parse_cell_ref(ref_attr.Value)
                    if not parsed:
                        continue
                    col_idx, _r = parsed
                    s_attr = c_el.Attribute("s")
                    style_idx = int(str(s_attr.Value)) if s_attr is not None else 0
                    t_attr = c_el.Attribute("t")
                    ctype = str(t_attr.Value) if t_attr is not None else "n"
                    value = None
                    if ctype == "s":
                        v_el = c_el.Element(NS_MAIN + "v")
                        if v_el is not None:
                            try:
                                sidx = int(str(v_el.Value))
                                if 0 <= sidx < len(shared_strings):
                                    value = shared_strings[sidx]
                            except ValueError:
                                pass
                    elif ctype == "inlineStr":
                        is_el = c_el.Element(NS_MAIN + "is")
                        if is_el is not None:
                            value = "".join([t.Value for t in is_el.Descendants(NS_MAIN + "t")])
                    elif ctype == "b":
                        v_el = c_el.Element(NS_MAIN + "v")
                        if v_el is not None:
                            value = (str(v_el.Value) == "1")
                    elif ctype == "str":
                        v_el = c_el.Element(NS_MAIN + "v")
                        if v_el is not None:
                            value = str(v_el.Value)
                    else:
                        v_el = c_el.Element(NS_MAIN + "v")
                        if v_el is not None and str(v_el.Value) != "":
                            raw = str(v_el.Value)
                            try:
                                fval = float(raw)
                                value = int(fval) if fval == int(fval) else fval
                            except ValueError:
                                value = raw
                    cells[(row_idx, col_idx)] = {"value": value, "style": style_idx}
                    if row_idx > max_row_seen:
                        max_row_seen = row_idx
                    if col_idx > max_col_seen:
                        max_col_seen = col_idx

        merges = []
        mc_el = root.Element(NS_MAIN + "mergeCells")
        if mc_el is not None:
            for m in mc_el.Elements(NS_MAIN + "mergeCell"):
                ref_attr = m.Attribute("ref")
                if ref_attr is not None:
                    merges.append(parse_range_ref(ref_attr.Value))

        if print_area_raw:
            # Preserve all print-area ranges by rendering their overall
            # bounding box. This also handles a non-contiguous print area.
            print_ranges = []
            for part in str(print_area_raw).split(","):
                part = part.strip()
                if "!" in part:
                    part = part.split("!")[-1]
                try:
                    print_ranges.append(parse_range_ref(part))
                except Exception:
                    pass
            if print_ranges:
                min_row = min(r[0] for r in print_ranges)
                max_row = max(r[1] for r in print_ranges)
                min_col = min(r[2] for r in print_ranges)
                max_col = max(r[3] for r in print_ranges)
            else:
                min_row, min_col = 1, 1
                max_row, max_col = max_row_seen, max_col_seen
        else:
            min_row, min_col = 1, 1
            max_row, max_col = max_row_seen, max_col_seen

        # --- images (via the sheet's own drawing, if any) ---
        images = []
        sheet_rels = _parse_rels(archive, sheet_part)
        drawing_part = None
        sheet_rels_xml = _read_entry_text(archive, _rels_path_for(sheet_part))
        if sheet_rels_xml:
            rdoc = XDocument.Parse(sheet_rels_xml)
            for rel in rdoc.Root.Elements(NS_PKGREL + "Relationship"):
                type_attr = rel.Attribute("Type")
                if type_attr is not None and str(type_attr.Value).endswith("/drawing"):
                    drawing_part = _resolve_relative(sheet_part, rel.Attribute("Target").Value)
                    break

        if drawing_part:
            drawing_xml = _read_entry_text(archive, drawing_part)
            if drawing_xml:
                ddoc = XDocument.Parse(drawing_xml)
                drawing_rid_map = _parse_rels(archive, drawing_part)

                def parse_marker(el):
                    return {
                        "col": int(str(el.Element(NS_XDR + "col").Value)),
                        "colOff": int(str(el.Element(NS_XDR + "colOff").Value)),
                        "row": int(str(el.Element(NS_XDR + "row").Value)),
                        "rowOff": int(str(el.Element(NS_XDR + "rowOff").Value)),
                    }

                for tag in ("twoCellAnchor", "oneCellAnchor"):
                    for anchor in ddoc.Root.Elements(NS_XDR + tag):
                        from_el = anchor.Element(NS_XDR + "from")
                        frm = parse_marker(from_el) if from_el is not None else None
                        to_el = anchor.Element(NS_XDR + "to")
                        to = parse_marker(to_el) if to_el is not None else None
                        ext = None
                        ext_el = anchor.Element(NS_XDR + "ext")
                        if ext_el is not None and ext_el.Attribute("cx") is not None:
                            ext = (int(str(ext_el.Attribute("cx").Value)), int(str(ext_el.Attribute("cy").Value)))
                        blip_rid = None
                        for b in anchor.Descendants(NS_A + "blip"):
                            embed_attr = b.Attribute(NS_R + "embed")
                            if embed_attr is not None:
                                blip_rid = str(embed_attr.Value)
                                break
                        if frm and blip_rid and blip_rid in drawing_rid_map:
                            images.append({
                                "from": frm, "to": to, "ext": ext,
                                "part": drawing_rid_map[blip_rid],
                            })

        return {
            "min_row": min_row, "max_row": max_row, "min_col": min_col, "max_col": max_col,
            "col_widths": col_widths, "row_heights": row_heights,
            "hidden_cols": hidden_cols, "hidden_rows": hidden_rows,
            "default_col_width": default_col_width,
            "default_row_height_pt": default_row_height_pt,
            "cells": cells, "merges": merges, "style_for": style_for, "is_rtl": is_rtl,
            "custom_numfmts": custom_numfmts,
            "images": images, "archive_path": path,
        }
    finally:
        archive.Dispose()


def extract_image_bytes(path, part):
    archive = ZipFile.OpenRead(path)
    try:
        return _read_entry_bytes(archive, part)
    finally:
        archive.Dispose()


# ---------------------------------------------------------------------------
# Panel (raw WPF - no pyrevit.forms), Emperor red & white theme (lib/emperor_ui.py)
# ---------------------------------------------------------------------------
_FALLBACK_RESOURCES = (
    '<SolidColorBrush x:Key="Red" Color="#8B111C"/>'
    '<SolidColorBrush x:Key="Line" Color="#D8CBCD"/>'
    '<SolidColorBrush x:Key="Muted" Color="#77777D"/>'
    '<SolidColorBrush x:Key="HeaderBrush" Color="#8B111C"/>'
    '<Style x:Key="RedBtn" TargetType="Button"><Setter Property="Background" Value="#8B111C"/>'
    '<Setter Property="Foreground" Value="White"/><Setter Property="Padding" Value="12,5"/></Style>'
    '<Style x:Key="OutlineBtn" TargetType="Button"><Setter Property="Padding" Value="12,5"/></Style>'
)

def show_panel():
    xaml_path = os.path.join(os.path.dirname(__file__), "ExcelImportUI.xaml")
    with open(xaml_path, "r") as f:
        xaml_text = f.read()
    try:
        import emperor_ui
        xaml_text = emperor_ui.inject(xaml_text)
    except Exception as ex:
        # No Emperor theme: plain controls. Keys used with StaticResource must still exist.
        logger.debug("Emperor theme not loaded: {0}".format(ex))
        xaml_text = xaml_text.replace("<!--EMPEROR_THEME-->", _FALLBACK_RESOURCES)
    window = XamlReader.Parse(xaml_text)
    try:
        import emperor_ui
        emperor_ui.enable_mouse_glow(window)
    except Exception:
        pass

    lb_files = window.FindName("lb_files")
    btn_add = window.FindName("btn_add")
    btn_remove = window.FindName("btn_remove")
    rb_new = window.FindName("rb_new")
    rb_update = window.FindName("rb_update")
    lbl_viewname = window.FindName("lbl_viewname")
    tb_viewname = window.FindName("tb_viewname")
    lbl_targetview = window.FindName("lbl_targetview")
    cb_views = window.FindName("cb_views")
    btn_ok = window.FindName("btn_ok")
    btn_cancel = window.FindName("btn_cancel")

    drafting_views = sorted(
        [v for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewDrafting) if not v.IsTemplate],
        key=lambda v: v.Name,
    )
    for v in drafting_views:
        cb_views.Items.Add(v.Name)
    if drafting_views:
        cb_views.SelectedIndex = 0

    result = {"ok": False, "files": [], "mode": "new", "view_name": "", "target_view": None}

    def add_files(sender, args):
        dlg = OpenFileDialog()
        dlg.Filter = "Excel Files (*.xlsx)|*.xlsx"
        dlg.Multiselect = True
        dlg.Title = "Select Excel file(s)"
        if dlg.ShowDialog():
            existing = list(lb_files.Items)
            for p in dlg.FileNames:
                if p not in existing:
                    lb_files.Items.Add(p)

    def remove_files(sender, args):
        for item in list(lb_files.SelectedItems):
            lb_files.Items.Remove(item)

    def mode_changed(sender, args):
        is_new = bool(rb_new.IsChecked)
        tb_viewname.Visibility = Visibility.Visible if is_new else Visibility.Collapsed
        lbl_viewname.Visibility = Visibility.Visible if is_new else Visibility.Collapsed
        cb_views.Visibility = Visibility.Collapsed if is_new else Visibility.Visible
        lbl_targetview.Visibility = Visibility.Collapsed if is_new else Visibility.Visible

    def ok_clicked(sender, args):
        files = list(lb_files.Items)
        if not files:
            alert_error("Add at least one Excel file.")
            return
        if rb_update.IsChecked:
            if len(files) != 1:
                alert_error("Pick exactly one Excel file when updating an existing view.")
                return
            if not drafting_views or cb_views.SelectedIndex < 0:
                alert_error("Pick a target drafting view to update.")
                return
            result["mode"] = "update"
            result["target_view"] = drafting_views[cb_views.SelectedIndex]
        else:
            result["mode"] = "new"
            result["view_name"] = tb_viewname.Text.strip() if tb_viewname.Text else ""
        result["files"] = files
        result["ok"] = True
        window.DialogResult = True
        window.Close()

    def cancel_clicked(sender, args):
        window.DialogResult = False
        window.Close()

    btn_add.Click += add_files
    btn_remove.Click += remove_files
    rb_new.Checked += mode_changed
    rb_update.Checked += mode_changed
    btn_ok.Click += ok_clicked
    btn_cancel.Click += cancel_clicked

    window.ShowDialog()
    return result


# ---------------------------------------------------------------------------
# View helpers
# ---------------------------------------------------------------------------
def unique_view_name(base_name):
    existing = set(v.Name for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewDrafting) if not v.IsTemplate)
    name = base_name
    i = 2
    while name in existing:
        name = "{0} ({1})".format(base_name, i)
        i += 1
    return name


def create_drafting_view(name):
    vft = None
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType).ToElements():
        if v.ViewFamily == DB.ViewFamily.Drafting:
            vft = v
            break
    if vft is None:
        raise Exception("No Drafting ViewFamilyType found in this project/template.")
    new_view = DB.ViewDrafting.Create(doc, vft.Id)
    new_view.Name = unique_view_name(name)
    return new_view


def force_true_scale(view):
    """All the coordinate math in import_workbook assumes true 1:1
    paper-inch positions. Revit keeps TextNote height constant regardless
    of view scale, but FilledRegions/ImageInstances (ordinary detail
    geometry) shrink or grow WITH the view's scale - so unless the view is
    at 1:1, cell backgrounds and text drift out of sync and overlap. Force
    it to 1:1 before drawing; the user can freely change the scale
    afterward (Revit will resize the geometry to match, keeping text at
    its true size, which is the normal intended workflow)."""
    try:
        if view.Scale != 1:
            view.Scale = 1
    except Exception as ex:
        logger.debug("Could not force view '{0}' to 1:1 scale: {1}".format(view.Name, ex))


def clear_previous_import(view):
    ids = List[DB.ElementId]()
    for cls in (DB.FilledRegion, DB.TextNote, DB.ImageInstance, DB.DetailLine):
        for el in DB.FilteredElementCollector(doc, view.Id).OfClass(cls):
            ids.Add(el.Id)
    if ids.Count:
        doc.Delete(ids)


# ---------------------------------------------------------------------------
# Color / fill / text-type helpers (cached across all files in this run)
# ---------------------------------------------------------------------------
def hex_to_color(hexstr):
    if not hexstr or len(hexstr) < 6:
        return None
    hexstr = hexstr[-6:]
    try:
        return DB.Color(int(hexstr[0:2], 16), int(hexstr[2:4], 16), int(hexstr[4:6], 16))
    except ValueError:
        return None


_solid_pattern_id = [None]

# Problems that would otherwise be swallowed silently. Collected as
# {message: count} and shown in the "Done" summary.
diagnostics = {}


def note_problem(where, ex):
    key = "{0}: {1}: {2}".format(where, type(ex).__name__, ex)
    diagnostics[key] = diagnostics.get(key, 0) + 1


def get_solid_fill_pattern_id():
    """A FilledRegionType needs a solid pattern whose target is DRAFTING
    (a solid *model* pattern is rejected)."""
    if _solid_pattern_id[0] is not None:
        return _solid_pattern_id[0]
    for fp in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement):
        try:
            pat = fp.GetFillPattern()
            if pat.IsSolidFill and pat.Target == DB.FillPatternTarget.Drafting:
                _solid_pattern_id[0] = fp.Id
                return _solid_pattern_id[0]
        except Exception:
            continue
    for name in ("Solid fill", "<Solid fill>"):
        fp = DB.FillPatternElement.GetFillPatternElementByName(doc, DB.FillPatternTarget.Drafting, name)
        if fp:
            _solid_pattern_id[0] = fp.Id
            return _solid_pattern_id[0]
    _solid_pattern_id[0] = DB.ElementId.InvalidElementId
    return _solid_pattern_id[0]


def _resolve_element(raw):
    """Return a real Autodesk.Revit.DB.Element for either an Element or ElementId.

    In normal Revit API usage FilteredElementCollector iteration yields Elements.
    Some IronPython/pyRevit combinations can expose ElementIds instead, so all
    type-selection code deliberately normalizes the value before touching .Name.
    """
    if raw is None:
        return None
    try:
        if isinstance(raw, DB.ElementId):
            return doc.GetElement(raw)
    except Exception:
        pass
    try:
        rid = raw.Id
        if isinstance(rid, DB.ElementId):
            resolved = doc.GetElement(rid)
            return resolved if resolved is not None else raw
    except Exception:
        pass
    return raw


def _element_name(raw):
    """Safely get an Element name, resolving ElementId first."""
    el = _resolve_element(raw)
    if el is None:
        return ""
    try:
        return str(el.Name)
    except Exception:
        # Some element wrappers do not surface Name, but the built-in
        # element name parameter is still available for ElementType objects.
        try:
            p = el.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
            if p and p.HasValue:
                return p.AsString() or ""
        except Exception:
            pass
        return ""


def _pick_base_type(type_cls):
    """Find a usable base type and always return the actual Element object.

    Do not rely on Python iteration over FilteredElementCollector here. The
    Revit API documents ToElements() as the element-returning method, while
    ToElementIds()/FirstElementId() return ElementIds. Normalizing both forms
    makes this safe under pyRevit/IronPython wrappers too.
    """
    first_any = None
    first_other = None
    try:
        collector = DB.FilteredElementCollector(doc).OfClass(type_cls)
        try:
            raw_items = collector.ToElements()
        except Exception:
            raw_items = collector
        for raw in raw_items:
            t = _resolve_element(raw)
            if t is None:
                continue
            if first_any is None:
                first_any = t
            tname = _element_name(t)
            if tname and not tname.startswith("XL_"):
                first_other = t
                break
    except Exception as ex:
        note_problem("enumerating types to pick a base type", ex)

    if first_other is not None:
        return first_other
    if first_any is not None:
        return first_any

    # Last-resort route: use the element id then explicitly resolve it.
    try:
        eid = DB.FilteredElementCollector(doc).OfClass(type_cls).FirstElementId()
        if eid is not None:
            return _resolve_element(eid)
    except Exception as ex:
        note_problem("FirstElementId fallback while picking a base type", ex)
    return None


def _duplicate_type(base_type, name, type_cls):
    """Duplicate an ElementType and return the actual new ElementType.

    Duplicate() should return an ElementType, but normalize ElementId/object
    wrappers and use explicit element-id retrieval as the fallback.
    """
    base_type = _resolve_element(base_type)
    if base_type is None:
        raise Exception("No usable base type found for {0}".format(type_cls))

    try:
        dup = _resolve_element(base_type.Duplicate(name))
        if dup is not None:
            return dup
    except Exception:
        pass

    try:
        collector = DB.FilteredElementCollector(doc).OfClass(type_cls)
        try:
            raw_items = collector.ToElements()
        except Exception:
            raw_items = collector
        for raw in raw_items:
            t = _resolve_element(raw)
            if _element_name(t) == name:
                return t
    except Exception:
        pass

    # Re-run Duplicate so the original API exception is preserved when no
    # existing type can be reused.
    return _resolve_element(base_type.Duplicate(name))


_region_type_cache = {}
_base_region_type = [None]
_invisible_line_style_id = [False]   # False = not looked up yet, None = unavailable


def get_invisible_line_style_id():
    """Style for filled-region outlines: Excel fills have no outline of
    their own (borders are drawn separately), so hide Revit's default one."""
    if _invisible_line_style_id[0] is not False:
        return _invisible_line_style_id[0]
    result = None
    try:
        cat = DB.Category.GetCategory(doc, DB.BuiltInCategory.OST_InvisibleLines)
        if cat is not None:
            gs = cat.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
            if gs is not None:
                result = gs.Id
    except Exception as ex:
        note_problem("invisible line style lookup (OST_InvisibleLines)", ex)
    if result is None:
        # Some templates don't expose OST_InvisibleLines directly - it's
        # really a subcategory of "Lines", so look for it there by name.
        try:
            lines_cat = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
            if lines_cat is not None:
                for sub in lines_cat.SubCategories:
                    if sub.Name in ("Invisible lines", "Invisible Lines", "<Invisible lines>"):
                        gs = sub.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
                        if gs is not None:
                            result = gs.Id
                            break
        except Exception as ex:
            note_problem("invisible line style lookup (Lines subcategory)", ex)
    _invisible_line_style_id[0] = result
    return result


def _set_region_colors(new_type, color, pattern_id):
    """Sets a solid foreground pattern + color. Tries the direct property
    setters, then the parameter-based routes as fallbacks."""
    try:
        new_type.ForegroundPatternId = pattern_id
        new_type.ForegroundPatternColor = color
        try:
            new_type.BackgroundPatternId = DB.ElementId.InvalidElementId
        except Exception:
            pass
        return True
    except Exception as ex:
        note_problem("FilledRegionType property setters", ex)
    try:
        any_set = False
        for ptid, val in ((DB.ParameterTypeId.ForegroundAnyPatternIdParam, pattern_id),
                          (DB.ParameterTypeId.ForegroundPatternColorParam, color)):
            p = new_type.GetParameter(ptid)
            if p and not p.IsReadOnly:
                p.Set(val)
                any_set = True
        if any_set:
            return True
    except Exception as ex:
        note_problem("FilledRegionType ParameterTypeId setters", ex)
    try:
        any_set = False
        for bip, val in ((DB.BuiltInParameter.FOREGROUND_ANY_PATTERN_ID_PARAM, pattern_id),
                         (DB.BuiltInParameter.FOREGROUND_PATTERN_COLOR_PARAM, color)):
            p = new_type.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(val)
                any_set = True
        return any_set
    except Exception as ex:
        note_problem("FilledRegionType BuiltInParameter setters", ex)
        return False


def get_filled_region_type(color):
    if color is None:
        return None
    key = (color.Red, color.Green, color.Blue)
    if key in _region_type_cache:
        return _region_type_cache[key]
    if _base_region_type[0] is None:
        _base_region_type[0] = _pick_base_type(DB.FilledRegionType)
    if _base_region_type[0] is None:
        note_problem("no usable FilledRegionType found in this document at all", Exception("none found"))
        return None
    base_id = _base_region_type[0].Id
    name = "XL_fill_%02X%02X%02X" % key
    result_id = base_id
    try:
        # Reuse an existing generated type on later button clicks, but ALWAYS
        # re-apply the expected properties. This is important because pyRevit
        # can keep the IronPython engine alive between runs while the cache is
        # reset; the element itself survives in the Revit document.
        new_type = _duplicate_type(_base_region_type[0], name, DB.FilledRegionType)
        if not _set_region_colors(new_type, color, get_solid_fill_pattern_id()):
            fill_color_failures[0] += 1
        result_id = new_type.Id
    except Exception as ex:
        note_problem("creating/refreshing FilledRegionType {0}".format(name), ex)
        result_id = base_id
    _region_type_cache[key] = result_id
    return result_id


fill_color_failures = [0]

_text_type_cache = {}
_base_text_type = [None]


def color_to_line_color_int(color):
    return color.Red + (color.Green << 8) + (color.Blue << 16)


def get_text_type(size_ft, bold, italic, color, font_name=None):
    size_ft = max(size_ft, MIN_TEXT_SIZE_FT)
    rgb_key = (color.Red, color.Green, color.Blue) if color else (0, 0, 0)
    key = (round(size_ft, 4), bool(bold), bool(italic), rgb_key, font_name or "")
    if key in _text_type_cache:
        return _text_type_cache[key]
    if _base_text_type[0] is None:
        # Revit 2024 exposes the document's default text-note type directly.
        # This avoids the ElementId-vs-Element ambiguity seen in some
        # IronPython/pyRevit collector iterations.
        try:
            default_id = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
            _base_text_type[0] = _resolve_element(default_id)
        except Exception:
            _base_text_type[0] = _pick_base_type(DB.TextNoteType)
    if _base_text_type[0] is None:
        note_problem("no usable TextNoteType found in this document at all", Exception("none found"))
        return None
    base_id = _base_text_type[0].Id
    safe_font = re.sub(r"[^A-Za-z0-9]", "", font_name or "")
    name = "XL_%.4f_%d_%d_%02X%02X%02X_%s" % (size_ft, bold, italic, rgb_key[0], rgb_key[1], rgb_key[2], safe_font)
    result_id = base_id
    try:
        # Reuse an existing generated type on later runs, then refresh ALL
        # relevant properties. Without this, a second click can take a
        # different code path through Revit's type table and leave the note
        # using the document's base/default formatting.
        new_type = _duplicate_type(_base_text_type[0], name, DB.TextNoteType)

        def _set(bip_name, value):
            try:
                p = new_type.get_Parameter(getattr(DB.BuiltInParameter, bip_name))
                if p and not p.IsReadOnly:
                    p.Set(value)
            except Exception as ex:
                note_problem("TextNoteType {0}".format(bip_name), ex)

        _set("TEXT_SIZE", size_ft)
        _set("TEXT_STYLE_BOLD", 1 if bold else 0)
        _set("TEXT_STYLE_ITALIC", 1 if italic else 0)
        _set("LINE_COLOR", color_to_line_color_int(color) if color else 0)
        _set("TEXT_BACKGROUND", 1)        # transparent, so fills show behind text
        _set("TEXT_BOX_VISIBILITY", 0)    # no border box around the text
        if font_name:
            _set("TEXT_FONT", font_name)
        result_id = new_type.Id
    except Exception as ex:
        note_problem("creating/refreshing TextNoteType {0}".format(name), ex)
        result_id = base_id
    _text_type_cache[key] = result_id
    return result_id


# Excel border style names -> an approximate Revit line weight (1-16).
# Dash/dot patterns aren't reproduced (all draw solid) - only presence and
# relative thickness are, which covers the common "thin grid" / "thick
# outline" cases without needing custom LinePatternElements per style.
_BORDER_WEIGHT = {
    "hair": 1, "thin": 1, "dotted": 1, "dashed": 1, "dashDot": 1, "dashDotDot": 1, "slantDashDot": 1,
    "medium": 3, "mediumDashed": 3, "mediumDashDot": 3, "mediumDashDotDot": 3,
    "thick": 6, "double": 2,
}

_line_style_cache = {}
_lines_category = [None]


def get_border_line_style(style_name, color_hex):
    weight = _BORDER_WEIGHT.get(style_name, 1)
    color = hex_to_color(color_hex) or DB.Color(0, 0, 0)
    key = (color.Red, color.Green, color.Blue, weight)
    if key in _line_style_cache:
        return _line_style_cache[key]
    try:
        if _lines_category[0] is None:
            _lines_category[0] = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
        lines_cat = _lines_category[0]
        name = "XL_border_%02X%02X%02X_w%d" % (color.Red, color.Green, color.Blue, weight)
        sub = None
        for c in lines_cat.SubCategories:
            if c.Name == name:
                sub = c
                break
        if sub is None:
            sub = doc.Settings.Categories.NewSubcategory(lines_cat, name)
        try:
            sub.LineColor = color
        except Exception as ex:
            logger.debug("Could not set border line color: {0}".format(ex))
        try:
            sub.SetLineWeight(weight, DB.GraphicsStyleType.Projection)
        except Exception as ex:
            logger.debug("Could not set border line weight: {0}".format(ex))
        gs = sub.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
        result = gs.Id if gs else None
    except Exception as ex:
        logger.debug("get_border_line_style failed for {0}: {1}".format(key, ex))
        result = None
    _line_style_cache[key] = result
    return result


def draw_cell_borders(view, x0, y0, x1, y1, border):
    if not border or not any(border.values()):
        return
    edges = {
        "top": (DB.XYZ(x0, y1, 0), DB.XYZ(x1, y1, 0)),
        "bottom": (DB.XYZ(x0, y0, 0), DB.XYZ(x1, y0, 0)),
        "left": (DB.XYZ(x0, y0, 0), DB.XYZ(x0, y1, 0)),
        "right": (DB.XYZ(x1, y0, 0), DB.XYZ(x1, y1, 0)),
    }
    for side, info in border.items():
        if not info:
            continue
        style_name, color_hex = info
        p0, p1 = edges[side]
        if p0.DistanceTo(p1) < 1e-9:
            continue
        gs_id = get_border_line_style(style_name, color_hex)
        try:
            line = DB.Line.CreateBound(p0, p1)
            curve_elem = doc.Create.NewDetailCurve(view, line)
            if gs_id is not None:
                gs = doc.GetElement(gs_id)
                if gs is not None:
                    curve_elem.LineStyle = gs
        except Exception as ex:
            note_problem("border line", ex)


def rect_curve_loop(x0, y0, x1, y1, z=0.0):
    p0, p1, p2, p3 = DB.XYZ(x0, y0, z), DB.XYZ(x1, y0, z), DB.XYZ(x1, y1, z), DB.XYZ(x0, y1, z)
    loop = DB.CurveLoop()
    loop.Append(DB.Line.CreateBound(p0, p1))
    loop.Append(DB.Line.CreateBound(p1, p2))
    loop.Append(DB.Line.CreateBound(p2, p3))
    loop.Append(DB.Line.CreateBound(p3, p0))
    return loop


def _clamp_text_width(type_id, width_ft):
    """Clamp a wrapping TextNote width to Revit's valid paper-space range."""
    try:
        min_w = DB.TextNote.GetMinimumAllowedWidth(doc, type_id)
        max_w = DB.TextNote.GetMaximumAllowedWidth(doc, type_id)
        return max(min_w, min(max_w, width_ft))
    except Exception as ex:
        note_problem("TextNote width limits", ex)
        return max(width_ft, 0.05)


def create_excel_text_note(view, type_id, value, sx0, sx1, y0, y1,
                           resolved_h, vertical, wrap_text):
    """Use Revit's true unwrapped/wrapped TextNote APIs to mirror Excel."""
    horizontal_enum = {
        "left": DB.HorizontalTextAlignment.Left,
        "center": DB.HorizontalTextAlignment.Center,
        "right": DB.HorizontalTextAlignment.Right,
    }.get(resolved_h, DB.HorizontalTextAlignment.Left)
    vertical_enum = {
        "top": DB.VerticalTextAlignment.Top,
        "center": DB.VerticalTextAlignment.Middle,
        "bottom": DB.VerticalTextAlignment.Bottom,
    }.get(vertical, DB.VerticalTextAlignment.Bottom)

    opts = DB.TextNoteOptions(type_id)
    opts.HorizontalAlignment = horizontal_enum
    opts.VerticalAlignment = vertical_enum

    margin = TEXT_MARGIN_FT
    if resolved_h == "center":
        ax = (sx0 + sx1) / 2.0
    elif resolved_h == "right":
        ax = sx1 - margin
    else:
        ax = sx0 + margin

    if vertical == "center":
        ay = (y0 + y1) / 2.0
    elif vertical == "bottom":
        ay = y0 + margin
    else:
        ay = y1 - margin

    origin = DB.XYZ(ax, ay, 0)
    try:
        if not wrap_text:
            # IMPORTANT: this overload is genuinely unwrapped.
            return DB.TextNote.Create(doc, view.Id, origin, str(value), opts)
        width = max(sx1 - sx0 - 2 * margin, 0.05)
        width = _clamp_text_width(type_id, width)
        return DB.TextNote.Create(doc, view.Id, origin, width, str(value), opts)
    finally:
        try:
            opts.Dispose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Core: draw one workbook's print area into one drafting view
# ---------------------------------------------------------------------------
def import_workbook(xlsx_path, view):
    sheet = read_xlsx(xlsx_path)
    min_row, max_row = sheet["min_row"], sheet["max_row"]
    min_col, max_col = sheet["min_col"], sheet["max_col"]
    cells = sheet["cells"]
    style_for = sheet["style_for"]
    custom_numfmts = sheet["custom_numfmts"]

    hidden_cols = sheet.get("hidden_cols", set())
    hidden_rows = sheet.get("hidden_rows", set())
    default_col_width = sheet.get("default_col_width", DEFAULT_COL_WIDTH_UNITS)
    default_row_height_pt = sheet.get("default_row_height_pt", DEFAULT_ROW_HEIGHT_PT)

    col_offset_ft = {min_col - 1: 0.0}
    for c in range(min_col, max_col + 1):
        w = 0.0 if c in hidden_cols else sheet["col_widths"].get(c, default_col_width)
        col_offset_ft[c] = col_offset_ft[c - 1] + max(w, 0.0) * FEET_PER_COLWIDTH_UNIT

    row_offset_ft = {min_row - 1: 0.0}
    for r in range(min_row, max_row + 1):
        h = 0.0 if r in hidden_rows else sheet["row_heights"].get(r, default_row_height_pt)
        row_offset_ft[r] = row_offset_ft[r - 1] + max(h, 0.0) * FEET_PER_POINT

    # RTL support: everything above/below stays in LOGICAL (natural reading
    # order) coordinates - column A always at logical x=0, increasing
    # rightward in reading order, exactly like an LTR sheet. Only at the
    # point of building actual Revit geometry do we mirror to screen space
    # for an RTL sheet (column A ends up on the right, like Excel shows
    # it) via to_screen_x0x1(). This keeps overflow-scanning, cell_rect,
    # and border logic identical either way - RTL-awareness is isolated to
    # this one conversion, plus which side text/borders anchor to.
    is_rtl_sheet = sheet["is_rtl"]
    TOTAL_WIDTH_FT = col_offset_ft[max_col]

    def to_screen_x0x1(logical_x0, logical_x1):
        if is_rtl_sheet:
            return TOTAL_WIDTH_FT - logical_x1, TOTAL_WIDTH_FT - logical_x0
        return logical_x0, logical_x1

    def cell_rect(c0, r0, c1, r1):
        x0 = col_offset_ft[c0 - 1]
        x1 = col_offset_ft[c1]
        y0 = -row_offset_ft[r1]
        y1 = -row_offset_ft[r0 - 1]
        return x0, y0, x1, y1

    merge_of = {}
    covered = set()
    for (mr0, mr1, mc0, mc1) in sheet["merges"]:
        if mc1 < min_col or mc0 > max_col or mr1 < min_row or mr0 > max_row:
            continue
        merge_of[(mr0, mc0)] = (mr0, mr1, mc0, mc1)
        for rr in range(mr0, mr1 + 1):
            for cc in range(mc0, mc1 + 1):
                if (rr, cc) != (mr0, mc0):
                    covered.add((rr, cc))

    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            if (row, col) in covered:
                continue

            try:
                entry = cells.get((row, col))
                if (row, col) in merge_of:
                    r0, r1, c0, c1 = merge_of[(row, col)]
                else:
                    r0, r1, c0, c1 = row, row, col, col

                x0, y0, x1, y1 = cell_rect(c0, r0, c1, r1)
                if x1 <= x0 or y1 <= y0:
                    continue

                style_idx = entry["style"] if entry else 0
                font, fill_hex, numfmt_id, _merge_top_left_border, align = style_for(style_idx)
                fill_color = hex_to_color(fill_hex)

                is_white = (fill_color is not None and fill_color.Red == 255
                            and fill_color.Green == 255 and fill_color.Blue == 255)
                if fill_color is not None and not is_white:   # white on a white view adds nothing
                    region_type_id = get_filled_region_type(fill_color)
                    if region_type_id is not None:
                        try:
                            fx0, fx1 = to_screen_x0x1(x0, x1)
                            region = DB.FilledRegion.Create(doc, region_type_id, view.Id, [rect_curve_loop(fx0, y0, fx1, y1)])
                            inv_id = get_invisible_line_style_id()
                            if inv_id is not None:
                                try:
                                    region.SetLineStyleId(inv_id)
                                except Exception as ex:
                                    note_problem("FilledRegion.SetLineStyleId", ex)
                        except Exception as ex:
                            note_problem("FilledRegion.Create", ex)

                raw_value = entry["value"] if entry else None
                value = raw_value
                if value is not None:
                    value = format_cell_value(value, numfmt_id, custom_numfmts)
                if value is not None and str(value).strip() != "":
                    size_ft = (font["size"] or 11.0) * FEET_PER_POINT * TEXT_SIZE_FACTOR
                    font_color = hex_to_color(font["color"])
                    type_id = get_text_type(size_ft, bool(font["bold"]), bool(font["italic"]), font_color, font.get("name"))

                    try:
                        # Resolve which way this cell reads: per-cell
                        # readingOrder overrides the sheet default; 0 follows it.
                        reading_order = align.get("readingOrder", 0)
                        cell_rtl = is_rtl_sheet
                        if reading_order == 1:
                            cell_rtl = False
                        elif reading_order == 2:
                            cell_rtl = True

                        horiz = align.get("horizontal")
                        if horiz in ("left", "right", "center"):
                            resolved_h = horiz
                        elif horiz in ("centerContinuous", "distributed", "justify"):
                            resolved_h = "center"
                        else:
                            is_text_value = isinstance(raw_value, str)
                            resolved_h = ("right" if cell_rtl else "left") if is_text_value else ("left" if cell_rtl else "right")

                        logical_left, logical_right = x0, x1
                        is_single_cell = (c0 == c1 and r0 == r1)
                        has_overflow_room = False
                        if is_single_cell and not align["wrapText"] and resolved_h in ("left", "right"):
                            scan_toward_higher_index = (resolved_h == "left") != is_rtl_sheet
                            if scan_toward_higher_index:
                                oc = col + 1
                                while oc <= max_col and (row, oc) not in covered and (row, oc) not in merge_of:
                                    oentry = cells.get((row, oc))
                                    if oentry and oentry.get("value") not in (None, ""):
                                        break
                                    if oc not in hidden_cols:
                                        has_overflow_room = True
                                    logical_right = col_offset_ft[oc]
                                    oc += 1
                            else:
                                oc = col - 1
                                while oc >= min_col and (row, oc) not in covered and (row, oc) not in merge_of:
                                    oentry = cells.get((row, oc))
                                    if oentry and oentry.get("value") not in (None, ""):
                                        break
                                    if oc not in hidden_cols:
                                        has_overflow_room = True
                                    logical_left = col_offset_ft[oc - 1]
                                    oc -= 1

                        vertical = align.get("vertical")
                        if vertical in ("center", "middle"):
                            resolved_v = "center"
                        elif vertical == "top":
                            resolved_v = "top"
                        else:
                            resolved_v = "bottom"

                        sx0, sx1 = to_screen_x0x1(logical_left, logical_right)
                        wrap_note = bool(align["wrapText"] or (is_single_cell and resolved_h in ("left", "right") and not has_overflow_room))

                        create_excel_text_note(view, type_id, value, sx0, sx1, y0, y1,
                                               resolved_h, resolved_v, wrap_note)
                    except Exception as ex:
                        note_problem("alignment/text creation", ex)
                        try:
                            fallback_origin = DB.XYZ(x0 + TEXT_MARGIN_FT, y1 - TEXT_MARGIN_FT, 0)
                            opts = DB.TextNoteOptions(type_id)
                            opts.HorizontalAlignment = DB.HorizontalTextAlignment.Left
                            opts.VerticalAlignment = DB.VerticalTextAlignment.Top
                            DB.TextNote.Create(doc, view.Id, fallback_origin, str(value), opts)
                            try:
                                opts.Dispose()
                            except Exception:
                                pass
                        except Exception as fallback_ex:
                            note_problem("TextNote fallback", fallback_ex)
            except Exception as ex:
                note_problem("cell rendering", ex)

    # --- borders: a separate pass over every ORIGINAL cell, since Excel stores
    # border formatting per cell even inside a merged range. Excel only SHOWS
    # the outer edge of a merged range, so every side that lies inside a merge
    # (between two cells of the same merged range) is dropped here. ---
    merge_range_of = {}
    for (mr0, mr1, mc0, mc1) in sheet["merges"]:
        for rr in range(mr0, mr1 + 1):
            for cc in range(mc0, mc1 + 1):
                merge_range_of[(rr, cc)] = (mr0, mr1, mc0, mc1)

    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            try:
                entry = cells.get((row, col))
                style_idx = entry["style"] if entry else 0
                _, _, _, border, _align = style_for(style_idx)
                if not border or not any(border.values()):
                    continue
                mr = merge_range_of.get((row, col))
                if mr is not None:
                    mr0, mr1, mc0, mc1 = mr
                    border = dict(border)
                    if col > mc0:
                        border["left"] = None
                    if col < mc1:
                        border["right"] = None
                    if row > mr0:
                        border["top"] = None
                    if row < mr1:
                        border["bottom"] = None
                    if not any(border.values()):
                        continue
                x0 = col_offset_ft[col - 1]
                x1 = col_offset_ft[col]
                y0 = -row_offset_ft[row]
                y1 = -row_offset_ft[row - 1]
                if x1 <= x0 or y1 <= y0:
                    continue
                if col in hidden_cols or row in hidden_rows:
                    continue
                sx0, sx1 = to_screen_x0x1(x0, x1)
                if is_rtl_sheet:
                    border = dict(border)
                    border["left"], border["right"] = border.get("right"), border.get("left")
                draw_cell_borders(view, sx0, y0, sx1, y1, border)
            except Exception as ex:
                logger.debug("Border at col {0} row {1} skipped: {2}".format(col, row, ex))

    seen_images = set()
    image_type_cache = {}
    temp_image_paths = []
    try:
        for i, img in enumerate(sheet["images"]):
            try:
                frm = img["from"]
                to = img["to"]
                ext = img["ext"]

                dedup_key = (frm["col"], frm["colOff"], frm["row"], frm["rowOff"],
                             to["col"] if to else None, to["colOff"] if to else None,
                             to["row"] if to else None, to["rowOff"] if to else None,
                             ext, img["part"])
                if dedup_key in seen_images:
                    continue
                seen_images.add(dedup_key)

                a_col, a_row = frm["col"] + 1, frm["row"] + 1
                if a_col < min_col or a_col > max_col or a_row < min_row or a_row > max_row:
                    continue
                if a_col in hidden_cols or a_row in hidden_rows:
                    continue

                x0 = col_offset_ft.get(a_col - 1, 0.0) + frm["colOff"] / EMU_PER_FOOT
                y0 = -(row_offset_ft.get(a_row - 1, 0.0) + frm["rowOff"] / EMU_PER_FOOT)

                if to is not None:
                    b_col = to["col"] + 1
                    b_row = to["row"] + 1
                    x1 = col_offset_ft.get(b_col - 1, x0) + to["colOff"] / EMU_PER_FOOT
                    bottom_y = row_offset_ft.get(b_row - 1, row_offset_ft.get(a_row - 1, 0.0)) + to["rowOff"] / EMU_PER_FOOT
                    width_ft = max(x1 - x0, 0.05)
                    height_ft = max(y0 - (-bottom_y), 0.05)
                elif ext is not None:
                    width_ft = max(ext[0] / EMU_PER_FOOT, 0.05)
                    height_ft = max(ext[1] / EMU_PER_FOOT, 0.05)
                else:
                    width_ft = 1.0
                    height_ft = 1.0

                part = img["part"]
                image_type = image_type_cache.get(part)
                if image_type is None:
                    data = extract_image_bytes(xlsx_path, part)
                    if not data:
                        continue
                    fmt = part.rsplit(".", 1)[-1].lower() if "." in part else "png"
                    tmp_path = os.path.join(tempfile.gettempdir(),
                                            "xl_img_{0}_{1}_{2}.{3}".format(view.Id.IntegerValue, i, abs(hash(part)), fmt))
                    DotNetFile.WriteAllBytes(tmp_path, data)
                    temp_image_paths.append(tmp_path)
                    options = DB.ImageTypeOptions(tmp_path, False, DB.ImageTypeSource.Import)
                    try:
                        image_type = DB.ImageType.Create(doc, options)
                    finally:
                        try:
                            options.Dispose()
                        except Exception:
                            pass
                    image_type_cache[part] = image_type

                screen_x0, _ = to_screen_x0x1(x0, x0 + width_ft)
                desired_top_left = DB.XYZ(screen_x0, y0, 0)
                placement = DB.ImagePlacementOptions(desired_top_left, DB.BoxPlacement.TopLeft)
                try:
                    instance = DB.ImageInstance.Create(doc, view, image_type.Id, placement)
                finally:
                    try:
                        placement.Dispose()
                    except Exception:
                        pass

                try:
                    try:
                        instance.LockProportions = False
                    except Exception:
                        pass
                    instance.Width = width_ft
                    instance.Height = height_ft
                    doc.Regenerate()
                    actual_top_left = instance.GetLocation(DB.BoxPlacement.TopLeft)
                    delta = desired_top_left - actual_top_left
                    if delta.GetLength() > 1e-9:
                        DB.ElementTransformUtils.MoveElement(doc, instance.Id, delta)
                except Exception as ex:
                    note_problem("image resize/reposition", ex)
            except Exception as ex:
                note_problem("image", ex)
    finally:
        for tmp_path in temp_image_paths:
            try:
                os.remove(tmp_path)
            except Exception:
                pass



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _reset_run_state():
    """These caches only make sense within a single run (reused across the
    files picked in one click). pyRevit can keep the IronPython engine
    alive between separate button clicks, so without this, a second run
    could reuse ElementIds from the previous run/document state (e.g. a
    type you've since purged) instead of looking them up fresh."""
    diagnostics.clear()
    fill_color_failures[0] = 0
    _solid_pattern_id[0] = None
    _region_type_cache.clear()
    _base_region_type[0] = None
    _invisible_line_style_id[0] = False
    _text_type_cache.clear()
    _base_text_type[0] = None
    _line_style_cache.clear()
    _lines_category[0] = None


def main():
    _reset_run_state()
    ui_result = show_panel()
    if not ui_result["ok"]:
        return

    mode = ui_result["mode"]
    xlsx_paths = ui_result["files"]
    view_name_input = ui_result["view_name"]
    target_view = ui_result["target_view"]

    results = []
    errors = []

    with revit.Transaction("Import Excel print area(s)"):
        if mode == "update":
            force_true_scale(target_view)
            clear_previous_import(target_view)
            try:
                import_workbook(xlsx_paths[0], target_view)
                results.append((xlsx_paths[0], target_view.Name))
            except Exception as ex:
                errors.append((xlsx_paths[0], "{0}\n{1}".format(ex, traceback.format_exc())))
                logger.error("Failed on {0}: {1}".format(xlsx_paths[0], ex))
        else:
            for path in xlsx_paths:
                base = os.path.splitext(os.path.basename(path))[0]
                if view_name_input:
                    name = view_name_input if len(xlsx_paths) == 1 else "{0} - {1}".format(view_name_input, base)
                else:
                    name = base

                view = create_drafting_view(name)
                force_true_scale(view)
                try:
                    import_workbook(path, view)
                    results.append((path, view.Name))
                except Exception as ex:
                    try:
                        doc.Delete(view.Id)
                    except Exception as delete_ex:
                        logger.error("Could not remove failed drafting view {0}: {1}".format(view.Name, delete_ex))
                    errors.append((path, "{0}\n{1}".format(ex, traceback.format_exc())))
                    logger.error("Failed on {0}: {1}".format(path, ex))

    summary_lines = ["  {0} -> {1}".format(os.path.basename(p), v) for p, v in results]
    if diagnostics:
        summary_lines.append("")
        summary_lines.append("Some Revit API calls failed (drawn with defaults instead):")
        for msg, cnt in sorted(diagnostics.items(), key=lambda kv: -kv[1])[:8]:
            summary_lines.append("  [{0}x] {1}".format(cnt, msg[:180]))
        summary_lines.append("(copy this text back to Claude if something looks wrong)")
    if errors:
        summary_lines.append("")
        summary_lines.append("Failed:")
        summary_lines.extend("  {0} : {1}".format(os.path.basename(p), msg.splitlines()[0]) for p, msg in errors)
        for p, msg in errors:
            logger.error("Full traceback for {0}:\n{1}".format(p, msg))

    alert("Done.\n\n{0}".format("\n".join(summary_lines)))


try:
    main()
except Exception:
    _tb_text = traceback.format_exc()
    _log_path = _save_crash_log("=== Excel to Drafting crash log ===\n" + _tb_text)
    _show_crash(_tb_text, _log_path)
