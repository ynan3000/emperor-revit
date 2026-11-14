# -*- coding: ascii -*-
"""Emperor - Sync Views (plans only).

While ON, switching from one plan view to another keeps the same zoom and position, so the new plan
opens on exactly the same spot. Works between floor plans, ceiling plans, structural (engineering) plans
and area plans of the same project - never for 3D views, sections, elevations, drafting views or sheets.
Going plan -> section -> plan still syncs the second plan with the first.

How: Revit's ViewActivating event stores the zoom corners of the plan you leave, ViewActivated zooms the
plan you open to the same rectangle. The ON / OFF choice is kept in %APPDATA%\\Emperor\\sync_views.xml and
applied when Revit starts. The two event handlers are kept in the AppDomain so the ribbon button (another
script engine) can remove them again.
"""
import os
import re

APP_KEY = 'EmperorSyncViews.Handlers'


def _folder():
    folder = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'Emperor')
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return folder


def _settings_path():
    return os.path.join(_folder(), 'sync_views.xml')


def is_enabled():
    try:
        with open(_settings_path()) as f:
            m = re.search(r'enabled\s*=\s*"([^"]*)"', f.read())
        return bool(m) and m.group(1).strip().lower() == 'true'
    except Exception:
        return False


def set_enabled(value):
    try:
        with open(_settings_path(), 'w') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                    '<!-- Emperor Sync Views: true = plans keep the same zoom / position (starts with Revit) -->\n'
                    '<SyncViews enabled="%s"/>\n' % ('true' if value else 'false'))
    except Exception:
        pass


def _log(text):
    try:
        with open(os.path.join(_folder(), 'sync_views.log'), 'a') as f:
            f.write(text.rstrip() + '\n')
    except Exception:
        pass


# ---------------------------------------------------------------- the handlers
class _Sync(object):
    def __init__(self):
        from Autodesk.Revit import DB
        self.plan_types = (DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan,
                           DB.ViewType.EngineeringPlan, DB.ViewType.AreaPlan)
        self.doc_key = None
        self.corners = None
        self.errors = 0

    def _is_plan(self, view):
        try:
            return view is not None and not view.IsTemplate and view.ViewType in self.plan_types
        except Exception:
            return False

    @staticmethod
    def _key(doc):
        try:
            return doc.PathName or doc.Title
        except Exception:
            return None

    @staticmethod
    def _ui_view(uiapp, view):
        try:
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None:
                return None
            for uv in uidoc.GetOpenUIViews():
                if uv.ViewId == view.Id:
                    return uv
        except Exception:
            pass
        return None

    def activating(self, sender, args):
        """The plan we are LEAVING: remember where it looks."""
        try:
            view = args.CurrentActiveView
            if not self._is_plan(view):
                return
            uv = self._ui_view(sender, view)
            if uv is None:
                return
            c = uv.GetZoomCorners()
            self.corners = (c[0], c[1])
            self.doc_key = self._key(args.Document)
        except Exception as ex:
            self._fail(ex)

    def activated(self, sender, args):
        """The plan we OPEN: same rectangle."""
        try:
            view = args.CurrentActiveView
            if self.corners is None or not self._is_plan(view):
                return
            if self._key(args.Document) != self.doc_key:
                return
            uv = self._ui_view(sender, view)
            if uv is not None:
                uv.ZoomAndCenterRectangle(self.corners[0], self.corners[1])
        except Exception as ex:
            self._fail(ex)

    def _fail(self, ex):
        self.errors += 1
        if self.errors <= 3:
            _log('sync error: %s' % ex)


def _uiapp(uiapp=None):
    if uiapp is not None:
        return uiapp
    try:
        from pyrevit import HOST_APP
        return HOST_APP.uiapp
    except Exception:
        return None


def running():
    try:
        from System import AppDomain
        return AppDomain.CurrentDomain.GetData(APP_KEY) is not None
    except Exception:
        return False


def start(uiapp=None):
    """Hook the view events once per Revit session. Returns True when running."""
    if running():
        return True
    app = _uiapp(uiapp)
    if app is None:
        _log('start failed: no UIApplication')
        return False
    try:
        from System import AppDomain, EventHandler
        from Autodesk.Revit.UI.Events import ViewActivatingEventArgs, ViewActivatedEventArgs
        sync = _Sync()
        h1 = EventHandler[ViewActivatingEventArgs](sync.activating)
        h2 = EventHandler[ViewActivatedEventArgs](sync.activated)
        app.ViewActivating += h1
        app.ViewActivated += h2
        AppDomain.CurrentDomain.SetData(APP_KEY, [h1, h2, sync])
        return True
    except Exception as ex:
        _log('start failed: %s' % ex)
        return False


def stop(uiapp=None):
    try:
        from System import AppDomain
        data = AppDomain.CurrentDomain.GetData(APP_KEY)
        if data is None:
            return
        app = _uiapp(uiapp)
        if app is not None:
            app.ViewActivating -= data[0]
            app.ViewActivated -= data[1]
        AppDomain.CurrentDomain.SetData(APP_KEY, None)
    except Exception as ex:
        _log('stop failed: %s' % ex)


def ensure(uiapp=None):
    """Called at Revit start: hook the events when Sync Views was left ON."""
    if is_enabled():
        start(uiapp)
