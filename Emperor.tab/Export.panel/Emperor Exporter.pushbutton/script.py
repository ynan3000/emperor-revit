# -*- coding: ascii -*-
# Emperor BIM Toolkit - Emperor Exporter
import os
import sys
import traceback

_lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)

from pyrevit import revit, forms

import emperor_ui

try:
    import emperor_exporter
    emperor_exporter.launch_exporter(revit)
except Exception:
    emperor_ui.alert('Emperor Exporter failed to start:\n\n' + traceback.format_exc(), title='Emperor Exporter')
