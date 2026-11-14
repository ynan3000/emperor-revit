# -*- coding: ascii -*-
"""Shortcut Guard - English keyboard while Revit is in front (ON / OFF)."""
import os


def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
    """Show the ON / OFF icon when the ribbon loads."""
    try:
        import emperor_shortcut_guard as G
        on = G.is_enabled()
        if on and not G.running():          # make sure it really runs when the ribbon loads
            on = bool(G.start())
        icon = os.path.join(script_cmp.directory, 'on.png' if on else 'off.png')
        try:
            from pyrevit.coreutils.ribbon import ICON_LARGE
            ui_button_cmp.set_icon(icon, icon_size=ICON_LARGE)
        except Exception:
            ui_button_cmp.set_icon(icon)
    except Exception:
        pass
    return True


if __name__ == '__main__':
    import emperor_shortcut_guard as G
    from pyrevit import script

    # decide from what is really running (the saved file can disagree, e.g. when the start at
    # Revit launch did not happen) - one click always flips what the user actually has
    turn_on = not G.running()
    ok = G.start() if turn_on else (G.stop() or True)
    if turn_on and not ok:
        turn_on = False
        import emperor_ui
        emperor_ui.alert('Shortcut Guard could not start on this PC. Details are in '
                         '%APPDATA%\\Emperor\\shortcut_guard.log', 'Emperor - Shortcut Guard', warn=True)
    G.set_enabled(turn_on)
    try:
        script.toggle_icon(turn_on)
    except Exception:
        pass
