# -*- coding: ascii -*-
"""Emperor - Shortcut Guard.

Revit keyboard shortcuts work by the LETTER a key types, so with an Arabic (or any non-English) keyboard
layout they do nothing. While Shortcut Guard is ON:
  * when Revit (or one of its windows) is in front, the keyboard switches to English by itself;
  * while you are typing text (a text box, a text note, a parameter value - anything with a text cursor)
    it leaves your language alone, so you can still type Arabic there;
  * when you go to another program, the language you had before comes back.

A small timer on Revit's UI thread checks the front window 4 times a second (almost no CPU).
The ON / OFF choice is kept in %APPDATA%\\Emperor\\shortcut_guard.xml and applied when Revit starts. The running timer is kept in the
AppDomain so the ribbon button (another script engine) can start / stop it.
"""
import os
import json

APP_KEY = 'EmperorShortcutGuard.Timer'
WM_INPUTLANGCHANGEREQUEST = 0x0050
LANG_ENGLISH = 0x09


def _folder():
    folder = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'Emperor')
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return folder


def _settings_path():
    return os.path.join(_folder(), 'shortcut_guard.xml')


def is_enabled():
    """ON / OFF as saved in %APPDATA%\\Emperor\\shortcut_guard.xml  (<ShortcutGuard enabled="true"/>)."""
    try:
        import re
        with open(_settings_path()) as f:
            m = re.search(r'enabled\s*=\s*"([^"]*)"', f.read())
        if m:
            return m.group(1).strip().lower() == 'true'
    except Exception:
        pass
    try:                                    # older builds saved JSON
        with open(os.path.join(_folder(), 'shortcut_guard.json')) as f:
            return bool(json.load(f).get('enabled', False))
    except Exception:
        return False


def set_enabled(value):
    try:
        with open(_settings_path(), 'w') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                    '<!-- Emperor Shortcut Guard: true = keep Revit in English (starts with Revit) -->\n'
                    '<ShortcutGuard enabled="%s"/>\n' % ('true' if value else 'false'))
    except Exception:
        pass
    try:
        os.remove(os.path.join(_folder(), 'shortcut_guard.json'))
    except Exception:
        pass


def _log(text):
    try:
        folder = _folder()
        with open(os.path.join(folder, 'shortcut_guard.log'), 'a') as f:
            f.write(text.rstrip() + '\n')
    except Exception:
        pass


# ---------------------------------------------------------------- Win32
def _wpf_refs():
    """At Revit start (startup.py) the WPF assemblies may not be loaded into the engine yet."""
    try:
        import clr
        for name in ('WindowsBase', 'PresentationCore', 'PresentationFramework'):
            try:
                clr.AddReference(name)
            except Exception:
                pass
    except Exception:
        pass


def _win32():
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                    ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.c_ulong), ('flags', ctypes.c_ulong),
                    ('hwndActive', ctypes.c_void_p), ('hwndFocus', ctypes.c_void_p),
                    ('hwndCapture', ctypes.c_void_p), ('hwndMenuOwner', ctypes.c_void_p),
                    ('hwndMoveSize', ctypes.c_void_p), ('hwndCaret', ctypes.c_void_p),
                    ('rcCaret', RECT)]

    u32.GetForegroundWindow.restype = ctypes.c_void_p
    u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    u32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    u32.GetKeyboardLayout.argtypes = [ctypes.c_ulong]
    u32.GetKeyboardLayout.restype = ctypes.c_void_p
    u32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.c_void_p]
    u32.GetKeyboardLayoutList.restype = ctypes.c_int
    u32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    u32.PostMessageW.restype = ctypes.c_int
    u32.GetGUIThreadInfo.argtypes = [ctypes.c_ulong, ctypes.POINTER(GUITHREADINFO)]
    u32.GetGUIThreadInfo.restype = ctypes.c_int
    u32.LoadKeyboardLayoutW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
    u32.LoadKeyboardLayoutW.restype = ctypes.c_void_p
    return ctypes, u32, GUITHREADINFO


def _process_id(ct=None):
    """Id of this Revit process.

    Not 'from System.Diagnostics import Process' alone: on Revit 2025+ (.NET 8) that class lives in its own
    assembly, which is not loaded yet while Revit starts - the guard then failed to start at launch and only
    worked after a click on the button.
    """
    try:
        k32 = ct.windll.kernel32
        k32.GetCurrentProcessId.restype = ct.c_ulong
        pid = int(k32.GetCurrentProcessId())
        if pid:
            return pid
    except Exception:
        pass
    try:
        pid = int(os.getpid())
        if pid:
            return pid
    except Exception:
        pass
    import clr
    for name in ('System.Diagnostics.Process', 'System'):
        try:
            clr.AddReference(name)
        except Exception:
            pass
    from System.Diagnostics import Process
    return int(Process.GetCurrentProcess().Id)


def _lang(hkl):
    try:
        return int(hkl or 0) & 0x3FF
    except Exception:
        return 0


class Guard(object):
    def __init__(self):
        self.ctypes, self.u32, self.GTI = _win32()
        self.pid = _process_id(self.ctypes)
        self.english = self._english_layout()
        self.in_revit = False
        self.previous = None          # layout to give back when leaving Revit
        self.errors = 0

    def _english_layout(self):
        ct, u32 = self.ctypes, self.u32
        n = u32.GetKeyboardLayoutList(0, None)
        if n > 0:
            arr = (ct.c_void_p * n)()
            u32.GetKeyboardLayoutList(n, ct.cast(arr, ct.c_void_p))
            for h in arr:
                if _lang(h) == LANG_ENGLISH:
                    return int(h)
        h = u32.LoadKeyboardLayoutW(u'00000409', 0)     # US English, not activated
        return int(h or 0x04090409)

    def _typing(self, tid):
        """True when the user is typing text (a text cursor is shown, or a WPF text box has the focus)."""
        info = self.GTI()
        info.cbSize = self.ctypes.sizeof(self.GTI)
        if self.u32.GetGUIThreadInfo(tid, self.ctypes.byref(info)):
            if info.hwndCaret or info.hwndMenuOwner:
                return True
        try:
            from System.Windows.Input import Keyboard
            from System.Windows.Controls.Primitives import TextBoxBase
            from System.Windows.Controls import PasswordBox
            fe = Keyboard.FocusedElement
            if isinstance(fe, (TextBoxBase, PasswordBox)):
                return True
        except Exception:
            pass
        return False

    def tick(self, sender=None, args=None):
        try:
            ct, u32 = self.ctypes, self.u32
            fg = u32.GetForegroundWindow()
            if not fg:
                return
            pid = ct.c_ulong(0)
            tid = u32.GetWindowThreadProcessId(fg, ct.byref(pid))
            if pid.value == self.pid:
                self.in_revit = True
                if self._typing(tid):
                    return
                hkl = u32.GetKeyboardLayout(tid)
                if _lang(hkl) != LANG_ENGLISH:
                    if self.previous is None:
                        self.previous = int(hkl)
                    u32.PostMessageW(fg, WM_INPUTLANGCHANGEREQUEST, None, self.english)
            else:
                if self.in_revit and self.previous is not None:
                    hkl = u32.GetKeyboardLayout(tid)
                    if _lang(hkl) == LANG_ENGLISH:
                        u32.PostMessageW(fg, WM_INPUTLANGCHANGEREQUEST, None, self.previous)
                self.in_revit = False
                self.previous = None
        except Exception as ex:
            self.errors += 1
            if self.errors <= 3:
                _log('tick error: %s' % ex)


# ---------------------------------------------------------------- start / stop
def _timer():
    try:
        from System import AppDomain
        return AppDomain.CurrentDomain.GetData(APP_KEY)
    except Exception:
        return None


def running():
    t = _timer()
    try:
        return t is not None and bool(t.IsEnabled)
    except Exception:
        return False


def start():
    """Start the guard (creates the timer once per Revit session). Returns True when running."""
    t = _timer()
    if t is not None:
        t.Start()
        return True
    try:
        _wpf_refs()
        from System import AppDomain, TimeSpan
        from System.Windows.Threading import DispatcherTimer, DispatcherPriority
        guard = Guard()
        t = DispatcherTimer(DispatcherPriority.Background)
        t.Interval = TimeSpan.FromMilliseconds(250)
        t.Tick += guard.tick
        AppDomain.CurrentDomain.SetData(APP_KEY, t)
        AppDomain.CurrentDomain.SetData(APP_KEY + '.Guard', guard)   # keep the Python side alive
        t.Start()
        return True
    except Exception as ex:
        _log('start failed: %s' % ex)
        return False


def stop():
    t = _timer()
    if t is not None:
        try:
            t.Stop()
        except Exception:
            pass


def ensure(uiapp=None):
    """Called at Revit start: run the guard when it was left ON.

    When it cannot start yet (Revit still loading), it is tried once more the first time Revit is idle.
    """
    if not is_enabled():
        return
    if start() and running():
        return
    if uiapp is None:
        try:
            from pyrevit import HOST_APP
            uiapp = HOST_APP.uiapp
        except Exception:
            uiapp = None
    if uiapp is None:
        return
    try:
        from System import EventHandler, AppDomain
        from Autodesk.Revit.UI.Events import IdlingEventArgs
        key = APP_KEY + '.IdleRetry'
        state = {}

        def once(sender, args):
            try:
                sender.Idling -= state['h']
            except Exception:
                pass
            AppDomain.CurrentDomain.SetData(key, None)
            try:
                if is_enabled() and not running():
                    if start():
                        _log('started on first idle (could not start while Revit was loading)')
                    try:
                        import emperor_toggles
                        emperor_toggles.refresh_icons()
                    except Exception:
                        pass
            except Exception as ex:
                _log('idle retry failed: %s' % ex)
        h = EventHandler[IdlingEventArgs](once)
        state['h'] = h
        AppDomain.CurrentDomain.SetData(key, h)       # keep it alive until it ran
        uiapp.Idling += h
    except Exception as ex:
        _log('idle retry not set: %s' % ex)
