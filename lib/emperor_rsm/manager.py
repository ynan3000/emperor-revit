# -*- coding: ascii -*-
# Emperor BIM Toolkit - Room & Space Manager
# Revit 2024 / 2025 + pyRevit, IronPython 2.7
# Author: Yahya Morcy
#
# One modeless window with ROOMS and SPACES tabs. The window only reads the
# model directly; every change goes through one ExternalEvent so Revit runs it
# in a valid API context. The pushbutton runs with a persistent engine, which
# pyRevit needs for modeless windows that call back into Revit.

import re
import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System')
clr.AddReference('System.Data')

import System
from System import AppDomain
from System.Data import DataTable, DataColumn
from System.Collections.Generic import List
from System.Windows import (Window, Thickness, HorizontalAlignment, VerticalAlignment, GridLength,
                            GridUnitType, WindowStartupLocation, ResizeMode, TextWrapping,
                            MessageBox, MessageBoxButton, MessageBoxImage, MessageBoxResult, CornerRadius)
from System.Windows.Controls import Grid as WpfGrid
from System.Windows.Controls import (DockPanel, StackPanel, Border, TextBox, TabControl, TabItem,
                                     DataGrid, DataGridTextColumn, DataGridLength, DataGridLengthUnitType,
                                     ScrollViewer, ScrollBarVisibility, ColumnDefinition, RowDefinition,
                                     DataGridSelectionMode, DataGridSelectionUnit, DataGridHeadersVisibility,
                                     DataGridGridLinesVisibility, Dock, WrapPanel, Orientation,
                                     DataGridTemplateColumn)
from System.Windows.Markup import XamlReader
from System.Windows.Data import Binding
from System.Windows.Input import Cursors
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Media import FontFamily

from Autodesk.Revit import DB
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent, ExternalEventRequest

from emperor_rsm import theme as T
from emperor_rsm.theme import u, log, log_exception, LOG_PATH

TOOL_TITLE = 'Room & Space Manager'
VERSION = '2.2.0'
REGISTRY_KEY = 'EmperorRoomSpaceManager_'
BIP = DB.BuiltInParameter
CATEGORY = {'Room': DB.BuiltInCategory.OST_Rooms, 'Space': DB.BuiltInCategory.OST_MEPSpaces}
SCOPES = ['All host-model rows', 'Filtered rows (what the table shows)', 'Selected rows only', 'Ticked rows (check boxes)']
COLUMNS = ['Key', 'Name', 'Number', 'Level', 'Phase', 'Area', 'Height', 'Source', 'Linked Model', 'Element Id', 'Status']
REVIT_DEFAULT_SPACE_NAME = u'space'


# =============================================================== model helpers
from pyrevit.compat import get_elementid_value_func as _get_eid_value_func
_EID_VALUE = _get_eid_value_func()   # ElementId.Value (2024+) or .IntegerValue (older)


def id_value(element_id):
    try:
        return int(_EID_VALUE(element_id))
    except Exception:
        return -1


def is_valid(element):
    if element is None:
        return False
    try:
        return bool(element.IsValidObject)
    except Exception:
        return True


def element_name(element):
    # Element.Name is hidden on Room/Space in IronPython; read it through the base property.
    try:
        return u(DB.Element.Name.GetValue(element))
    except Exception:
        try:
            return u(element.Name)
        except Exception:
            return u''


def param_text(element, bip):
    try:
        p = element.get_Parameter(bip)
        if p is None:
            return u''
        value = p.AsString()
        if value is None:
            value = p.AsValueString()
        return u(value)
    except Exception:
        return u''


# Rooms AND spaces store Name / Number / Phase in the ROOM_* parameters.
# (SPACE_NAME / SPACE_NUMBER / SPACE_PHASE do not exist in the Revit API.)
def get_name(element):
    return param_text(element, BIP.ROOM_NAME)


def get_number(element):
    return param_text(element, BIP.ROOM_NUMBER)


def set_field(element, field_name, value):
    bip = BIP.ROOM_NAME if field_name == 'Name' else BIP.ROOM_NUMBER
    p = element.get_Parameter(bip)
    if p is None or p.IsReadOnly:
        return False
    return bool(p.Set(u(value)))


def level_name(doc, element):
    try:
        level = doc.GetElement(element.LevelId)
        if level is not None:
            return element_name(level)
    except Exception:
        pass
    return u'(No level)'


def phase_name(doc, element):
    try:
        p = element.get_Parameter(BIP.ROOM_PHASE)
        if p is not None:
            phase = doc.GetElement(p.AsElementId())
            if phase is not None:
                return element_name(phase)
    except Exception:
        pass
    try:
        phase = doc.GetElement(element.CreatedPhaseId)
        if phase is not None:
            return element_name(phase)
    except Exception:
        pass
    return u''


def area_text(element):
    try:
        p = element.get_Parameter(BIP.ROOM_AREA)
        if p is not None:
            return u(p.AsValueString())
    except Exception:
        pass
    return u''


def height_text(element):
    """Unbounded height in meters (2 decimals)."""
    try:
        p = element.get_Parameter(BIP.ROOM_HEIGHT)
        if p is not None and p.HasValue:
            return u'%.2f' % (p.AsDouble() * 0.3048)
    except Exception:
        pass
    return u''


def placement_state(element):
    try:
        if element.Location is None:
            return u'Not placed'
        if element.Area > 1e-6:
            return u'Placed'
        return u'Not enclosed'
    except Exception:
        return u''


def spatial_elements(doc, kind):
    # OfClass(Room) / OfClass(Space) throws in Revit ("not in Revit's native object
    # model"), so collect by category and keep only real spatial elements.
    result = []
    try:
        collector = DB.FilteredElementCollector(doc).OfCategory(CATEGORY[kind]).WhereElementIsNotElementType()
        for element in collector:
            if isinstance(element, DB.SpatialElement):
                result.append(element)
    except Exception:
        log_exception('Could not collect {0}s from {1}'.format(kind, element_name(doc)))
    return result


def location_point(element):
    try:
        loc = element.Location
        if isinstance(loc, DB.LocationPoint):
            return loc.Point
    except Exception:
        pass
    return None


def sorted_levels(doc):
    try:
        levels = list(DB.FilteredElementCollector(doc).OfClass(DB.Level).WhereElementIsNotElementType())
    except Exception:
        levels = []
    levels.sort(key=lambda lev: (lev.Elevation, element_name(lev).lower()))
    return levels


def like_escape(value):
    """Escape text for a DataView RowFilter LIKE clause: quotes doubled, wildcards and brackets bracketed."""
    out = []
    for ch in u(value).replace(u"'", u"''"):
        if ch in u'[]*%':
            out.append(u'[' + ch + u']')
        else:
            out.append(ch)
    return u''.join(out)


def equals_escape(value):
    return u(value).replace(u"'", u"''")


# =============================================================== transactions
class WarningSwallower(DB.IFailuresPreprocessor):
    """Removes Revit *warnings* (never errors) so a batch does not stop on dialogs; they are counted for the report."""
    def __init__(self):
        self.count = 0

    def PreprocessFailures(self, accessor):
        # Warnings are removed and counted. Errors are resolved with Revit's default
        # resolution when one exists; otherwise the transaction is rolled back quietly
        # (run_transaction then reports it) - never a modal dialog in the middle of a batch.
        try:
            resolved_error = False
            for message in accessor.GetFailureMessages():
                severity = message.GetSeverity()
                if severity == DB.FailureSeverity.Warning:
                    accessor.DeleteWarning(message)
                    self.count += 1
                elif message.HasResolutions():
                    accessor.ResolveFailure(message)
                    resolved_error = True
                    self.count += 1
                else:
                    log('Revit error, rolling back: ' + u(message.GetDescriptionText()))
                    return DB.FailureProcessingResult.ProceedWithRollBack
            if resolved_error:
                return DB.FailureProcessingResult.ProceedWithCommit
        except Exception:
            log_exception('Failure preprocessor failed.')
        return DB.FailureProcessingResult.Continue


def run_transaction(doc, name, work):
    """Runs work() in a transaction. Returns (result, suppressed_warnings). Raises if Revit rolls back."""
    t = DB.Transaction(doc, name)
    swallower = WarningSwallower()
    try:
        options = t.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(swallower)
        options.SetClearAfterRollback(True)
        t.SetFailureHandlingOptions(options)
    except Exception:
        pass
    t.Start()
    try:
        result = work()
        status = t.Commit()
        if status != DB.TransactionStatus.Committed:
            raise Exception('Revit did not commit "{0}" (status: {1}).'.format(name, status))
        return result, swallower.count
    except Exception:
        try:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
        except Exception:
            pass
        raise


# =============================================================== room matching
class RoomMatcher(object):
    """Finds the host or linked room that contains a point (host coordinates).
    A bounding-box pre-check keeps it fast on models with hundreds of linked rooms."""

    TOL = 0.05

    def __init__(self, doc):
        self.records = []
        self._add_rooms(doc, None, u'')
        try:
            links = list(DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance))
        except Exception:
            links = []
        for link in links:
            try:
                link_doc = link.GetLinkDocument()
                if link_doc is None:
                    continue
                self._add_rooms(link_doc, link.GetTotalTransform().Inverse, element_name(link))
            except Exception:
                log_exception('Room matcher could not read a link.')

    def _add_rooms(self, room_doc, inverse, source):
        for room in spatial_elements(room_doc, 'Room'):
            try:
                if room.Area <= 1e-6:
                    continue
                box = room.get_BoundingBox(None)
                if box is None:
                    continue
                self.records.append({
                    'room': room, 'inverse': inverse, 'min': box.Min, 'max': box.Max,
                    'name': get_name(room), 'number': get_number(room),
                    'phase': phase_name(room_doc, room).lower(), 'source': source})
            except Exception:
                pass

    def match(self, point, phase):
        if point is None:
            return None
        phase = u(phase).lower()
        fallback = None
        for dz in (0.0, 1.0):
            test = DB.XYZ(point.X, point.Y, point.Z + dz)
            for rec in self.records:
                p = rec['inverse'].OfPoint(test) if rec['inverse'] is not None else test
                lo = rec['min']
                hi = rec['max']
                tol = self.TOL
                if (p.X < lo.X - tol or p.X > hi.X + tol or p.Y < lo.Y - tol or p.Y > hi.Y + tol
                        or p.Z < lo.Z - tol or p.Z > hi.Z + tol):
                    continue
                try:
                    if not rec['room'].IsPointInRoom(p):
                        continue
                except Exception:
                    continue
                if rec['phase'] == phase:
                    return rec
                if fallback is None:
                    fallback = rec
            if fallback is not None:
                return fallback
        return fallback


# =============================================================== external event
class ActionHandler(IExternalEventHandler):
    def __init__(self, manager):
        self.manager = manager
        self.pending = None

    def Execute(self, uiapp):
        action = self.pending
        self.pending = None
        if action is None:
            return
        try:
            self.manager.execute_action(action, uiapp)
        except Exception:
            log_exception('External event failed: ' + u(action))
            try:
                self.manager.finish_action('Action failed. Details were written to: ' + LOG_PATH, True)
            except Exception:
                pass

    def GetName(self):
        return 'Emperor Room & Space Manager'


# =============================================================== window
class RoomSpaceManager(object):

    def __init__(self, uiapp, uidoc):
        self.uiapp = uiapp
        self.uidoc = uidoc
        self.doc = uidoc.Document
        self.handler = None
        self.external_event = None
        self.busy = False
        self.loading = False
        self.meta = {}
        self.rows = {}
        self.tables = {'Room': self._new_table('Rooms'), 'Space': self._new_table('Spaces')}
        self.ui = {'Room': {}, 'Space': {}}
        self.action_buttons = []
        self.phase_items = []
        self.level_items = []
        self.non_bounding_links = []
        self.auto_start_number = u'1'
        self.last_report = 'Room & Space Manager ready.'

        self.win = Window()
        self.win.Title = 'Emperor - ' + TOOL_TITLE
        self.win.Width = 1200
        self.win.Height = 760
        self.win.MinWidth = 960
        self.win.MinHeight = 560
        self.win.ResizeMode = ResizeMode.CanResize
        self.win.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.win.Background = T.brush(T.WINDOW_BG)
        self.win.FontFamily = FontFamily('Segoe UI')
        try:
            th = T.theme()
            if th is not None:
                self.win.Resources.MergedDictionaries.Add(th)
            T.enable_glow(self.win)
        except Exception:
            log_exception('Theme not attached.')
        try:
            import emperor_ui
            if not emperor_ui.apply_theme(self.win):
                log('Emperor button theme could not be loaded - buttons fall back to the Room & Space theme.')
        except Exception:
            log_exception('Emperor button theme not attached.')
        self._set_owner()
        try:
            import emperor_ui
            emperor_ui.keep_owner_in_front(self.win, self.uiapp.MainWindowHandle)
        except Exception:
            log_exception('Focus hand-back not attached.')

        self._build_ui()
        self._load_all_data()
        self._populate_creation_lists()
        self._update_counts()

    # ------------------------------------------------------------ setup
    def _set_owner(self):
        try:
            WindowInteropHelper(self.win).Owner = self.uiapp.MainWindowHandle
        except Exception:
            try:
                from System.Diagnostics import Process
                WindowInteropHelper(self.win).Owner = Process.GetCurrentProcess().MainWindowHandle
            except Exception:
                pass

    def _new_table(self, name):
        table = DataTable(name)
        pick = DataColumn('Pick', clr.GetClrType(System.Boolean))
        pick.DefaultValue = False
        table.Columns.Add(pick)
        for column in COLUMNS:
            table.Columns.Add(DataColumn(column, clr.GetClrType(System.String)))
        return table

    def _safe(self, callback):
        # An exception escaping a WPF handler can take Revit down: catch, log, show.
        def handler(sender, args):
            try:
                callback()
            except Exception as ex:
                log_exception('UI handler failed.')
                self._message('Unexpected error:\n\n{0}\n\nDetails were written to:\n{1}'.format(u(ex), LOG_PATH), error=True)
        return handler

    def _action_button(self, label, icon, action, primary=False, width=None, tooltip=None):
        b = T.button(label, icon, primary, width, tooltip)
        b.Click += self._safe(lambda: self.request_action(action))
        self.action_buttons.append(b)
        return b

    # ------------------------------------------------------------ layout
    def _build_ui(self):
        dock = DockPanel()
        dock.LastChildFill = True

        header = Border()
        header.Background = T.header_brush()
        header.BorderBrush = T.brush('#E2B3B8')
        header.BorderThickness = Thickness(0, 0, 0, 2)
        header.Padding = Thickness(14, 8, 14, 8)
        head_grid = WpfGrid()
        self._add_col(head_grid, GridLength(1, GridUnitType.Star))
        self._add_col(head_grid, GridLength.Auto)
        titles = T.vstack(T.text(TOOL_TITLE.upper(), 17, T.WHITE, True),
                          T.text('Emperor BIM Toolkit  |  Host and linked rooms / spaces  |  Bulk naming  |  Spaces on every level',
                                 11, '#F7DDE0', False, True))
        head_grid.Children.Add(titles)
        version = T.text('v' + VERSION, 11, '#F7DDE0')
        version.VerticalAlignment = VerticalAlignment.Bottom
        WpfGrid.SetColumn(version, 1)
        head_grid.Children.Add(version)
        header.Child = head_grid
        DockPanel.SetDock(header, Dock.Top)
        dock.Children.Add(header)

        toolbar = WrapPanel()
        toolbar.Orientation = Orientation.Horizontal
        toolbar.Background = T.brush(T.WHITE)
        bar_border = Border()
        bar_border.Background = T.brush(T.WHITE)
        bar_border.BorderBrush = T.brush(T.BORDER)
        bar_border.BorderThickness = Thickness(0, 0, 0, 1)
        bar_border.Padding = Thickness(6, 2, 6, 2)
        toolbar.Children.Add(self._action_button('Refresh', 'refresh', 'refresh', tooltip='Re-read rooms and spaces from the model and its links.'))
        toolbar.Children.Add(self._action_button('Select in Revit', 'select', 'select', tooltip='Select the highlighted rows in Revit (double-click a row does the same).'))
        toolbar.Children.Add(self._action_button('Clear Selection', 'clear', 'unselect', tooltip='Clear the Revit selection.'))
        report_btn = T.button('Results / Log', 'report', False, None, 'Show the last result report.')
        report_btn.Click += self._safe(lambda: self._show_report(self.last_report))
        toolbar.Children.Add(report_btn)
        bar_border.Child = toolbar
        DockPanel.SetDock(bar_border, Dock.Top)
        dock.Children.Add(bar_border)

        status_border = Border()
        status_border.Background = T.brush(T.STATUS_BG)
        status_border.BorderBrush = T.brush(T.BORDER)
        status_border.BorderThickness = Thickness(0, 1, 0, 0)
        status_border.Padding = Thickness(10, 4, 10, 4)
        status_grid = WpfGrid()
        self._add_col(status_grid, GridLength(1, GridUnitType.Star))
        self._add_col(status_grid, GridLength.Auto)
        self.status_text = T.text('Loading model data...', 11, T.GRAY)
        status_grid.Children.Add(self.status_text)
        self.count_text = T.text('', 11, T.GRAY)
        WpfGrid.SetColumn(self.count_text, 1)
        status_grid.Children.Add(self.count_text)
        status_border.Child = status_grid
        DockPanel.SetDock(status_border, Dock.Bottom)
        dock.Children.Add(status_border)

        self.tabs = TabControl()
        self.tabs.FontFamily = FontFamily('Segoe UI')
        self.tabs.FontSize = 12
        self.tabs.Margin = Thickness(6, 4, 6, 6)
        self.tabs.BorderBrush = T.brush(T.BORDER)
        self.tabs.BorderThickness = Thickness(0, 1, 0, 0)
        self.tabs.Background = T.brush(T.WINDOW_BG)
        self.tabs.Items.Add(self._build_tab('Room'))
        self.tabs.Items.Add(self._build_tab('Space'))
        self.tabs.SelectionChanged += self._on_tab_changed
        dock.Children.Add(self.tabs)

        self.win.Content = dock

    def _add_col(self, grid, width):
        c = ColumnDefinition()
        c.Width = width
        grid.ColumnDefinitions.Add(c)

    def _add_row(self, grid, height):
        r = RowDefinition()
        r.Height = height
        grid.RowDefinitions.Add(r)

    def _build_tab(self, kind):
        ui = self.ui[kind]
        tab = TabItem()
        tab.Header = 'ROOMS' if kind == 'Room' else 'SPACES'

        page = WpfGrid()
        page.Margin = Thickness(0, 6, 0, 0)
        self._add_col(page, GridLength(1, GridUnitType.Star))
        self._add_col(page, GridLength(T.TOOL_PANEL_WIDTH))

        # ---- left: filters + table
        card = Border()
        card.Background = T.brush(T.WHITE)
        card.BorderBrush = T.brush(T.BORDER)
        card.BorderThickness = Thickness(1)
        card.CornerRadius = CornerRadius(6)
        card.Padding = Thickness(6)
        card.Margin = Thickness(0, 0, 6, 0)
        left = WpfGrid()
        self._add_row(left, GridLength.Auto)
        self._add_row(left, GridLength(1, GridUnitType.Star))
        self._add_row(left, GridLength.Auto)

        filters = WrapPanel()
        filters.Orientation = Orientation.Horizontal
        filters.Margin = Thickness(0, 0, 0, 6)
        search_label = T.image('search', 18)
        search_label.VerticalAlignment = VerticalAlignment.Center
        search_label.Margin = Thickness(4, 0, 2, 0)
        filters.Children.Add(search_label)
        ui['search'] = T.textbox('', 210)
        ui['search'].ToolTip = 'Search name, number, level, phase or linked model'
        ui['search'].TextChanged += self._safe(lambda: self._on_filter_changed(kind))
        filters.Children.Add(ui['search'])
        ui['level'] = T.combo(['All Levels'], 150)
        ui['level'].SelectionChanged += self._safe(lambda: self._on_filter_changed(kind))
        filters.Children.Add(ui['level'])
        ui['source'] = T.combo(['All Sources', 'Host', 'Link'], 110)
        ui['source'].SelectionChanged += self._safe(lambda: self._on_filter_changed(kind))
        filters.Children.Add(ui['source'])
        ui['status_filter'] = T.combo(['Any Status', 'Placed', 'Not placed', 'Not enclosed'], 120)
        ui['status_filter'].SelectionChanged += self._safe(lambda: self._on_filter_changed(kind))
        filters.Children.Add(ui['status_filter'])
        tick_all = T.button(u'Tick shown', None, False, None, 'Tick every row the table shows (host rows).')
        tick_all.Click += self._safe(lambda: self._tick(kind, True))
        untick = T.button(u'Untick all', None, False, None, 'Clear every tick.')
        untick.Click += self._safe(lambda: self._tick(kind, False))
        filters.Children.Add(tick_all)
        filters.Children.Add(untick)
        WpfGrid.SetRow(filters, 0)
        left.Children.Add(filters)

        ui['grid'] = self._make_data_grid(self.tables[kind])
        ui['grid'].SelectionChanged += self._safe(self._update_counts)
        ui['grid'].SelectionChanged += self._safe(lambda: self._on_select(kind))
        grid_ref = ui['grid']
        ui['grid'].MouseDoubleClick += self._safe(lambda: self.request_action('select') if grid_ref.SelectedItems.Count else None)
        WpfGrid.SetRow(ui['grid'], 1)
        left.Children.Add(ui['grid'])

        ui['counter'] = T.text('', 11, T.GRAY)
        ui['counter'].Margin = Thickness(4, 6, 4, 0)
        WpfGrid.SetRow(ui['counter'], 2)
        left.Children.Add(ui['counter'])
        card.Child = left
        page.Children.Add(card)

        # ---- right: tools
        scroller = ScrollViewer()
        scroller.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        scroller.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled
        scroller.Content = self._build_room_tools() if kind == 'Room' else self._build_space_tools()
        WpfGrid.SetColumn(scroller, 1)
        page.Children.Add(scroller)

        tab.Content = page
        return tab

    def _edit_section(self, kind):
        """Rename ONE room / space, or set the height of the selected ones (host model only)."""
        ui = self.ui[kind]
        what = 'room' if kind == 'Room' else 'space'
        body = T.vstack()
        body.Children.Add(T.hint('Rename: one row. Height: the ticked rows, or the selected rows when none is ticked.'))
        body.Children.Add(T.field_label('Name'))
        ui['edit_name'] = T.textbox('', T.FIELD_WIDTH)
        body.Children.Add(ui['edit_name'])
        body.Children.Add(T.field_label('Number'))
        ui['edit_number'] = T.textbox('', 150)
        rename = self._action_button('Rename', 'replace', 'rename|' + kind, True, T.FIELD_WIDTH - 158,
                                     'Write the name and number above to the ONE selected ' + what + '.')
        body.Children.Add(T.hstack(ui['edit_number'], rename))
        body.Children.Add(T.field_label('Height (m), measured from the base of the ' + what))
        ui['edit_height'] = T.textbox('', 150)
        height = self._action_button('Set Height', 'level', 'height|' + kind, False, T.FIELD_WIDTH - 158,
                                     'Upper limit = its own level, limit offset = base offset + this height, '
                                     'for every selected ' + what + '.')
        body.Children.Add(T.hstack(ui['edit_height'], height))
        return T.section('EDIT SELECTED', body)

    def _match_section(self):
        """Make spaces like the room they sit in (host or linked room)."""
        body = T.vstack()
        body.Children.Add(T.hint('Each space takes the values of the room it sits in (host or linked room, same phase).'))
        self.match_height = T.checkbox('Height (upper limit + offset)', True)
        self.match_names = T.checkbox('Name and number', False)
        body.Children.Add(T.hstack(self.match_height, self.match_names))
        grid = WpfGrid()
        self._add_col(grid, GridLength(1, GridUnitType.Star))
        self._add_col(grid, GridLength(1, GridUnitType.Star))
        all_btn = self._action_button('All Spaces', 'copy', 'match_all', True, None,
                                      'Every host space takes the values of its room.')
        one_btn = self._action_button('Selected Space', 'select', 'match_selected', False, None,
                                      'Only the ticked space(s) - or the selected one when none is ticked.')
        grid.Children.Add(all_btn)
        WpfGrid.SetColumn(one_btn, 1)
        grid.Children.Add(one_btn)
        body.Children.Add(grid)
        return T.section('MATCH SPACES TO ROOMS', body)

    def _match_spaces(self, only_selected):
        if not (self.match_height.IsChecked or self.match_names.IsChecked):
            self._message('Tick Height and / or Name and number.')
            self.finish_action('Nothing to match.', True)
            return
        if only_selected:
            metas, linked = self._selected_host('Space')
            if not metas:
                self._message('Tick (or select) the space(s) first.')
                self.finish_action('Match: no space chosen.', True)
                return
        else:
            metas = [m for m in self.meta.values() if m['kind'] == 'Space' and m['host']]
        matcher = RoomMatcher(self.doc)
        plan, no_room = [], 0
        for m in metas:
            sp = self.doc.GetElement(m['element_id'])
            if not is_valid(sp):
                continue
            rec = matcher.match(location_point(sp), phase_name(self.doc, sp))
            if rec is None:
                no_room += 1
                continue
            plan.append((m, sp, rec))
        if not plan:
            self._message('No space sits inside a room (host or linked).')
            self.finish_action('Match: no rooms found.', True)
            return
        do_h, do_n = bool(self.match_height.IsChecked), bool(self.match_names.IsChecked)

        def work():
            done, failed = [], []
            for m, sp, rec in plan:
                try:
                    room = rec['room']
                    if do_h:
                        rh = room.get_Parameter(BIP.ROOM_HEIGHT)
                        if rh is not None and rh.HasValue:
                            base = sp.get_Parameter(BIP.ROOM_LOWER_OFFSET)
                            base_ft = base.AsDouble() if (base is not None and base.HasValue) else 0.0
                            sp.get_Parameter(BIP.ROOM_UPPER_LEVEL).Set(sp.LevelId)
                            sp.get_Parameter(BIP.ROOM_UPPER_OFFSET).Set(base_ft + rh.AsDouble())
                    if do_n:
                        set_field(sp, 'Name', rec['name'])
                        if rec['number']:
                            set_field(sp, 'Number', rec['number'])
                    done.append(m['key'])
                except Exception:
                    failed.append(m['key'])
                    log_exception('Match failed for ' + m['key'])
            return done, failed
        (done, failed), warnings = run_transaction(self.doc, 'Emperor - Match spaces to rooms', work)
        for key in done:
            e = self.doc.GetElement(self.meta[key]['element_id'])
            if is_valid(e):
                self._refresh_row(key, e, 'Matched to room')
        self._apply_filter('Space')
        self.last_report = ('Match spaces to rooms\nSpaces matched: {0}\nNo room found: {1}\nFailed: {2}\n'
                            'Height: {3}   Name and number: {4}\nRevit warnings suppressed: {5}').format(
            len(done), no_room, len(failed), 'yes' if do_h else 'no', 'yes' if do_n else 'no', warnings)
        self.finish_action(u'Matched {0} space(s) to rooms; no room for {1}; failed {2}.'.format(
            len(done), no_room, len(failed)), bool(failed))

    def _on_select(self, kind):
        ui = self.ui[kind]
        if 'edit_name' not in ui:
            return
        items = list(ui['grid'].SelectedItems)
        if len(items) != 1:
            return
        row = items[0]
        ui['edit_name'].Text = u(row['Name'])
        ui['edit_number'].Text = u(row['Number'])
        try:
            m = self.meta.get(u(row['Key']))
            if m is not None and m['host']:
                e = self.doc.GetElement(m['element_id'])
                p = e.get_Parameter(BIP.ROOM_HEIGHT) if is_valid(e) else None
                if p is not None and p.HasValue:
                    ui['edit_height'].Text = u'%.2f' % (p.AsDouble() * 0.3048)
        except Exception:
            pass

    def _ticked_keys(self, kind):
        keys = []
        for row in self.tables[kind].Rows:
            try:
                if row['Pick'] is True or u(row['Pick']).lower() == u'true':
                    keys.append(u(row['Key']))
            except Exception:
                pass
        return keys

    def _tick(self, kind, value):
        for item in self.tables[kind].DefaultView if value else self.tables[kind].Rows:
            try:
                key = u(item['Key'])
                if value and not (self.meta.get(key) or {}).get('host'):
                    continue
                item['Pick'] = bool(value)
            except Exception:
                pass
        self._update_counts()

    def _selected_host(self, kind):
        """Rows the edit tools work on: the TICKED rows when any are ticked, otherwise the selected rows."""
        ui = self.ui[kind]
        metas, linked = [], 0
        keys = self._ticked_keys(kind) or [u(item['Key']) for item in ui['grid'].SelectedItems]
        for key in keys:
            m = self.meta.get(key)
            if m is None or m['kind'] != kind:
                continue
            if m['host']:
                metas.append(m)
            else:
                linked += 1
        return metas, linked

    def _rename_one(self, kind):
        ui = self.ui[kind]
        metas = []
        for item in ui['grid'].SelectedItems:
            m = self.meta.get(u(item['Key']))
            if m is not None and m['kind'] == kind and m['host']:
                metas.append(m)
        if len(metas) != 1:
            metas, linked = self._selected_host(kind)
        if len(metas) != 1:
            self._message('Select exactly ONE host-model row to rename (linked rows are read-only).')
            self.finish_action('Rename: select one row.', True)
            return
        m = metas[0]
        name, number = u(ui['edit_name'].Text).strip(), u(ui['edit_number'].Text).strip()
        if not name:
            self._message('The name cannot be empty.')
            self.finish_action('Rename: no name.', True)
            return

        def work():
            e = self.doc.GetElement(m['element_id'])
            ok1 = set_field(e, 'Name', name)
            ok2 = set_field(e, 'Number', number) if number else True
            return ok1 and ok2
        ok, warnings = run_transaction(self.doc, 'Emperor - Rename {0}'.format(kind), work)
        e = self.doc.GetElement(m['element_id'])
        if is_valid(e):
            self._refresh_row(m['key'], e, 'Renamed')
        self._apply_filter(kind)
        self.finish_action(u'Renamed to {0} {1}.'.format(number, name) + (u' (Revit warning: duplicate number?)' if warnings else u''),
                           not ok)

    def _set_height(self, kind):
        ui = self.ui[kind]
        metas, linked = self._selected_host(kind)
        if not metas:
            self._message('Select one or more host-model rows first (linked rows are read-only).')
            self.finish_action('Set height: nothing selected.', True)
            return
        try:
            h_m = float(u(ui['edit_height'].Text).replace(',', '.'))
            if h_m <= 0 or h_m > 100:
                raise ValueError()
        except Exception:
            self._message('Enter the height in meters, e.g. 3.00.')
            self.finish_action('Set height: invalid height.', True)
            return
        h_ft = h_m / 0.3048
        h_mm = h_m * 1000.0

        def work():
            done, failed = [], []
            for m in metas:
                e = self.doc.GetElement(m['element_id'])
                try:
                    base = e.get_Parameter(BIP.ROOM_LOWER_OFFSET)
                    base_ft = base.AsDouble() if (base is not None and base.HasValue) else 0.0
                    e.get_Parameter(BIP.ROOM_UPPER_LEVEL).Set(e.LevelId)
                    e.get_Parameter(BIP.ROOM_UPPER_OFFSET).Set(base_ft + h_ft)
                    done.append(m['key'])
                except Exception:
                    failed.append(m['key'])
                    log_exception('Set height failed for ' + m['key'])
            return done, failed
        (done, failed), warnings = run_transaction(self.doc, 'Emperor - {0} height'.format(kind), work)
        for key in done:
            e = self.doc.GetElement(self.meta[key]['element_id'])
            if is_valid(e):
                self._refresh_row(key, e, 'Height {0:.2f} m'.format(h_m))
        self._apply_filter(kind)
        extra = u' ({0} linked row(s) skipped)'.format(linked) if linked else u''
        self.finish_action(u'Height {0:.2f} m set on {1}; failed {2}.{3}'.format(h_m, len(done), len(failed), extra), bool(failed))

    def _scope_section(self, kind):
        ui = self.ui[kind]
        ui['scope'] = T.combo(SCOPES, T.FIELD_WIDTH)
        ui['scope'].SelectedIndex = 1
        what = 'rooms' if kind == 'Room' else 'spaces'
        return T.section('APPLY TO', T.vstack(
            ui['scope'],
            T.hint('Used by every operation on this tab. Linked {0} are read-only and always skipped.'.format(what))))

    def _replace_section(self, kind, title, with_field):
        ui = self.ui[kind]
        body = T.vstack()
        if with_field:
            body.Children.Add(T.field_label('Target field'))
            ui['field'] = T.combo(['Name', 'Number'], T.FIELD_WIDTH)
            body.Children.Add(ui['field'])
        body.Children.Add(T.field_label('Find text'))
        ui['find'] = T.textbox('', T.FIELD_WIDTH)
        body.Children.Add(ui['find'])
        body.Children.Add(T.field_label('Replace with'))
        ui['replace'] = T.textbox('', T.FIELD_WIDTH)
        body.Children.Add(ui['replace'])
        ui['case'] = T.checkbox('Case sensitive')
        ui['whole'] = T.checkbox('Match whole word')
        body.Children.Add(T.hstack(ui['case'], ui['whole']))
        ui['prefix_on'] = T.checkbox('Add prefix', False)
        ui['prefix_on'].Width = 96
        ui['prefix'] = T.textbox('', T.FIELD_WIDTH - 104)
        body.Children.Add(T.hstack(ui['prefix_on'], ui['prefix']))
        ui['suffix_on'] = T.checkbox('Add suffix', False)
        ui['suffix_on'].Width = 96
        ui['suffix'] = T.textbox('', T.FIELD_WIDTH - 104)
        body.Children.Add(T.hstack(ui['suffix_on'], ui['suffix']))
        if kind == 'Space':
            body.Children.Add(T.hint('Prefix / suffix apply to names only, and also to the names of newly created spaces.'))
        action = 'room_replace' if kind == 'Room' else 'space_replace'
        body.Children.Add(self._action_button('Apply Changes', 'replace', action, True, T.FIELD_WIDTH))
        return T.section(title, body)

    def _build_room_tools(self):
        stack = T.vstack()
        stack.Children.Add(self._edit_section('Room'))
        stack.Children.Add(self._scope_section('Room'))
        stack.Children.Add(self._replace_section('Room', 'FIND & REPLACE ROOM NAMES', False))
        return stack

    def _build_space_tools(self):
        ui = self.ui['Space']
        stack = T.vstack()
        stack.Children.Add(self._edit_section('Space'))
        stack.Children.Add(self._match_section())
        stack.Children.Add(self._scope_section('Space'))

        create = T.vstack()
        create.Children.Add(T.field_label('Phase'))
        self.create_phase = T.combo(['Loading...'], T.FIELD_WIDTH)
        create.Children.Add(self.create_phase)
        create.Children.Add(T.field_label('Default name when no room matches'))
        self.default_space_name = T.textbox('Space', T.FIELD_WIDTH)
        create.Children.Add(self.default_space_name)
        self.copy_room_names = T.checkbox('Copy name and number from the room above (host or linked)', True)
        create.Children.Add(self.copy_room_names)
        self.assign_sequence = T.checkbox('Number the rest in sequence, starting at', True)
        self.start_number = T.textbox('1', 70)
        create.Children.Add(T.hstack(self.assign_sequence, self.start_number))
        buttons = WpfGrid()
        self._add_col(buttons, GridLength(1, GridUnitType.Star))
        self._add_col(buttons, GridLength(1, GridUnitType.Star))
        all_btn = self._action_button('All Levels', 'create', 'create_all_spaces', True, None,
                                      'Create spaces in every enclosed region on every level that has a floor plan.')
        one_btn = self._action_button('Pick Levels...', 'level', 'create_selected_spaces', False, None,
                                      'Choose the levels in a list, then create spaces only on those levels.')
        buttons.Children.Add(all_btn)
        WpfGrid.SetColumn(one_btn, 1)
        buttons.Children.Add(one_btn)
        create.Children.Add(buttons)
        create.Children.Add(T.hint('Existing spaces are kept. Spaces are bounded by host elements and by links whose type has Room Bounding ON. Revit also tags the new spaces in the plan view used.'))
        stack.Children.Add(T.section('CREATE SPACES', create))

        from_rooms = T.vstack()
        from_rooms.Children.Add(T.hint('One space at every room (host and linked rooms) on the levels you pick, '
                                       'in the phase chosen above. Rooms that already have a space are skipped.'))
        self.fr_names = T.checkbox('Name and number', True)
        self.fr_height = T.checkbox('Base offset and height', True)
        from_rooms.Children.Add(T.hstack(self.fr_names, self.fr_height))
        from_rooms.Children.Add(self._action_button('Create Spaces from Rooms...', 'copy', 'spaces_from_rooms', True,
                                                    T.FIELD_WIDTH, 'Pick the levels, then create a space for every room on them.'))
        stack.Children.Add(T.section('SPACES FROM ROOMS', from_rooms))

        clean = T.vstack()
        self.default_as_unnamed = T.checkbox("Treat default names ('Space' / the default above) as unnamed", True)
        self.include_unplaced = T.checkbox('Also delete not placed / not enclosed spaces', False)
        clean.Children.Add(self.default_as_unnamed)
        clean.Children.Add(self.include_unplaced)
        clean_buttons = WpfGrid()
        self._add_col(clean_buttons, GridLength(1, GridUnitType.Star))
        self._add_col(clean_buttons, GridLength(1, GridUnitType.Star))
        del_btn = self._action_button('Delete Unnamed', 'delete', 'delete_unnamed', False, None,
                                      'Delete host spaces without a real name (with confirmation).')
        ctr_btn = self._action_button('Recenter for Tags', 'center', 'center_spaces', False, None,
                                      'Move each space location point to an interior point near its centre.')
        clean_buttons.Children.Add(del_btn)
        WpfGrid.SetColumn(ctr_btn, 1)
        clean_buttons.Children.Add(ctr_btn)
        clean.Children.Add(clean_buttons)
        clean.Children.Add(self._action_button('Delete Spaces on Levels...', 'delete', 'delete_level_spaces', False,
                                               T.FIELD_WIDTH, 'Pick the levels, then delete EVERY host space on them '
                                               '(with confirmation; Revit Undo brings them back).'))
        stack.Children.Add(T.section('CLEAN UP & TAGGING', clean))

        stack.Children.Add(self._replace_section('Space', 'FIND & REPLACE NAMES / NUMBERS', True))
        return stack

    def _make_data_grid(self, table):
        grid = DataGrid()
        grid.AutoGenerateColumns = False
        grid.IsReadOnly = True
        grid.CanUserAddRows = False
        grid.CanUserDeleteRows = False
        grid.CanUserResizeRows = False
        grid.SelectionMode = DataGridSelectionMode.Extended
        grid.SelectionUnit = DataGridSelectionUnit.FullRow
        grid.HeadersVisibility = DataGridHeadersVisibility.Column
        grid.GridLinesVisibility = DataGridGridLinesVisibility.Horizontal
        grid.HorizontalGridLinesBrush = T.brush(T.GRID_LINE)
        grid.RowBackground = T.brush(T.WHITE)
        grid.AlternatingRowBackground = T.brush(T.ALT_ROW)
        grid.BorderBrush = T.brush(T.BORDER)
        grid.BorderThickness = Thickness(1)
        grid.RowHeaderWidth = 0
        grid.FontFamily = FontFamily('Segoe UI')
        grid.FontSize = 11.5
        grid.Foreground = T.brush(T.INK)
        try:
            grid.EnableRowVirtualization = True
            grid.EnableColumnVirtualization = True
        except Exception:
            pass
        try:
            tick = DataGridTemplateColumn()
            tick.Header = u'\u2713'
            tick.Width = DataGridLength(32)
            tick.CanUserResize = False
            tick.SortMemberPath = 'Pick'
            tick.CellTemplate = XamlReader.Parse(
                '<DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">'
                '<CheckBox HorizontalAlignment="Center" VerticalAlignment="Center" Cursor="Hand" '
                'IsChecked="{Binding [Pick], Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}"/></DataTemplate>')
            grid.Columns.Add(tick)
        except Exception:
            log_exception('Tick column not added.')
        specs = [('Name', 1.6, 130), ('Number', 0.6, 64), ('Level', 1.0, 90), ('Phase', 0.9, 80),
                 ('Area', 0.6, 70), ('Height', 0.55, 66), ('Source', 0.5, 56), ('Linked Model', 1.2, 100),
                 ('Element Id', 0.6, 74), ('Status', 0.8, 86)]
        for header, star, min_width in specs:
            col = DataGridTextColumn()
            col.Header = header + (u' (m)' if header == 'Height' else u'')
            col.Binding = Binding('[' + header + ']')
            col.MinWidth = min_width
            col.Width = DataGridLength(star, DataGridLengthUnitType.Star)
            col.SortMemberPath = header
            grid.Columns.Add(col)
        grid.ItemsSource = table.DefaultView
        return grid

    # ------------------------------------------------------------ status / filters
    def _current_kind(self):
        return 'Room' if self.tabs.SelectedIndex <= 0 else 'Space'

    def _on_tab_changed(self, sender, args):
        # SelectionChanged bubbles up from the grids and combo boxes inside the tabs.
        try:
            if args.OriginalSource is not self.tabs:
                return
            self._update_counts()
        except Exception:
            pass

    def _on_filter_changed(self, kind):
        if not self.loading:
            self._apply_filter(kind)

    def _apply_filter(self, kind):
        ui = self.ui[kind]
        table = self.tables[kind]
        conditions = []
        search = u(ui['search'].Text).strip()
        if search:
            s = like_escape(search)
            conditions.append(u"([Name] LIKE '%{0}%' OR [Number] LIKE '%{0}%' OR [Level] LIKE '%{0}%' "
                              u"OR [Phase] LIKE '%{0}%' OR [Linked Model] LIKE '%{0}%')".format(s))
        level = u(ui['level'].SelectedItem)
        if level and level != u'All Levels':
            conditions.append(u"[Level] = '{0}'".format(equals_escape(level)))
        source = u(ui['source'].SelectedItem)
        if source and source != u'All Sources':
            conditions.append(u"[Source] = '{0}'".format(equals_escape(source)))
        status = u(ui['status_filter'].SelectedItem)
        if status and status != u'Any Status':
            conditions.append(u"[Status] LIKE '{0}%'".format(like_escape(status)))
        try:
            table.DefaultView.RowFilter = u' AND '.join(conditions)
        except Exception:
            log_exception('Row filter rejected: ' + u' AND '.join(conditions))
            table.DefaultView.RowFilter = u''
        self._update_counts()

    def _update_counts(self):
        try:
            for kind in ('Room', 'Space'):
                ui = self.ui[kind]
                table = self.tables[kind]
                shown = table.DefaultView.Count
                selected = ui['grid'].SelectedItems.Count
                host = len([1 for m in self.meta.values() if m['kind'] == kind and m['host']])
                ui['counter'].Text = u'Showing {0} of {1}   |   Host: {2}   Linked: {3}   |   Selected: {4}   (Ctrl / Shift + click for several, double-click to select in Revit)'.format(
                    shown, table.Rows.Count, host, table.Rows.Count - host, selected)
            kind = self._current_kind()
            self.count_text.Text = u'{0}: {1} selected'.format('Rooms' if kind == 'Room' else 'Spaces',
                                                              self.ui[kind]['grid'].SelectedItems.Count)
        except Exception:
            pass

    def _set_status(self, message, is_error=False):
        try:
            message = u(message)
            low = message.lower()
            if is_error or 'fail' in low or 'error' in low:
                color = T.RED2
            elif any(w in low for w in ('complete', 'ready', 'loaded', 'updated', 'created', 'deleted', 'adjusted', 'selected', 'cleared')):
                color = T.GREEN
            else:
                color = T.GRAY
            self.status_text.Text = message
            self.status_text.Foreground = T.brush(color)
        except Exception:
            pass

    # ------------------------------------------------------------ data
    def _load_all_data(self):
        self.loading = True
        try:
            for table in self.tables.values():
                table.DefaultView.RowFilter = u''
                table.Rows.Clear()
            self.meta = {}
            self.rows = {}
            self.non_bounding_links = []
            for kind in ('Room', 'Space'):
                self._collect(kind, self.doc, None)
            try:
                links = list(DB.FilteredElementCollector(self.doc).OfClass(DB.RevitLinkInstance))
            except Exception:
                links = []
            seen_types = set()
            for link in links:
                try:
                    link_doc = link.GetLinkDocument()
                    if link_doc is None:
                        continue
                    for kind in ('Room', 'Space'):
                        self._collect(kind, link_doc, link)
                    type_id = id_value(link.GetTypeId())
                    if type_id not in seen_types:
                        seen_types.add(type_id)
                        link_type = self.doc.GetElement(link.GetTypeId())
                        p = link_type.get_Parameter(BIP.WALL_ATTR_ROOM_BOUNDING) if link_type is not None else None
                        if p is not None and p.AsInteger() == 0:
                            self.non_bounding_links.append(element_name(link_type))
                except Exception:
                    log_exception('Failed reading a linked model.')
            for kind in ('Room', 'Space'):
                self._populate_filter_levels(kind)
        finally:
            self.loading = False
        for kind in ('Room', 'Space'):
            self._apply_filter(kind)
        self.last_report = self._count_report('Model data loaded.')
        self._set_status('Model data loaded. Click Refresh after changing the model outside this window.')
        log(self.last_report)

    def _row_values(self, kind, element, source_doc):
        return {
            'Name': get_name(element),
            'Number': get_number(element),
            'Level': level_name(source_doc, element),
            'Phase': phase_name(source_doc, element),
            'Area': area_text(element),
            'Height': height_text(element),
            'Status': placement_state(element),
        }

    def _collect(self, kind, source_doc, link):
        table = self.tables[kind]
        is_host = link is None
        link_name = u'' if is_host else element_name(link)
        for element in spatial_elements(source_doc, kind):
            try:
                id_str = str(id_value(element.Id))
                if is_host:
                    key = 'H|{0}|{1}'.format(kind, id_str)
                else:
                    key = 'L|{0}|{1}|{2}'.format(kind, id_value(link.Id), id_str)
                row = table.NewRow()
                row['Key'] = key
                for column, value in self._row_values(kind, element, source_doc).items():
                    row[column] = value
                row['Source'] = 'Host' if is_host else 'Link'
                row['Linked Model'] = link_name
                row['Element Id'] = id_str
                if not is_host:
                    row['Status'] = u(row['Status']) + u' (read-only)'
                table.Rows.Add(row)
                self.rows[key] = row
                self.meta[key] = {'key': key, 'kind': kind, 'host': is_host, 'element_id': element.Id,
                                  'link_id': None if is_host else link.Id, 'link_name': link_name}
            except Exception:
                log_exception('Could not add a spatial element to the table.')

    def _populate_filter_levels(self, kind):
        combo = self.ui[kind]['level']
        current = u(combo.SelectedItem) or u'All Levels'
        names = []
        order = dict((element_name(l), i) for i, l in enumerate(sorted_levels(self.doc)))
        for row in self.tables[kind].Rows:
            name = u(row['Level'])
            if name and name not in names:
                names.append(name)
        names.sort(key=lambda n: (order.get(n, 9999), n.lower()))
        combo.Items.Clear()
        combo.Items.Add(u'All Levels')
        for name in names:
            combo.Items.Add(name)
        index = combo.Items.IndexOf(current)
        combo.SelectedIndex = index if index >= 0 else 0

    def _host_space_numbers(self):
        numbers = []
        for space in spatial_elements(self.doc, 'Space'):
            value = get_number(space).strip()
            if value:
                numbers.append(value)
        return numbers

    def _populate_creation_lists(self):
        self.loading = True
        try:
            self.phase_items = []
            self.create_phase.Items.Clear()
            current_phase = None
            try:
                p = self.uidoc.ActiveView.get_Parameter(BIP.VIEW_PHASE)
                if p is not None:
                    current_phase = id_value(p.AsElementId())
            except Exception:
                pass
            try:
                phases = list(self.doc.Phases)
            except Exception:
                phases = []
            selected = len(phases) - 1  # default: the last (newest) phase
            for i, phase in enumerate(phases):
                self.phase_items.append(phase)
                self.create_phase.Items.Add(element_name(phase))
                if current_phase is not None and id_value(phase.Id) == current_phase:
                    selected = i  # prefer the active view's phase
            if not self.phase_items:
                self.create_phase.Items.Add('(No phases found)')
                selected = 0
            self.create_phase.SelectedIndex = selected

            self.level_items = sorted_levels(self.doc)

            # Next free number; only overwrite the box if the user did not type their own value.
            digits = [int(n) for n in self._host_space_numbers() if n.isdigit()]
            new_auto = u(max(digits) + 1 if digits else 1)
            if u(self.start_number.Text).strip() in (u'', self.auto_start_number):
                self.start_number.Text = new_auto
            self.auto_start_number = new_auto
        finally:
            self.loading = False

    def _count_report(self, prefix):
        counts = {}
        for m in self.meta.values():
            k = (m['kind'], m['host'])
            counts[k] = counts.get(k, 0) + 1
        lines = [prefix,
                 'Rooms : {0} host, {1} linked'.format(counts.get(('Room', True), 0), counts.get(('Room', False), 0)),
                 'Spaces: {0} host, {1} linked'.format(counts.get(('Space', True), 0), counts.get(('Space', False), 0)),
                 '']
        if self.non_bounding_links:
            lines.append('Links with Room Bounding OFF (they will not bound new spaces):')
            for name in self.non_bounding_links:
                lines.append('  - ' + name)
            lines.append('')
        lines.append('Linked elements can be browsed and selected; edits apply to the host model only.')
        lines.append('Log: ' + LOG_PATH)
        return '\n'.join(lines)

    # ------------------------------------------------------------ actions
    def request_action(self, action):
        if self.busy:
            self._set_status('Busy - wait for the current action to finish.')
            return
        if self.external_event is None or self.handler is None:
            self._set_status('External event not available. Close and reopen the manager.', True)
            return
        self._set_busy(True)
        self._set_status('Working: ' + action.replace('_', ' ') + ' ...')
        self.handler.pending = action
        try:
            result = self.external_event.Raise()
            if result in (ExternalEventRequest.Denied, ExternalEventRequest.TimedOut):
                self._set_busy(False)
                self._set_status('Revit did not accept the request (it may be busy in another command). Try again.', True)
        except Exception:
            self._set_busy(False)
            log_exception('Could not raise external event.')
            self._set_status('Could not start the action. See log.', True)

    def _set_busy(self, value):
        self.busy = value
        try:
            for b in self.action_buttons:
                b.IsEnabled = not value
            self.win.Cursor = Cursors.Wait if value else None
        except Exception:
            pass

    def finish_action(self, message, is_error=False):
        self._set_busy(False)
        self._set_status(message, is_error)
        self._update_counts()

    def execute_action(self, action, uiapp):
        try:
            if not is_valid(self.doc):
                self.finish_action('The project was closed. Close this window.', True)
                return
            active = uiapp.ActiveUIDocument
            if active is None or not active.Document.Equals(self.doc):
                self.finish_action('Switch Revit back to "{0}" first - this window belongs to that project.'.format(self.doc.Title), True)
                return
            self.uidoc = active
            if action == 'refresh':
                self._load_all_data()
                self._populate_creation_lists()
                self.finish_action('Refresh complete.')
            elif action == 'room_replace':
                self._bulk_replace('Room')
            elif action == 'space_replace':
                self._bulk_replace('Space')
            elif action == 'delete_unnamed':
                self._delete_unnamed_spaces()
            elif action == 'center_spaces':
                self._center_spaces()
            elif action == 'create_all_spaces':
                self._create_spaces(True)
            elif action == 'create_selected_spaces':
                self._create_spaces(False)
            elif action == 'select':
                self._select_in_revit()
            elif action == 'spaces_from_rooms':
                self._spaces_from_rooms()
            elif action == 'delete_level_spaces':
                self._delete_level_spaces()
            elif action == 'match_all':
                self._match_spaces(False)
            elif action == 'match_selected':
                self._match_spaces(True)
            elif action.startswith('rename|'):
                self._rename_one(action.split('|', 1)[1])
            elif action.startswith('height|'):
                self._set_height(action.split('|', 1)[1])
            elif action == 'unselect':
                self.uidoc.Selection.SetElementIds(List[DB.ElementId]())
                self.finish_action('Revit selection cleared.')
            else:
                self.finish_action('Unknown action: ' + action, True)
        except Exception:
            log_exception('Action failed: ' + action)
            self.last_report = 'Action failed: {0}\n\n{1}\n\nLog: {2}'.format(action, traceback.format_exc(), LOG_PATH)
            self.finish_action('Action failed. See Results / Log.', True)
            self._show_report(self.last_report)

    # ---- helpers
    def _message(self, message, title=None, error=False):
        try:
            import emperor_ui
            emperor_ui.alert(u(message), title or ('Emperor - ' + TOOL_TITLE), owner=self.win, warn=error)
        except Exception:
            log(message)

    def _confirm(self, message, title):
        import emperor_ui
        return emperor_ui.alert(u(message), u(title), yes=True, no=True, owner=self.win, warn=True)

    def _scope_metas(self, kind):
        """Host-model metas for the tab's 'Apply to' choice. Returns (metas, scope_label, linked_skipped)."""
        ui = self.ui[kind]
        scope = ui['scope'].SelectedIndex
        what = 'rooms' if kind == 'Room' else 'spaces'
        if scope == 0:
            keys = [k for k, m in self.meta.items() if m['kind'] == kind]
            label = 'all host-model ' + what
        elif scope == 2:
            keys = [u(item['Key']) for item in ui['grid'].SelectedItems]
            label = 'selected rows'
        elif scope == 3:
            keys = self._ticked_keys(kind)
            label = 'ticked rows'
        else:
            keys = [u(item['Key']) for item in self.tables[kind].DefaultView]
            label = 'filtered rows ({0} shown)'.format(len(keys))
        metas = []
        linked = 0
        for key in keys:
            m = self.meta.get(key)
            if m is None or m['kind'] != kind:
                continue
            if m['host']:
                metas.append(m)
            else:
                linked += 1
        return metas, label, linked

    def _refresh_row(self, key, element, status=None):
        row = self.rows.get(key)
        if row is None:
            return
        for column, value in self._row_values(self.meta[key]['kind'], element, self.doc).items():
            row[column] = value
        if status:
            row['Status'] = u(row['Status']) + u' - ' + u(status)

    def _remove_key(self, key):
        row = self.rows.pop(key, None)
        meta = self.meta.pop(key, None)
        if row is not None and meta is not None:
            try:
                self.tables[meta['kind']].Rows.Remove(row)
            except Exception:
                pass

    def _add_host_row(self, kind, element, status):
        key = 'H|{0}|{1}'.format(kind, id_value(element.Id))
        if key in self.meta:
            self._refresh_row(key, element, status)
            return
        row = self.tables[kind].NewRow()
        row['Key'] = key
        for column, value in self._row_values(kind, element, self.doc).items():
            row[column] = value
        row['Source'] = 'Host'
        row['Linked Model'] = u''
        row['Element Id'] = u(id_value(element.Id))
        row['Status'] = u(row['Status']) + u' - ' + u(status)
        self.tables[kind].Rows.Add(row)
        self.rows[key] = row
        self.meta[key] = {'key': key, 'kind': kind, 'host': True, 'element_id': element.Id, 'link_id': None, 'link_name': u''}

    # ---- bulk replace
    def _replace_options(self, kind):
        ui = self.ui[kind]
        field = u(ui['field'].SelectedItem) if 'field' in ui else u'Name'
        return {'find': u(ui['find'].Text), 'replace': u(ui['replace'].Text),
                'case': bool(ui['case'].IsChecked), 'whole': bool(ui['whole'].IsChecked),
                'prefix': u(ui['prefix'].Text) if ui['prefix_on'].IsChecked else u'',
                'suffix': u(ui['suffix'].Text) if ui['suffix_on'].IsChecked else u'',
                'field': field if field in (u'Name', u'Number') else u'Name'}

    def _new_value(self, original, opt):
        value = u(original)
        if opt['find']:
            pattern = re.escape(opt['find'])
            if opt['whole']:
                pattern = r'(?<!\w)' + pattern + r'(?!\w)'
            flags = re.UNICODE if opt['case'] else (re.IGNORECASE | re.UNICODE)
            replacement = opt['replace']
            value = re.sub(pattern, lambda m: replacement, value, flags=flags)
        if opt['field'] == u'Name':
            value = opt['prefix'] + value + opt['suffix']
        return value

    def _bulk_replace(self, kind):
        opt = self._replace_options(kind)
        is_name = opt['field'] == u'Name'
        if not opt['find'] and not (is_name and (opt['prefix'] or opt['suffix'])):
            self._message('Enter the text to find, or tick Add prefix / Add suffix (names only).')
            self.finish_action('Nothing to change.')
            return
        metas, scope, linked = self._scope_metas(kind)
        planned = []
        for m in metas:
            element = self.doc.GetElement(m['element_id'])
            if not is_valid(element):
                continue
            original = get_name(element) if is_name else get_number(element)
            new = self._new_value(original, opt)
            if new != original:
                planned.append((m, original, new))
        if not planned:
            self.last_report = 'No values would change in {0}.\nCheck the find text, case and whole-word options, and the Apply to choice.'.format(scope)
            self.finish_action('No matching values found.')
            self._show_report(self.last_report)
            return
        preview = '\n'.join(u'  {0}  ->  {1}'.format(o or u'(empty)', n or u'(empty)') for _, o, n in planned[:12])
        if len(planned) > 12:
            preview += u'\n  ... and {0} more'.format(len(planned) - 12)
        extra = '\n{0} linked row(s) in the scope are skipped (read-only).'.format(linked) if linked else ''
        if not self._confirm(u'Change {0} {1} value(s) in {2}?{3}\n\n{4}'.format(len(planned), opt['field'].lower(), scope, extra, preview),
                             'Confirm Bulk Changes'):
            self.finish_action('Cancelled.')
            return

        def work():
            done, failed = [], []
            for m, original, new in planned:
                try:
                    if set_field(self.doc.GetElement(m['element_id']), opt['field'], new):
                        done.append(m['key'])
                    else:
                        failed.append(m['key'])
                except Exception:
                    failed.append(m['key'])
                    log_exception('Bulk update failed for ' + m['key'])
            return done, failed
        name = 'Emperor - {0} {1} Replace'.format(kind, opt['field'])
        (done, failed), warnings = run_transaction(self.doc, name, work)
        for key in done:
            element = self.doc.GetElement(self.meta[key]['element_id'])
            if is_valid(element):
                self._refresh_row(key, element, 'Updated')
        self._apply_filter(kind)
        self.last_report = ('Bulk replace complete.\nKind: {0}\nField: {1}\nScope: {2}\nUpdated: {3}\nFailed: {4}\n'
                            'Revit warnings suppressed: {5}{6}\n\nLog: {7}').format(
            kind, opt['field'], scope, len(done), len(failed), warnings,
            '\n(Duplicate numbers are allowed by Revit but give warnings - check the numbers.)' if warnings else '', LOG_PATH)
        self.finish_action('Updated {0} value(s); failed {1}.'.format(len(done), len(failed)), bool(failed))

    # ---- delete unnamed
    def _delete_unnamed_spaces(self):
        metas, scope, linked = self._scope_metas('Space')
        default_names = set([REVIT_DEFAULT_SPACE_NAME])
        typed_default = u(self.default_space_name.Text).strip().lower()
        if typed_default:
            default_names.add(typed_default)
        treat_default = bool(self.default_as_unnamed.IsChecked)
        include_unplaced = bool(self.include_unplaced.IsChecked)
        targets = []
        for m in metas:
            element = self.doc.GetElement(m['element_id'])
            if not is_valid(element):
                continue
            name = get_name(element).strip()
            unnamed = (not name) or (treat_default and name.lower() in default_names)
            if unnamed or (include_unplaced and placement_state(element) != u'Placed'):
                targets.append(m)
        if not targets:
            self.last_report = 'No unnamed spaces found in {0}.'.format(scope)
            self.finish_action('No unnamed spaces found.')
            self._show_report(self.last_report)
            return
        if not self._confirm('Delete {0} space(s) from {1}?\n\nTheir tags are deleted with them. You can undo with Revit Undo.'.format(len(targets), scope),
                             'Confirm Space Deletion'):
            self.finish_action('Cancelled.')
            return

        def work():
            done, failed = [], []
            for m in targets:
                try:
                    self.doc.Delete(m['element_id'])
                    done.append(m['key'])
                except Exception:
                    failed.append(m['key'])
                    log_exception('Delete failed for ' + m['key'])
            return done, failed
        (done, failed), warnings = run_transaction(self.doc, 'Emperor - Delete Unnamed Spaces', work)
        for key in done:
            self._remove_key(key)
        self._apply_filter('Space')
        self.last_report = 'Delete unnamed spaces complete.\nScope: {0}\nDeleted: {1}\nFailed: {2}\nRevit warnings suppressed: {3}\n\nLog: {4}'.format(
            scope, len(done), len(failed), warnings, LOG_PATH)
        self.finish_action('Deleted {0} space(s); failed {1}.'.format(len(done), len(failed)), bool(failed))

    # ---- recenter
    def _inside(self, space, point):
        try:
            return bool(space.IsPointInSpace(point))
        except Exception:
            return False

    def _interior_point(self, space):
        box = space.get_BoundingBox(None)
        old = location_point(space)
        if box is None or old is None:
            return None
        cx = (box.Min.X + box.Max.X) / 2.0
        cy = (box.Min.Y + box.Max.Y) / 2.0
        z = (box.Min.Z + box.Max.Z) / 2.0
        if self._inside(space, DB.XYZ(cx, cy, z)):
            return DB.XYZ(cx, cy, old.Z)
        # Irregular shape: test a grid of candidates nearest-to-centre first and
        # stop at the first one inside - same result as testing all, far fewer calls.
        width = box.Max.X - box.Min.X
        height = box.Max.Y - box.Min.Y
        steps = [i / 24.0 for i in range(1, 24)]
        candidates = []
        for fx in steps:
            for fy in steps:
                x = box.Min.X + width * fx
                y = box.Min.Y + height * fy
                candidates.append(((x - cx) ** 2 + (y - cy) ** 2, x, y))
        candidates.sort()
        for score, x, y in candidates:
            if self._inside(space, DB.XYZ(x, y, z)):
                return DB.XYZ(x, y, old.Z)
        return None

    def _center_spaces(self):
        metas, scope, linked = self._scope_metas('Space')
        if not metas:
            self._message('No host spaces in the current scope ({0}).'.format(scope))
            self.finish_action('No spaces to recenter.')
            return
        if not self._confirm('Move the location point of {0} space(s) in {1} to an interior point near the centre?\n\nBoundaries do not change. Existing tags stay where they are; new tags use the new point.'.format(len(metas), scope),
                             'Confirm Recenter'):
            self.finish_action('Cancelled.')
            return

        def work():
            moved, same, skipped = 0, 0, 0
            for m in metas:
                space = self.doc.GetElement(m['element_id'])
                try:
                    if not is_valid(space) or placement_state(space) != u'Placed':
                        skipped += 1
                        continue
                    target = self._interior_point(space)
                    old = location_point(space)
                    if target is None or old is None:
                        skipped += 1
                        continue
                    if old.DistanceTo(target) < 0.01:
                        same += 1
                        continue
                    try:
                        space.Location.Point = target
                    except Exception:
                        DB.ElementTransformUtils.MoveElement(self.doc, space.Id, target.Subtract(old))
                    moved += 1
                except Exception:
                    skipped += 1
                    log_exception('Recenter failed for ' + m['key'])
            return moved, same, skipped
        (moved, same, skipped), warnings = run_transaction(self.doc, 'Emperor - Recenter Spaces', work)
        self.last_report = ('Recenter complete.\nScope: {0}\nMoved: {1}\nAlready centred: {2}\nSkipped (not placed / no interior point): {3}\n'
                            'Revit warnings suppressed: {4}\n\nLog: {5}').format(scope, moved, same, skipped, warnings, LOG_PATH)
        self.finish_action('Adjusted {0} space(s); {1} already centred; skipped {2}.'.format(moved, same, skipped))

    # ---- create spaces
    def _find_plan_view(self, level, phase):
        best, best_score = None, -1
        for view in DB.FilteredElementCollector(self.doc).OfClass(DB.ViewPlan):
            try:
                if view.IsTemplate or view.GenLevel is None or id_value(view.GenLevel.Id) != id_value(level.Id):
                    continue
                if view.ViewType not in (DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan, DB.ViewType.EngineeringPlan):
                    continue
                score = 0
                if view.ViewType == DB.ViewType.FloorPlan:
                    score += 5
                p = view.get_Parameter(BIP.VIEW_PHASE)
                if p is not None and id_value(p.AsElementId()) == id_value(phase.Id):
                    score += 10
                if score > best_score:
                    best, best_score = view, score
            except Exception:
                pass
        return best

    def _create_spaces(self, all_levels):
        index = self.create_phase.SelectedIndex
        phase = self.phase_items[index] if 0 <= index < len(self.phase_items) else None
        if phase is None:
            self._message('No phase is available in this project.')
            self.finish_action('No phase.', True)
            return
        if all_levels:
            levels = list(self.level_items)
        else:
            levels = self._pick_levels('Create spaces - levels', 'Pick the levels to create spaces on '
                                       '(Ctrl / Shift + click for several).', False)
        if not levels:
            if all_levels:
                self._message('No levels found.')
            self.finish_action('No level chosen.')
            return
        try:
            next_number = int(u(self.start_number.Text).strip())
            if next_number < 0:
                raise ValueError()
        except Exception:
            self._message('The starting number must be a whole number (0 or more).')
            self.finish_action('Invalid starting number.', True)
            return
        scope = 'all levels' if all_levels else 'levels ' + ', '.join(element_name(l) for l in levels)
        bounding_note = ''
        if self.non_bounding_links:
            bounding_note = '\n\nThese links have Room Bounding OFF, so their walls will NOT bound spaces:\n  ' + '\n  '.join(self.non_bounding_links)
        if not self._confirm('Create spaces on {0} for phase "{1}"?\n\nExisting spaces are kept; Revit fills only empty enclosed regions.{2}'.format(
                scope, element_name(phase), bounding_note), 'Confirm Space Creation'):
            self.finish_action('Cancelled.')
            return

        copy_room = bool(self.copy_room_names.IsChecked)
        assign_seq = bool(self.assign_sequence.IsChecked)
        default_name = u(self.default_space_name.Text).strip() or u'Space'
        opt = self._replace_options('Space')
        prefix, suffix = opt['prefix'], opt['suffix']
        used = set(n.lower() for n in self._host_space_numbers())
        counter = [next_number]
        matcher = RoomMatcher(self.doc) if copy_room else None
        phase_label = element_name(phase)
        results, created_ids = [], []
        totals = {'created': 0, 'matched': 0, 'warnings': 0}

        def make_level_work(level, view):
            def work():
                ids = list(self.doc.Create.NewSpaces2(level, phase, view))
                matched = 0
                for space_id in ids:
                    space = self.doc.GetElement(space_id)
                    if not is_valid(space):
                        continue
                    record = matcher.match(location_point(space), phase_label) if matcher else None
                    name = record['name'].strip() if record is not None and record['name'].strip() else default_name
                    set_field(space, 'Name', prefix + name + suffix)
                    numbered = False
                    if record is not None:
                        matched += 1
                        number = record['number'].strip()
                        if number and number.lower() not in used and set_field(space, 'Number', number):
                            used.add(number.lower())
                            numbered = True
                    if assign_seq and not numbered:
                        while u(counter[0]).lower() in used:
                            counter[0] += 1
                        if set_field(space, 'Number', u(counter[0])):
                            used.add(u(counter[0]).lower())
                            counter[0] += 1
                return ids, matched
            return work

        group = DB.TransactionGroup(self.doc, 'Emperor - Create Spaces')
        group.Start()
        try:
            for level in levels:
                lname = element_name(level)
                view = self._find_plan_view(level, phase)
                if view is None:
                    results.append(u'{0}: skipped - no floor / ceiling / structural plan view for this level'.format(lname))
                    continue
                try:
                    (ids, matched), warnings = run_transaction(self.doc, 'Create Spaces - ' + lname, make_level_work(level, view))
                    created_ids.extend(ids)
                    totals['created'] += len(ids)
                    totals['matched'] += matched
                    totals['warnings'] += warnings
                    results.append(u'{0}: {1} created, {2} matched to rooms (view: {3})'.format(
                        lname, len(ids), matched, element_name(view)) if ids else u'{0}: 0 - no empty enclosed regions'.format(lname))
                except Exception as ex:
                    log_exception('Space creation failed on level ' + lname)
                    results.append(u'{0}: FAILED - {1}'.format(lname, u(ex)))
            group.Assimilate()
        except Exception:
            try:
                group.RollBack()
            except Exception:
                pass
            raise

        for space_id in created_ids:
            space = self.doc.GetElement(space_id)
            if is_valid(space):
                self._add_host_row('Space', space, 'Created')
        self._populate_filter_levels('Space')
        self._apply_filter('Space')
        lines = ['Create spaces - results', 'Phase: ' + phase_label, 'Scope: ' + scope,
                 'Created: {0}   Matched to rooms: {1}   Revit warnings suppressed: {2}'.format(
                     totals['created'], totals['matched'], totals['warnings']), '']
        lines.extend(results)
        if self.non_bounding_links:
            lines.append('')
            lines.append('Links with Room Bounding OFF: ' + ', '.join(self.non_bounding_links))
        lines.append('')
        lines.append('One undo step: "Emperor - Create Spaces".  Log: ' + LOG_PATH)
        self.last_report = '\n'.join(lines)
        self.finish_action('Created {0} space(s) on {1} level(s).'.format(totals['created'], len(levels)))
        self._show_report(self.last_report)

    # ---- level picker
    def _pick_levels(self, title, prompt, preselect_all=True, extra=None):
        """Emperor list of the host levels (+ optional extra entries). Returns the picked items."""
        levels = list(self.level_items) or sorted_levels(self.doc)
        items = list(levels) + list(extra or [])
        labels = []
        for lev in levels:
            try:
                labels.append(u'{0}   ({1:+.2f} m)'.format(element_name(lev), lev.ProjectElevation * 0.3048))
            except Exception:
                labels.append(element_name(lev))
        labels.extend(u(x) for x in (extra or []))
        import emperor_ui
        picked = emperor_ui.choose(title, labels, prompt, multi=True,
                                   preselect=list(range(len(levels))) if preselect_all else [], owner=self.win)
        return [items[i] for i in picked]

    # ---- delete spaces on levels
    def _delete_level_spaces(self):
        not_placed = u'(Not placed spaces - no location)'
        picked = self._pick_levels('Delete spaces - levels',
                                   'Every host space on the picked levels is deleted. Ctrl / Shift + click for several.',
                                   False, [not_placed])
        if not picked:
            self.finish_action('Delete spaces: no level picked.')
            return
        level_ids = set(id_value(l.Id) for l in picked if not isinstance(l, basestring))
        with_unplaced = not_placed in picked
        targets = []
        for sp in spatial_elements(self.doc, 'Space'):
            try:
                unplaced = sp.Location is None or location_point(sp) is None
                if (unplaced and with_unplaced) or (not unplaced and id_value(sp.LevelId) in level_ids):
                    targets.append(sp.Id)
            except Exception:
                pass
        names = [element_name(l) if not isinstance(l, basestring) else l for l in picked]
        if not targets:
            self._message('There are no spaces on: ' + ', '.join(names))
            self.finish_action('No spaces to delete.')
            return
        if not self._confirm(u'Delete ALL {0} space(s) on:\n  {1}\n\nTheir tags go with them. Revit Undo brings them back.'.format(
                len(targets), u'\n  '.join(names)), 'Confirm Space Deletion'):
            self.finish_action('Cancelled.')
            return

        def work():
            done, failed = [], []
            for i in targets:
                try:
                    self.doc.Delete(i)
                    done.append(i)
                except Exception:
                    failed.append(i)
                    log_exception('Delete failed for space ' + u(id_value(i)))
            return done, failed
        (done, failed), warnings = run_transaction(self.doc, 'Emperor - Delete Spaces on Levels', work)
        for i in done:
            self._remove_key('H|Space|{0}'.format(id_value(i)))
        self._populate_filter_levels('Space')
        self._apply_filter('Space')
        self.last_report = u'Delete spaces on levels\nLevels: {0}\nDeleted: {1}\nFailed: {2}\nRevit warnings suppressed: {3}'.format(
            u', '.join(names), len(done), len(failed), warnings)
        self.finish_action(u'Deleted {0} space(s); failed {1}.'.format(len(done), len(failed)), bool(failed))

    # ---- spaces from rooms
    def _room_sources(self, phase_label):
        """[(room, transform or None, source name)] for host rooms and rooms of loaded links in the phase
        (a link without a phase of that name gives the rooms of its last phase)."""
        out = []
        want = u(phase_label).lower()
        docs = [(self.doc, None, u'Host')]
        try:
            for link in DB.FilteredElementCollector(self.doc).OfClass(DB.RevitLinkInstance):
                try:
                    ld = link.GetLinkDocument()
                    if ld is not None:
                        docs.append((ld, link.GetTotalTransform(), element_name(link)))
                except Exception:
                    log_exception('Could not read a link for spaces from rooms.')
        except Exception:
            pass
        for d, tr, source in docs:
            try:
                phases = [element_name(ph).lower() for ph in d.Phases]
            except Exception:
                phases = []
            use = want if (want in phases or not phases) else phases[-1]
            for room in spatial_elements(d, 'Room'):
                try:
                    if room.Area <= 1e-6 or location_point(room) is None:
                        continue
                    if phases and phase_name(d, room).lower() != use:
                        continue
                    out.append((room, tr, source, d))
                except Exception:
                    pass
        return out

    def _spaces_from_rooms(self):
        index = self.create_phase.SelectedIndex
        phase = self.phase_items[index] if 0 <= index < len(self.phase_items) else None
        if phase is None:
            self._message('No phase is available in this project.')
            self.finish_action('No phase.', True)
            return
        levels = self._pick_levels('Spaces from rooms - levels',
                                   'Create a space for every room on the picked levels. Ctrl / Shift + click for several.', True)
        if not levels:
            self.finish_action('Spaces from rooms: no level picked.')
            return
        all_levels = list(self.level_items) or sorted_levels(self.doc)
        picked_ids = set(id_value(l.Id) for l in levels)
        copy_names, copy_height = bool(self.fr_names.IsChecked), bool(self.fr_height.IsChecked)
        phase_label = element_name(phase)

        def host_level_for(z, link_level_z):
            best = None
            for lev in all_levels:
                if abs(lev.ProjectElevation - link_level_z) < 0.1:
                    return lev
            for lev in all_levels:
                if lev.ProjectElevation <= z + 0.1:
                    best = lev
            return best or (all_levels[0] if all_levels else None)

        plan, skipped_level, skipped_existing = [], 0, 0
        for room, tr, source, rdoc in self._room_sources(phase_label):
            try:
                pt = location_point(room)
                rlev = rdoc.GetElement(room.LevelId)
                lo = room.get_Parameter(BIP.ROOM_LOWER_OFFSET)
                lo_ft = lo.AsDouble() if (lo is not None and lo.HasValue) else 0.0
                rlev_z = rlev.ProjectElevation if rlev is not None else pt.Z
                if tr is not None:
                    pt = tr.OfPoint(pt)
                    rlev_z = tr.OfPoint(DB.XYZ(0, 0, rlev_z)).Z
                    level = host_level_for(rlev_z + lo_ft, rlev_z)
                else:
                    level = rlev
                if level is None or id_value(level.Id) not in picked_ids:
                    skipped_level += 1
                    continue
                base_off = (rlev_z + lo_ft) - level.ProjectElevation
                test = DB.XYZ(pt.X, pt.Y, level.ProjectElevation + max(base_off, 0.0) + 1.0)
                try:
                    if self.doc.GetSpaceAtPoint(test, phase) is not None:
                        skipped_existing += 1
                        continue
                except Exception:
                    pass
                hp = room.get_Parameter(BIP.ROOM_HEIGHT)
                height = hp.AsDouble() if (hp is not None and hp.HasValue) else None
                plan.append({'room': room, 'pt': pt, 'level': level, 'base': base_off, 'height': height,
                             'name': get_name(room), 'number': get_number(room), 'source': source})
            except Exception:
                log_exception('Spaces from rooms: room skipped.')
        if not plan:
            self._message(u'Nothing to create on the picked levels.\n\nRooms that already have a space: {0}\n'
                          u'Rooms on other levels: {1}'.format(skipped_existing, skipped_level))
            self.finish_action('Spaces from rooms: nothing to create.')
            return
        if not self._confirm(u'Create {0} space(s) from rooms on {1} level(s), phase "{2}"?\n\n'
                             u'Rooms that already have a space: {3} (skipped).'.format(
                                 len(plan), len(levels), phase_label, skipped_existing), 'Confirm Spaces from Rooms'):
            self.finish_action('Cancelled.')
            return

        def work():
            made, failed = [], 0
            for p in plan:
                try:
                    sp = self.doc.Create.NewSpace(p['level'], phase, DB.UV(p['pt'].X, p['pt'].Y))
                    if sp is None:
                        failed += 1
                        continue
                    if copy_names:
                        if p['name']:
                            set_field(sp, 'Name', p['name'])
                        if p['number']:
                            set_field(sp, 'Number', p['number'])
                    if copy_height:
                        try:
                            sp.get_Parameter(BIP.ROOM_LOWER_OFFSET).Set(p['base'])
                            if p['height']:
                                sp.get_Parameter(BIP.ROOM_UPPER_LEVEL).Set(p['level'].Id)
                                sp.get_Parameter(BIP.ROOM_UPPER_OFFSET).Set(p['base'] + p['height'])
                        except Exception:
                            log_exception('Height not copied for room ' + p['number'])
                    made.append(sp.Id)
                except Exception:
                    failed += 1
                    log_exception('Space from room failed: ' + p['number'] + ' ' + p['name'])
            return made, failed
        (made, failed), warnings = run_transaction(self.doc, 'Emperor - Spaces from Rooms', work)
        not_enclosed = 0
        for i in made:
            sp = self.doc.GetElement(i)
            if is_valid(sp):
                if placement_state(sp) != u'Placed':
                    not_enclosed += 1
                self._add_host_row('Space', sp, 'From room')
        self._populate_filter_levels('Space')
        self._apply_filter('Space')
        lines = ['Spaces from rooms', 'Phase: ' + phase_label,
                 'Levels: ' + ', '.join(element_name(l) for l in levels),
                 'Created: {0}   Failed: {1}'.format(len(made), failed),
                 'Skipped - room already has a space: {0}'.format(skipped_existing),
                 'Not enclosed (no bounding walls at that spot): {0}'.format(not_enclosed),
                 'Revit warnings suppressed: {0}'.format(warnings), '']
        if self.non_bounding_links:
            lines.append('Links with Room Bounding OFF (turn it on so their walls bound the spaces): '
                         + ', '.join(self.non_bounding_links))
        lines.append('One undo step: "Emperor - Spaces from Rooms".')
        self.last_report = '\n'.join(lines)
        self.finish_action(u'Created {0} space(s) from rooms; {1} not enclosed; failed {2}.'.format(
            len(made), not_enclosed, failed), bool(failed))
        self._show_report(self.last_report)

    # ---- selection
    def _select_in_revit(self):
        kind = self._current_kind()
        keys = [u(item['Key']) for item in self.ui[kind]['grid'].SelectedItems]
        if not keys:
            self._message('Highlight one or more rows first (Ctrl / Shift + click for several).')
            self.finish_action('No rows highlighted.')
            return
        refs = List[DB.Reference]()
        host_ids = List[DB.ElementId]()
        linked = 0
        for key in keys:
            m = self.meta.get(key)
            if m is None:
                continue
            try:
                if m['host']:
                    element = self.doc.GetElement(m['element_id'])
                    if is_valid(element):
                        host_ids.Add(element.Id)
                        refs.Add(DB.Reference(element))
                else:
                    link = self.doc.GetElement(m['link_id'])
                    link_doc = link.GetLinkDocument() if link is not None else None
                    element = link_doc.GetElement(m['element_id']) if link_doc is not None else None
                    if is_valid(element):
                        refs.Add(DB.Reference(element).CreateLinkReference(link))
                        linked += 1
            except Exception:
                log_exception('Could not build a reference for ' + key)
        if refs.Count == 0:
            self.finish_action('Nothing could be selected.', True)
            return
        try:
            self.uidoc.Selection.SetReferences(refs)
            self.finish_action('Selected {0} element(s) in Revit ({1} linked).'.format(refs.Count, linked))
        except Exception:
            log_exception('SetReferences failed; selecting host elements only.')
            self.uidoc.Selection.SetElementIds(host_ids)
            self.finish_action('Selected {0} host element(s); linked elements could not be selected here.'.format(host_ids.Count))

    # ------------------------------------------------------------ report window
    def _show_report(self, report_text):
        try:
            w = Window()
            w.Title = 'Emperor - {0} - Results'.format(TOOL_TITLE)
            w.Owner = self.win
            w.Width = 640
            w.Height = 460
            w.MinWidth = 480
            w.MinHeight = 300
            w.WindowStartupLocation = WindowStartupLocation.CenterOwner
            w.Background = T.brush(T.WINDOW_BG)
            w.FontFamily = FontFamily('Segoe UI')
            try:
                th = T.theme()
                if th is not None:
                    w.Resources.MergedDictionaries.Add(th)
            except Exception:
                pass
            T.enable_glow(w)
            dock = DockPanel()
            head = Border()
            head.Background = T.header_brush()
            head.Padding = Thickness(14, 8, 14, 8)
            head.Child = T.text('RESULTS', 14, T.WHITE, True)
            DockPanel.SetDock(head, Dock.Top)
            dock.Children.Add(head)
            buttons = StackPanel()
            buttons.Orientation = Orientation.Horizontal
            buttons.HorizontalAlignment = HorizontalAlignment.Right
            buttons.Margin = Thickness(8, 0, 8, 8)
            box = TextBox()
            copy_btn = T.button('Copy', 'copy', False, 100)
            copy_btn.Click += self._safe(lambda: System.Windows.Clipboard.SetText(u(box.Text)))
            close_btn = T.button('Close', 'close', True, 100)
            close_btn.Click += self._safe(lambda: w.Close())
            buttons.Children.Add(copy_btn)
            buttons.Children.Add(close_btn)
            DockPanel.SetDock(buttons, Dock.Bottom)
            dock.Children.Add(buttons)
            box.Text = u(report_text)
            box.IsReadOnly = True
            box.AcceptsReturn = True
            box.TextWrapping = TextWrapping.NoWrap
            box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
            box.HorizontalScrollBarVisibility = ScrollBarVisibility.Auto
            box.FontFamily = FontFamily('Consolas')
            box.FontSize = 12
            box.Margin = Thickness(8)
            box.Padding = Thickness(6)
            box.BorderBrush = T.brush(T.BORDER)
            box.Foreground = T.brush(T.INK)
            dock.Children.Add(box)
            w.Content = dock
            w.ShowDialog()
        except Exception:
            log_exception('Report window failed.')
            self._message(report_text)

    def show(self):
        self.win.Show()


# =============================================================== launcher
def _registry_key(doc):
    try:
        return REGISTRY_KEY + str(doc.GetHashCode())
    except Exception:
        return REGISTRY_KEY + u(doc.Title)


def launch(uiapp):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or uidoc.Document is None:
        import emperor_ui
        emperor_ui.alert('Open a Revit project first.', 'Emperor - ' + TOOL_TITLE, warn=True)
        return
    doc = uidoc.Document
    if doc.IsFamilyDocument:
        import emperor_ui
        emperor_ui.alert('Room & Space Manager works in projects, not in the Family Editor.', 'Emperor - ' + TOOL_TITLE)
        return
    key = _registry_key(doc)
    domain = AppDomain.CurrentDomain
    try:
        existing = domain.GetData(key)
        if existing is not None and existing.win.IsVisible:
            if existing.win.WindowState == System.Windows.WindowState.Minimized:
                existing.win.WindowState = System.Windows.WindowState.Normal
            existing.win.Activate()
            return
    except Exception:
        pass
    manager = RoomSpaceManager(uiapp, uidoc)
    manager.handler = ActionHandler(manager)
    manager.external_event = ExternalEvent.Create(manager.handler)

    def on_closed(sender, args):
        try:
            domain.SetData(key, None)
            manager.external_event.Dispose()
        except Exception:
            pass
    manager.win.Closed += on_closed
    domain.SetData(key, manager)
    manager.show()
