# -*- coding: utf-8 -*-
"""Select Revit's Location and Site dialog for Link Manager shared placement.

v1.11 strategy:
- Discover the actual dialog using Win32 EnumWindows/EnumChildWindows first.
- Prefer a real mouse click on the exact UI Automation site row and OK button when UIA exposes them.
- Use native Win32 ListBox selection only when UIA does not expose the row.
- Require a visible prompt that identifies BOTH the expected link and the position dialog.
- Verify the exact site selection after the click and log whether the dialog closed.
- Never click Duplicate, Rename, Delete, or Cancel.

The background worker only interacts with the dialog. It does not call the Revit API.
The Link Manager panel and placement/copy logic are not changed by this helper.

Log: %TEMP%\\LinkManager_dialogs.log, with TMP/temp/current-directory fallbacks.
"""
import os
import time
import traceback
import tempfile
import ctypes
import clr

clr.AddReference("UIAutomationClient")
clr.AddReference("UIAutomationTypes")
clr.AddReference("WindowsBase")
clr.AddReference("PresentationCore")
clr.AddReference("System.Windows.Forms")

from System import IntPtr
from System.Windows import Point
from System.Windows.Forms import Cursor
from System.Windows.Automation import (AutomationElement, PropertyCondition, AndCondition,
                                       TreeScope, ControlType, SelectionItemPattern,
                                       ScrollItemPattern, Condition, TreeWalker,
                                       PropertyConditionFlags)
from System.Diagnostics import Process
from System.Threading import Thread, ThreadStart



def _load_settings():
    """Dialog strings can be changed for another Revit language in lib/linkmgr_settings.json."""
    defaults = {"dialog_titles": ["location and site"],
                "prompt_markers": ["select the position"],
                "ok_labels": ["OK"]}
    try:
        import json
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linkmgr_settings.json")
        with open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8"))
        for key in defaults:
            value = data.get(key)
            if isinstance(value, list) and value:
                defaults[key] = [u"{}".format(v) for v in value]
    except Exception:
        pass
    return defaults


_SETTINGS = _load_settings()
DIALOG_TITLES = [t.lower() for t in _SETTINGS["dialog_titles"]]
PROMPT_MARKERS = [t.lower() for t in _SETTINGS["prompt_markers"]]
OK_LABELS = _SETTINGS["ok_labels"]
DIALOG_TITLE = DIALOG_TITLES[0]


def _title_matches(text):
    t = (text or u"").replace(u"\u00a0", u" ").lower()
    return any(x in t for x in DIALOG_TITLES)


def _has_prompt(text):
    t = (text or u"").replace(u"\u00a0", u" ").lower()
    return any(x in t for x in PROMPT_MARKERS)
_LOG_PATHS = []

# Win32 message constants used only if the dialog exposes a native list box.
LB_GETCOUNT = 0x018B
LB_GETCURSEL = 0x0188
LB_GETTEXT = 0x0189
LB_GETTEXTLEN = 0x018A
LB_SETCURSEL = 0x0186
LB_FINDSTRINGEXACT = 0x01A2
LBN_SELCHANGE = 1
WM_COMMAND = 0x0111
BM_CLICK = 0x00F5
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

# Set up pointer-sized Win32 declarations. If unavailable for any reason, UIA remains
# available as a fallback and the failure is recorded in the diagnostic log.
_USER32 = None
_WIN32_AVAILABLE = False
_WIN32_ERROR = ""
try:
    _USER32 = ctypes.windll.user32
    _WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_ssize_t)
    _USER32.EnumWindows.argtypes = [_WNDENUMPROC, ctypes.c_ssize_t]
    _USER32.EnumWindows.restype = ctypes.c_int
    _USER32.EnumChildWindows.argtypes = [ctypes.c_void_p, _WNDENUMPROC, ctypes.c_ssize_t]
    _USER32.EnumChildWindows.restype = ctypes.c_int
    _USER32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    _USER32.GetWindowTextW.restype = ctypes.c_int
    _USER32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    _USER32.GetClassNameW.restype = ctypes.c_int
    _USER32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    _USER32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    _USER32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _USER32.IsWindowVisible.restype = ctypes.c_int
    _USER32.IsWindowEnabled.argtypes = [ctypes.c_void_p]
    _USER32.IsWindowEnabled.restype = ctypes.c_int
    _USER32.GetDlgCtrlID.argtypes = [ctypes.c_void_p]
    _USER32.GetDlgCtrlID.restype = ctypes.c_int
    _USER32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                     ctypes.c_size_t, ctypes.c_ssize_t]
    _USER32.SendMessageW.restype = ctypes.c_ssize_t
    _USER32.IsWindow.argtypes = [ctypes.c_void_p]
    _USER32.IsWindow.restype = ctypes.c_int
    _USER32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    _USER32.SetCursorPos.restype = ctypes.c_int
    _USER32.mouse_event.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                                    ctypes.c_uint, ctypes.c_size_t]
    _USER32.mouse_event.restype = None
    _WIN32_AVAILABLE = True
except Exception as _win_ex:
    _WIN32_ERROR = str(_win_ex)


def _init_log_paths():
    paths = []
    for raw in (os.environ.get("TEMP"), os.environ.get("TMP"), tempfile.gettempdir()):
        if raw:
            path = os.path.join(raw, "LinkManager_dialogs.log")
            if path.lower() not in [p.lower() for p in paths]:
                paths.append(path)
    return paths


_LOG_PATHS = _init_log_paths()


def _norm(txt):
    return u" ".join((txt or u"").replace(u"\u00a0", u" ").split()).lower()


def _site_key(txt):
    """Normalize a site label, excluding Revit's informational '(in use)' suffix."""
    value = _norm(txt)
    suffix = u" (in use)"
    while value.endswith(suffix):
        value = value[:-len(suffix)].strip()
    return value


def _as_unicode(value):
    try:
        return u"{}".format(value)
    except Exception:
        try:
            return unicode(value)
        except Exception:
            return u"<unprintable value>"


def _log(*lines):
    """Append diagnostics and retain destination failures instead of silently discarding them."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    payload = u"".join(u"{} | {}\r\n".format(stamp, _as_unicode(line)) for line in lines)
    errors = []
    for path in _LOG_PATHS:
        try:
            try:
                if os.path.exists(path) and os.path.getsize(path) > 1024 * 1024:
                    old = path + ".old"
                    if os.path.exists(old):
                        os.remove(old)
                    os.rename(path, old)
            except Exception:
                pass
            folder = os.path.dirname(path)
            if folder and not os.path.isdir(folder):
                os.makedirs(folder)
            with open(path, "ab") as fh:
                fh.write(payload.encode("utf-8", "replace"))
                fh.flush()
            return path
        except Exception as ex:
            errors.append(u"{}: {}".format(path, ex))
    try:
        path = os.path.abspath("LinkManager_dialogs.log")
        with open(path, "ab") as fh:
            fh.write(payload.encode("utf-8", "replace"))
            fh.flush()
        if path.lower() not in [p.lower() for p in _LOG_PATHS]:
            _LOG_PATHS.append(path)
        return path
    except Exception as ex:
        errors.append(u"current directory: {}".format(ex))
    # There is no safe place left to report these errors except debugger output.
    try:
        import System
        System.Diagnostics.Debug.WriteLine("Link Manager SitePicker log failure: " + "; ".join(errors))
    except Exception:
        pass
    return None


def _hval(hwnd):
    try:
        if hasattr(hwnd, "value"):
            return int(hwnd.value or 0)
        return int(hwnd or 0)
    except Exception:
        return 0


def _hptr(hwnd):
    return ctypes.c_void_p(_hval(hwnd))


def _win_text(hwnd):
    if not _WIN32_AVAILABLE or not hwnd:
        return u""
    try:
        buf = ctypes.create_unicode_buffer(2048)
        _USER32.GetWindowTextW(_hptr(hwnd), buf, len(buf))
        return buf.value or u""
    except Exception:
        return u""


def _win_class(hwnd):
    if not _WIN32_AVAILABLE or not hwnd:
        return u""
    try:
        buf = ctypes.create_unicode_buffer(512)
        _USER32.GetClassNameW(_hptr(hwnd), buf, len(buf))
        return buf.value or u""
    except Exception:
        return u""


def _win_pid(hwnd):
    if not _WIN32_AVAILABLE or not hwnd:
        return 0
    try:
        val = ctypes.c_ulong(0)
        _USER32.GetWindowThreadProcessId(_hptr(hwnd), ctypes.byref(val))
        return int(val.value)
    except Exception:
        return 0


def _win_visible(hwnd):
    try:
        return bool(_USER32.IsWindowVisible(_hptr(hwnd)))
    except Exception:
        return False


def _win_enabled(hwnd):
    try:
        return bool(_USER32.IsWindowEnabled(_hptr(hwnd)))
    except Exception:
        return False


def _send(hwnd, message, wparam=0, lparam=0):
    return _USER32.SendMessageW(_hptr(hwnd), int(message), ctypes.c_size_t(int(wparam)),
                                ctypes.c_ssize_t(int(lparam)))


def _enum_windows():
    out = []
    if not _WIN32_AVAILABLE:
        return out

    def callback(hwnd, lparam):
        out.append(_hval(hwnd))
        return 1

    cb = _WNDENUMPROC(callback)
    _USER32.EnumWindows(cb, 0)
    return out


def _enum_children(hwnd):
    out = []
    if not _WIN32_AVAILABLE or not hwnd:
        return out

    def callback(child, lparam):
        out.append(_hval(child))
        return 1

    cb = _WNDENUMPROC(callback)
    _USER32.EnumChildWindows(_hptr(hwnd), cb, 0)
    return out


def _win_desc(hwnd):
    return u"title={!r} class={!r} hwnd={} pid={} visible={} enabled={}".format(
        _win_text(hwnd), _win_class(hwnd), _hval(hwnd), _win_pid(hwnd),
        _win_visible(hwnd), _win_enabled(hwnd))


def _win32_find_dialog(pid):
    """Find visible Location and Site HWNDs, including nested child HWNDs."""
    inventory = []
    if not _WIN32_AVAILABLE:
        return None, [u"Win32 APIs unavailable: {}".format(_WIN32_ERROR)]

    roots = _enum_windows()
    owned_roots = []
    for hwnd in roots:
        if _win_pid(hwnd) != pid:
            continue
        owned_roots.append(hwnd)
        title = _win_text(hwnd)
        inventory.append(_win_desc(hwnd))
        if _win_visible(hwnd) and _title_matches(title):
            return hwnd, inventory

    # EnumWindows normally finds owned modal dialogs. This second pass also handles
    # dialog-like HWNDs hosted as descendants by particular Revit window configurations.
    for root in owned_roots:
        for child in _enum_children(root):
            if _win_pid(child) != pid:
                continue
            title = _win_text(child)
            if title and _title_matches(title):
                inventory.append(u"nested title candidate: " + _win_desc(child))
                if _win_visible(child):
                    return child, inventory
    return None, inventory


def _read_listbox(lb):
    """Return strings from a real Win32/WinForms ListBox HWND, or an empty list."""
    try:
        count = int(_send(lb, LB_GETCOUNT, 0, 0))
        if count < 0 or count > 10000:
            return []
        names = []
        for idx in range(count):
            length = int(_send(lb, LB_GETTEXTLEN, idx, 0))
            if length < 0 or length > 32768:
                names.append(u"")
                continue
            buf = ctypes.create_unicode_buffer(length + 2)
            _send(lb, LB_GETTEXT, idx, ctypes.addressof(buf))
            names.append(buf.value or u"")
        return names
    except Exception as ex:
        _log(u"Win32 listbox read failed | hwnd={} | {}".format(lb, ex), traceback.format_exc())
        return []


def _get_uia_window(hwnd):
    try:
        return AutomationElement.FromHandle(IntPtr(_hval(hwnd)))
    except Exception as ex:
        _log(u"AutomationElement.FromHandle failed for hwnd {}: {}".format(hwnd, ex),
             traceback.format_exc())
        return None


_log(u"=== Link Manager SitePicker v1.11 (physical mouse + UIA) imported ===",
     u"process id={}".format(Process.GetCurrentProcess().Id),
     u"log candidates={}".format(u"; ".join(_LOG_PATHS)),
     u"Win32 API available={}{}".format(_WIN32_AVAILABLE,
         u"; error=" + _WIN32_ERROR if _WIN32_ERROR else u""))


class SitePicker(object):
    """Use as a context manager around RevitLinkInstance.Create(..., Shared)."""
    _last_thread = None

    def __init__(self, site, link_file):
        self.site = (site or u"").strip()
        self.link_file = (link_file or u"").strip()
        self.result = u""
        self._stop = False
        self._thread = None
        self._started_at = None
        self._dialog_hwnd = 0

    def __enter__(self):
        self._started_at = time.time()
        _log(u"picker enter | link={!r} | wanted site={!r}".format(self.link_file, self.site),
             u"thread starting | main thread id={}".format(Thread.CurrentThread.ManagedThreadId))
        if not self.site:
            self.result = u"no named site was specified; automatic selection skipped"
            _log(self.result)
            return self
        try:
            prior = SitePicker._last_thread
            if prior is not None and prior.IsAlive:
                try:
                    prior.Join(250)
                except Exception:
                    pass
                if prior.IsAlive:
                    self.result = u"previous picker worker is still active; automatic selection skipped"
                    _log(self.result)
                    return self
            self._thread = Thread(ThreadStart(self._run))
            self._thread.IsBackground = True
            self._thread.Name = "LinkManager SitePicker Win32/UIA worker"
            self._thread.Start()
            SitePicker._last_thread = self._thread
            _log(u"worker started | alive={} | thread name={!r}".format(
                self._thread.IsAlive, self._thread.Name))
        except Exception as ex:
            self.result = u"worker failed to start: {}".format(ex)
            _log(self.result, traceback.format_exc())
        return self

    def __exit__(self, exc_type, exc, tb):
        alive_before = bool(self._thread and self._thread.IsAlive)
        _log(u"picker exit requested | elapsed={:.3f}s | worker alive before stop={} | result={!r}".format(
            (time.time() - self._started_at) if self._started_at else -1, alive_before, self.result),
            u"placement exception type={} | value={!r}".format(
                getattr(exc_type, "__name__", None), exc))
        # If an automated OK just closed the modal dialog, allow the worker to record its
        # successful result before asking it to stop. Without this small grace period, Revit's
        # Create call and the worker can resume at nearly the same time and lose the success note.
        if self._thread is not None and self._thread.IsAlive:
            try:
                self._thread.Join(200)
            except Exception as ex:
                _log(u"worker completion grace wait raised: {}".format(ex), traceback.format_exc())
        alive_after_grace = bool(self._thread and self._thread.IsAlive)
        if alive_after_grace:
            self._stop = True
            try:
                self._thread.Join(1000)
            except Exception as ex:
                _log(u"worker join raised: {}".format(ex), traceback.format_exc())
        alive_after = bool(self._thread and self._thread.IsAlive)
        _log(u"worker stop requested | alive before={} | alive after bounded join={}".format(
            alive_before, alive_after))
        return False

    def _element_details(self, element):
        try:
            c = element.Current
            return u"name={!r} | type={} | class={!r} | id={!r} | hwnd={} | pid={}".format(
                c.Name, c.ControlType.ProgrammaticName, c.ClassName, c.AutomationId,
                c.NativeWindowHandle, c.ProcessId)
        except Exception as ex:
            return u"<element details failed: {}>".format(ex)

    def _point_in_dialog(self, x, y):
        """True only when the screen point belongs to the dialog being automated."""
        dlg = self._dialog_hwnd
        if not dlg:
            return False
        try:
            cur = AutomationElement.FromPoint(Point(float(x), float(y)))
            walker = TreeWalker.ControlViewWalker
            for _ in range(20):
                if cur is None:
                    break
                try:
                    if int(cur.Current.NativeWindowHandle) == int(dlg):
                        return True
                except Exception:
                    pass
                cur = walker.GetParent(cur)
        except Exception as ex:
            _log(u"point-in-dialog check failed: {}".format(ex))
        return False

    def _physical_click(self, element, description):
        """Use an actual desktop mouse click so Revit receives the same input as a user.

        UIA SelectionItemPattern.Select() can report IsSelected=True without proving that
        Revit's modal placement dialog processed the same user interaction. This helper
        scrolls the control into view and physically clicks a verified clickable point.
        It fails closed if a safe screen point is not available.
        """
        if not _WIN32_AVAILABLE:
            _log(u"physical click unavailable for {}: Win32 mouse API unavailable".format(description))
            return False
        try:
            try:
                scroll = element.GetCurrentPattern(ScrollItemPattern.Pattern)
                scroll.ScrollIntoView()
                Thread.Sleep(100)
            except Exception:
                pass
            try:
                element.SetFocus()
            except Exception:
                pass
            point = element.GetClickablePoint()
            x = int(round(point.X))
            y = int(round(point.Y))
            # Negative screen coordinates are valid when Revit is on a monitor left/above
            # the primary display, so do not reject them.
            # Safety: never click a point that is not inside the dialog being automated
            # (another window on top, a scaling mismatch, a moved dialog...). The dialog is
            # then left for the user.
            if not self._point_in_dialog(x, y):
                _log(u"physical click refused for {}: point ({}, {}) is not inside dialog hwnd={}".format(
                    description, x, y, self._dialog_hwnd))
                return False
            try:
                saved_cursor = Cursor.Position
            except Exception:
                saved_cursor = None
            moved = bool(_USER32.SetCursorPos(x, y))
            if not moved:
                _log(u"physical click refused for {}: SetCursorPos failed at ({}, {})".format(
                    description, x, y))
                return False
            Thread.Sleep(60)
            _USER32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            Thread.Sleep(45)
            _USER32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            Thread.Sleep(180)
            if saved_cursor is not None:
                try:
                    Cursor.Position = saved_cursor      # give the mouse back to the user
                except Exception:
                    pass
            _log(u"physical mouse click sent | control={} | point=({}, {}) | cursor_moved={}".format(
                description, x, y, moved))
            return True
        except Exception as ex:
            _log(u"physical click failed for {}: {}".format(description, ex), traceback.format_exc())
            return False

    def _wait_for_dialog_close(self, hwnd, timeout_ms=1800):
        """Wait for the exact placement dialog window to disappear after a real OK click."""
        if not hwnd:
            _log(u"dialog close could not be verified because the dialog HWND was unavailable")
            return False
        elapsed = 0
        while elapsed < timeout_ms:
            try:
                if not _USER32.IsWindow(_hptr(hwnd)) or not _USER32.IsWindowVisible(_hptr(hwnd)):
                    _log(u"dialog close verified after {} ms".format(elapsed))
                    return True
            except Exception:
                pass
            Thread.Sleep(60)
            elapsed += 60
        _log(u"dialog window was still present after {} ms following OK click | hwnd={}".format(
            timeout_ms, hwnd))
        return False

    def _find_uia_window(self, pid):
        wins = AutomationElement.RootElement.FindAll(
            TreeScope.Children,
            PropertyCondition(AutomationElement.ProcessIdProperty, pid))
        names = []
        for i in range(wins.Count):
            w = wins[i]
            nm = w.Current.Name or u""
            names.append(u"{} [class={!r}, hwnd={}, pid={}]".format(
                nm, w.Current.ClassName, w.Current.NativeWindowHandle, w.Current.ProcessId))
            if _title_matches(nm):
                _log(u"UIA root window match at index {}: {}".format(i, self._element_details(w)))
                return w, names
        # Search below main/owned UIA roots as a compatibility fallback.
        title_conds = [PropertyCondition(AutomationElement.NameProperty, t,
                                        PropertyConditionFlags.IgnoreCase)
                       for t in _SETTINGS["dialog_titles"]]
        for i in range(wins.Count):
            try:
                hit = None
                for title_cond in title_conds:
                    hit = wins[i].FindFirst(TreeScope.Descendants, title_cond)
                    if hit is not None:
                        break
                if hit is not None:
                    _log(u"UIA descendant window match below root {}: {}".format(
                        i, self._element_details(hit)))
                    return hit, names
            except Exception as ex:
                _log(u"UIA descendant search failed at index {}: {}".format(i, ex))
        return None, names

    def _run(self):
        try:
            pid = Process.GetCurrentProcess().Id
            started = time.time()
            last_poll_log = 0.0
            _log(u"worker running | pid={} | thread id={} | site={!r} | link={!r}".format(
                pid, Thread.CurrentThread.ManagedThreadId, self.site, self.link_file))
            while not self._stop and time.time() - started < 60:
                elapsed = time.time() - started
                hwnd = None
                inventory = []
                try:
                    hwnd, inventory = _win32_find_dialog(pid)
                except Exception as ex:
                    _log(u"Win32 window discovery exception at {:.2f}s: {}".format(elapsed, ex),
                         traceback.format_exc())
                if hwnd is not None:
                    _log(u"Win32 dialog found after {:.3f}s | {}".format(
                        time.time() - started, _win_desc(hwnd)))
                    self._dialog_hwnd = _hval(hwnd)
                    self._handle_win32(hwnd, pid)
                    _log(u"Win32 handler returned | result={!r} | stop={}".format(self.result, self._stop))
                    return

                # UIA fallback handles dialogs that have no usable native ListBox HWND.
                try:
                    win, uia_names = self._find_uia_window(pid)
                except Exception as ex:
                    _log(u"UIA discovery exception at {:.2f}s: {}".format(elapsed, ex),
                         traceback.format_exc())
                    win, uia_names = None, []
                if win is not None:
                    _log(u"UIA dialog found after {:.3f}s | {}".format(
                        time.time() - started, self._element_details(win)))
                    try:
                        self._dialog_hwnd = int(win.Current.NativeWindowHandle)
                    except Exception:
                        self._dialog_hwnd = 0
                    self._handle(win)
                    _log(u"UIA handler returned | result={!r} | stop={}".format(self.result, self._stop))
                    return

                if elapsed - last_poll_log >= 1.0:
                    last_poll_log = elapsed
                    _log(u"poll {:.1f}s | stop={} | Win32 windows={} | Win32 available={} | UIA roots={}".format(
                        elapsed, self._stop, inventory[:30], _WIN32_AVAILABLE, uia_names[:30]))
                Thread.Sleep(100)
            if self._stop:
                _log(u"worker stopped before finding dialog | elapsed={:.3f}s".format(time.time() - started))
            else:
                self.result = u"dialog not found within 60 seconds"
                _log(self.result, u"last poll elapsed={:.3f}s".format(time.time() - started))
        except Exception as ex:
            self.result = u"automation error: {}".format(ex)
            _log(self.result, traceback.format_exc())

    def _hwnd_dialog_text(self, hwnd):
        handles = [hwnd] + _enum_children(hwnd)
        vals = []
        for child in handles:
            txt = _win_text(child)
            if txt and txt.strip():
                vals.append(txt.strip())
        return vals

    def _uia_dialog_text(self, win):
        vals = []
        try:
            els = win.FindAll(TreeScope.Descendants, Condition.TrueCondition)
            for i in range(min(els.Count, 500)):
                try:
                    txt = els[i].Current.Name
                    if txt and txt.strip():
                        vals.append(txt.strip())
                except Exception:
                    pass
        except Exception as ex:
            _log(u"UIA dialog text read failed: {}".format(ex))
        return vals

    def _verify_dialog_identity(self, hwnd, uia_win=None):
        """Fail closed unless dialog text identifies this exact link's position picker."""
        texts = self._hwnd_dialog_text(hwnd)
        joined = u" | ".join(texts)
        prompt_found = _has_prompt(joined)
        if not prompt_found and uia_win is not None:
            uia_texts = self._uia_dialog_text(uia_win)
            texts.extend(uia_texts)
            joined = u" | ".join(texts)
            prompt_found = _has_prompt(joined)
        else:
            uia_texts = []
        link_found = bool(self.link_file and _norm(self.link_file) in _norm(joined))
        _log(u"dialog identity check | title={!r} | pid={} | prompt_found={} | link_found={} | "
             u"expected_link={!r} | visible texts={!r}".format(
                 _win_text(hwnd), _win_pid(hwnd), prompt_found, link_found, self.link_file, texts[:80]))
        if not prompt_found:
            self.result = u"position prompt text not exposed; dialog left untouched"
            _log(self.result)
            return False
        if not link_found:
            self.result = u"dialog does not identify expected link '{}'; dialog left untouched".format(
                self.link_file)
            _log(self.result)
            return False
        return True

    def _button_hwnd(self, hwnd, wanted):
        wanted_norms = [_norm(w) for w in (wanted if isinstance(wanted, (list, tuple)) else [wanted])]
        for child in _enum_children(hwnd):
            cls = _win_class(child).lower()
            label = _norm(_win_text(child))
            if label in wanted_norms and (cls == u"button" or u".button." in cls or cls.endswith(u"button")):
                return child
        return None

    def _press_ok_win32_or_uia(self, hwnd, uia_win):
        if self._stop:
            self.result = u"stop flag set before OK; dialog left open"
            _log(self.result)
            return False
        ok_hwnd = self._button_hwnd(hwnd, OK_LABELS)
        if ok_hwnd is not None and not _win_enabled(ok_hwnd):
            self.result = u"native OK button is disabled; dialog left open"
            _log(self.result)
            return False
        _log(u"attempting a physical click on the exact OK control")
        if uia_win is not None:
            try:
                ok = self._ok_button(uia_win)
                if ok is not None and ok.Current.IsEnabled:
                    _log(u"physically clicking UIA OK button | {}".format(self._element_details(ok)))
                    if self._physical_click(ok, u"exact OK button"):
                        self.result = u"selected '{}' and physically clicked OK via UIA".format(self.site)
                        return True
            except Exception as ex:
                _log(u"physical UIA OK click failed: {}".format(ex), traceback.format_exc())
        self.result = u"site selected and verified, but OK could not be physically clicked; dialog left open"
        _log(self.result)
        return False

    def _handle_win32(self, hwnd, pid):
        """Safely operate a real Windows list box when Revit exposes one."""
        try:
            if self._stop:
                self.result = u"stop flag already set; no action taken"
                _log(self.result)
                return
            if _win_pid(hwnd) != pid or not _win_visible(hwnd):
                self.result = u"candidate dialog is not a visible window owned by Revit; no action taken"
                _log(self.result)
                return
            uia_win = _get_uia_window(hwnd)
            if not self._verify_dialog_identity(hwnd, uia_win):
                self._dump_hwnd(hwnd)
                return

            # Prefer a physical click on the exact UIA row whenever it is exposed, even if
            # a top-level Win32 dialog HWND was discovered. Fall back to ListBox messages
            # only when the UIA row is not available.
            if uia_win is not None:
                try:
                    uia_items = uia_win.FindAll(TreeScope.Descendants, PropertyCondition(
                        AutomationElement.ControlTypeProperty, ControlType.ListItem))
                    for ui_index in range(uia_items.Count):
                        if _site_key(uia_items[ui_index].Current.Name) == _site_key(self.site):
                            self._handle(uia_win)
                            return
                except Exception as ex:
                    _log(u"preference check for physical UIA row click failed: {}".format(ex),
                         traceback.format_exc())

            controls = _enum_children(hwnd)
            listboxes = []
            for child in controls:
                cls = _win_class(child).lower()
                if cls == u"listbox" or u"listbox" in cls:
                    values = _read_listbox(child)
                    listboxes.append((child, cls, values))
            _log(u"native list box inventory | count={} | detail={!r}".format(
                len(listboxes), [(h, cls, vals) for h, cls, vals in listboxes]))

            wanted = _norm(self.site)
            chosen = None
            chosen_items = None
            target_index = -1
            for lb, cls, values in listboxes:
                for idx, value in enumerate(values):
                    if _site_key(value) == _site_key(self.site):
                        chosen = lb
                        chosen_items = values
                        target_index = idx
                        break
                if chosen is not None:
                    break

            if chosen is not None:
                # LB_FINDSTRINGEXACT is recorded as an independent cross-check. Selection
                # is based on an enumerated exact normalized match, not a partial match.
                query = ctypes.create_unicode_buffer(self.site)
                find_index = int(_send(chosen, LB_FINDSTRINGEXACT, -1, ctypes.addressof(query)))
                _log(u"site exact match | site={!r} | enumerated_index={} | LB_FINDSTRINGEXACT={} | "
                     u"listbox={} | all_items={!r}".format(
                         self.site, target_index, find_index, chosen, chosen_items))
                if self._stop:
                    self.result = u"stop flag set before list selection; dialog left open"
                    _log(self.result)
                    return
                _send(chosen, LB_SETCURSEL, target_index, 0)
                Thread.Sleep(80)
                selected_idx = int(_send(chosen, LB_GETCURSEL, 0, 0))
                selected_text = u""
                if 0 <= selected_idx < len(chosen_items):
                    selected_text = chosen_items[selected_idx]
                # Confirm by reading selection from the HWND again, not just cached data.
                selected_len = int(_send(chosen, LB_GETTEXTLEN, selected_idx, 0)) if selected_idx >= 0 else -1
                if selected_idx >= 0 and selected_len >= 0 and selected_len < 32768:
                    selected_buf = ctypes.create_unicode_buffer(selected_len + 2)
                    _send(chosen, LB_GETTEXT, selected_idx, ctypes.addressof(selected_buf))
                    selected_text = selected_buf.value or u""
                _log(u"native selection verification | selected_index={} | selected_text={!r} | "
                     u"expected={!r}".format(selected_idx, selected_text, self.site))
                if selected_idx != target_index or _site_key(selected_text) != _site_key(self.site):
                    self.result = u"native site selection could not be verified; dialog left open"
                    _log(self.result)
                    self._dump_hwnd(hwnd)
                    return

                # Notify the owning dialog as a real listbox selection change. Do not send
                # commands for any controls other than the verified position list.
                try:
                    control_id = int(_USER32.GetDlgCtrlID(_hptr(chosen)))
                    if control_id:
                        command = ((LBN_SELCHANGE & 0xffff) << 16) | (control_id & 0xffff)
                        _send(hwnd, WM_COMMAND, command, _hval(chosen))
                        Thread.Sleep(40)
                        now_idx = int(_send(chosen, LB_GETCURSEL, 0, 0))
                        _log(u"sent LBN_SELCHANGE | listbox={} | control id={} | selected index now={}".format(
                            chosen, control_id, now_idx))
                        if now_idx != target_index:
                            self.result = u"selection changed unexpectedly after notification; OK not pressed"
                            _log(self.result)
                            return
                except Exception as ex:
                    _log(u"LBN_SELCHANGE notification failed (selection remains verified): {}".format(ex),
                         traceback.format_exc())
                self._press_ok_win32_or_uia(hwnd, uia_win)
                return

            _log(u"no exact native ListBox item found for {!r}; try UIA control tree".format(self.site))
            if uia_win is not None:
                self._handle(uia_win)
                return
            self.result = u"native position list unavailable; dialog left open for manual selection"
            _log(self.result)
            self._dump_hwnd(hwnd)
        except Exception as ex:
            self.result = u"Win32 dialog automation error: {}".format(ex)
            _log(self.result, traceback.format_exc())
            try:
                self._dump_hwnd(hwnd)
            except Exception:
                pass

    def _ok_button(self, win):
        for label in OK_LABELS:
            btn = self._button(win, label)
            if btn is not None:
                return btn
        return None

    def _button(self, win, name):
        cond = AndCondition(
            PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Button),
            PropertyCondition(AutomationElement.NameProperty, name))
        return win.FindFirst(TreeScope.Descendants, cond)

    def _dump(self, win):
        lines = [u"UIA dialog structure dump begin"]
        try:
            lines.append(u"dialog root: {}".format(self._element_details(win)))
            els = win.FindAll(TreeScope.Descendants, Condition.TrueCondition)
            lines.append(u"descendant count={}".format(els.Count))
            for i in range(min(els.Count, 500)):
                lines.append(u"  [{}] {}".format(i, self._element_details(els[i])))
        except Exception as ex:
            lines.append(u"enumeration failed: {}".format(ex))
            lines.append(traceback.format_exc())
        lines.append(u"UIA dialog structure dump end")
        _log(*lines)

    def _dump_hwnd(self, hwnd):
        lines = [u"Win32 dialog structure dump begin", _win_desc(hwnd)]
        try:
            children = _enum_children(hwnd)
            lines.append(u"descendant HWND count={}".format(len(children)))
            for i, child in enumerate(children[:500]):
                lines.append(u"  [{}] {}".format(i, _win_desc(child)))
        except Exception as ex:
            lines.append(u"Win32 enumeration failed: {}".format(ex))
            lines.append(traceback.format_exc())
        lines.append(u"Win32 dialog structure dump end")
        _log(*lines)
        uia_win = _get_uia_window(hwnd)
        if uia_win is not None:
            self._dump(uia_win)

    def _handle(self, win):
        """UI Automation fallback. It also fails closed unless prompt identity is verified."""
        try:
            _log(u"UIA handler started | stop={} | wanted site={!r} | expected link={!r} | root={}".format(
                self._stop, self.site, self.link_file, self._element_details(win)))
            if self._stop:
                self.result = u"stop flag already set; no action taken"
                _log(self.result)
                return

            texts = win.FindAll(TreeScope.Descendants, PropertyCondition(
                AutomationElement.ControlTypeProperty, ControlType.Text))
            prompts = [texts[i].Current.Name for i in range(texts.Count)
                       if _has_prompt(texts[i].Current.Name)]
            all_text = [texts[i].Current.Name for i in range(texts.Count)
                        if texts[i].Current.Name]
            joined = u" | ".join(all_text)
            prompt_found = _has_prompt(joined)
            link_found = bool(self.link_file and _norm(self.link_file) in _norm(joined))
            _log(u"UIA identity check | matching prompts={!r} | prompt_found={} | link_found={} | "
                 u"all text={!r}".format(prompts, prompt_found, link_found, all_text[:100]))
            if not prompt_found or not link_found:
                self.result = u"UIA prompt/link identity could not be verified; dialog left untouched"
                _log(self.result)
                self._dump(win)
                return

            items = win.FindAll(TreeScope.Descendants, PropertyCondition(
                AutomationElement.ControlTypeProperty, ControlType.ListItem))
            names = [items[i].Current.Name for i in range(items.Count)]
            _log(u"UIA ListItem count={} | all names={!r}".format(items.Count, names))
            target = None
            target_index = -1
            for i in range(items.Count):
                if _site_key(names[i]) == _site_key(self.site):
                    target = items[i]
                    target_index = i
                    break
            if target is None:
                self.result = u"site '{}' not in UIA list: dialog left open".format(self.site)
                _log(self.result)
                self._dump(win)
                return
            if self._stop:
                self.result = u"stop flag set before selection; no action taken"
                _log(self.result)
                return

            _log(u"attempting physical click on exact UIA site item | index={} | site={!r} | element={}".format(
                target_index, names[target_index], self._element_details(target)))
            # Do not rely only on SelectionItemPattern.Select(): the previous build reported
            # success but the resulting link did not retain the shared-position association.
            if not self._physical_click(target, u"site item '{}'".format(names[target_index])):
                self.result = u"site item could not be physically clicked safely; dialog left open"
                _log(self.result)
                self._dump(win)
                return
            try:
                sel = target.GetCurrentPattern(SelectionItemPattern.Pattern)
                Thread.Sleep(120)
                selected = bool(sel.Current.IsSelected)
                selected_name = target.Current.Name or u""
            except Exception as ex:
                self.result = u"site click sent but selection could not be verified; dialog left open: {}".format(ex)
                _log(self.result, traceback.format_exc())
                self._dump(win)
                return
            _log(u"post-click site selection verification | IsSelected={} | selected_name={!r} | expected={!r}".format(
                selected, selected_name, self.site))
            if not selected or _site_key(selected_name) != _site_key(self.site):
                self.result = u"physical click did not select the exact requested site; OK not pressed"
                _log(self.result)
                self._dump(win)
                return
            if self._stop:
                self.result = u"stop flag set after selection; OK not pressed"
                _log(self.result)
                return

            ok = self._ok_button(win)
            if ok is None:
                self.result = u"UIA OK button not found; selected site left for manual confirmation"
                _log(self.result)
                self._dump(win)
                return
            if not ok.Current.IsEnabled:
                self.result = u"UIA OK button is disabled; dialog left open"
                _log(self.result)
                return
            _log(u"physically clicking exact UIA OK button | {}".format(self._element_details(ok)))
            dialog_hwnd = 0
            try:
                dialog_hwnd = int(win.Current.NativeWindowHandle)
            except Exception:
                dialog_hwnd = 0
            if not self._physical_click(ok, u"exact OK button"):
                self.result = u"site selected and verified, but OK could not be physically clicked; dialog left open"
                _log(self.result)
                return
            closed = self._wait_for_dialog_close(dialog_hwnd)
            if closed:
                self.result = u"physically selected '{}' and clicked OK; dialog close verified".format(self.site)
            else:
                self.result = u"physically selected '{}' and clicked OK, but dialog close was not verified".format(
                    self.site)
            _log(self.result)
        except Exception as ex:
            self.result = u"UIA automation error: {}".format(ex)
            _log(self.result, traceback.format_exc())
            try:
                self._dump(win)
            except Exception as dump_ex:
                _log(u"UIA dump after exception also failed: {}".format(dump_ex), traceback.format_exc())
