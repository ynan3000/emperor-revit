# -*- coding: ascii -*-
"""Open the Emperor user guide (docs/Emperor_Instructions.html) in the default browser."""
import os

_ext_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
_guide = os.path.join(_ext_root, 'docs', 'Emperor_Instructions.html')

try:
    os.startfile(_guide)
except Exception as ex:
    from pyrevit import forms
    import emperor_ui
    emperor_ui.alert('Could not open the user guide:\n{0}\n\n{1}'.format(_guide, ex),
                title='Emperor - Instructions')
