# -*- coding: ascii -*-
"""Ribbon icons of the Toggles panel (Shortcut Guard, Sync Views).

pyRevit 7 builds the ribbon in its C# loader and no longer runs a button's __selfinit__, so the icons
are set from startup.py: right away, and once more on the first Idling event (when the ribbon is
certainly built). The icon always shows what is really RUNNING (red = on, grey = off).
"""
import os

PANEL = 'Toggles'
TAB = 'Emperor'


def _panel_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), 'Emperor.tab', 'Toggles.panel')


def _states():
    out = {}
    try:
        import emperor_shortcut_guard as G
        out['Shortcut Guard'] = G.running()
    except Exception:
        pass
    try:
        import emperor_sync_views as S
        out['Sync Views'] = S.running()
    except Exception:
        pass
    return out


def refresh_icons():
    """Set the red / grey icon of every toggle. Returns the number of buttons updated."""
    from pyrevit.coreutils import ribbon
    states = _states()
    done = 0
    tab = ribbon.get_current_ui().ribbon_tab(TAB)
    for pnl in tab:
        if pnl.name != PANEL:
            continue
        for b in pnl:
            if b.name not in states:
                continue
            icon = os.path.join(_panel_dir(), b.name + '.pushbutton', 'on.png' if states[b.name] else 'off.png')
            try:
                b.set_icon(icon, icon_size=ribbon.ICON_LARGE)
                done += 1
            except Exception:
                pass
    return done


def refresh_icons_when_idle(uiapp):
    """Refresh now (if the ribbon exists) and once more when Revit is first idle."""
    try:
        refresh_icons()
    except Exception:
        pass
    if uiapp is None:
        return
    try:
        from System import EventHandler, AppDomain
        from Autodesk.Revit.UI.Events import IdlingEventArgs
        key = 'EmperorToggles.IdleIcons'
        state = {}

        def once(sender, args):
            try:
                sender.Idling -= state['h']
            except Exception:
                pass
            AppDomain.CurrentDomain.SetData(key, None)
            try:
                refresh_icons()
            except Exception:
                pass
        h = EventHandler[IdlingEventArgs](once)
        state['h'] = h
        AppDomain.CurrentDomain.SetData(key, h)       # keep it alive until it ran
        uiapp.Idling += h
    except Exception:
        pass
