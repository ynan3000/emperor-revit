# -*- coding: ascii -*-
"""Sync Views - plans keep the same zoom / position (ON / OFF)."""
import os


def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
    """Show the ON / OFF icon when the ribbon loads."""
    try:
        import emperor_sync_views as S
        on = S.is_enabled()
        if on and not S.running():          # make sure it really runs when the ribbon loads
            on = bool(S.start(__rvt__))
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
    import emperor_sync_views as S
    from pyrevit import script

    # decide from what is really running (the saved file can disagree, e.g. when the start at
    # Revit launch did not happen) - one click always flips what the user actually has
    turn_on = not S.running()
    ok = S.start(__revit__) if turn_on else (S.stop(__revit__) or True)
    if turn_on and not ok:
        turn_on = False
        import emperor_ui
        emperor_ui.alert('Sync Views could not start. Details are in %APPDATA%\\Emperor\\sync_views.log',
                         'Emperor - Sync Views', warn=True)
    S.set_enabled(turn_on)
    try:
        script.toggle_icon(turn_on)
    except Exception:
        pass
