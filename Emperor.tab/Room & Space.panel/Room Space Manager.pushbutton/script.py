# -*- coding: ascii -*-
# Emperor BIM Toolkit - Room & Space Manager
# The window is modeless and calls back into Revit through an ExternalEvent,
# so pyRevit must keep this script's engine alive after the script returns.
__persistentengine__ = True

import os
import sys
import traceback

_lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)

try:
    from emperor_rsm import manager
    manager.launch(__revit__)
except Exception:
    from pyrevit import forms
    import emperor_ui
    try:
        from emperor_rsm.theme import log, LOG_PATH
        log('Room & Space Manager failed to start:\n' + traceback.format_exc())
    except Exception:
        LOG_PATH = '(log unavailable)'
    emperor_ui.alert('Room & Space Manager failed to start:\n\n' + traceback.format_exc()
                + '\n\nLog: ' + LOG_PATH, title='Emperor - Room & Space Manager')
