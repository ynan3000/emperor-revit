# -*- coding: utf-8 -*-
"""Emperor Claude Connector - runs automatically when Revit / pyRevit loads.

1. starts the local listener the MCP server talks to
2. registers the MCP server with Claude Desktop (in the background, silently)

Any error is written to the pyRevit log and to
%APPDATA%\\Emperor\\claude_connector_error.log instead of breaking pyRevit loading.
"""
import os
import threading
import traceback


def _log_error(where):
    text = traceback.format_exc()
    try:
        from pyrevit import script
        script.get_logger().error("Emperor Claude Connector (%s): %s" % (where, text))
    except Exception:
        pass
    try:
        folder = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Emperor")
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(os.path.join(folder, "claude_connector_error.log"), "ab") as f:
            f.write(("[%s]\n%s\n" % (where, text)).encode("utf-8"))
    except Exception:
        pass


# Shortcut Guard (English keyboard while Revit is in front) - only when the user turned it ON
try:
    import emperor_shortcut_guard
    emperor_shortcut_guard.ensure(globals().get('__revit__'))
except Exception:
    _log_error("shortcut guard")

# Sync Views (plans keep the same zoom / position) - only when the user turned it ON
try:
    import emperor_sync_views
    emperor_sync_views.ensure(globals().get('__revit__'))
except Exception:
    _log_error("sync views")

# red / grey icons of the Toggles panel = what is really running (pyRevit 7 skips __selfinit__)
try:
    import emperor_toggles
    _uiapp = globals().get('__revit__')
    if _uiapp is None:
        try:
            from pyrevit import HOST_APP
            _uiapp = HOST_APP.uiapp
        except Exception:
            _uiapp = None
    emperor_toggles.refresh_icons_when_idle(_uiapp)
except Exception:
    _log_error("toggle icons")

try:
    from emperor_claude import settings, listener, bridge
except Exception:
    _log_error("import")
    settings = listener = bridge = None

if bridge is not None:
    try:
        bridge.remember_server_path()          # the Claude Desktop extension launcher reads it
    except Exception:
        _log_error("server path")

if listener is not None:
    try:
        listener.start()
    except Exception:
        _log_error("listener")


def _message(text, icon):
    import clr
    clr.AddReference("System.Windows.Forms")
    from System.Windows.Forms import MessageBox, MessageBoxButtons
    MessageBox.Show(text, "Emperor - Claude Connector", MessageBoxButtons.OK, icon)


def _auto_register():
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import MessageBoxIcon
        cfg = settings.load()
        if not cfg.get("auto_register", True):
            return
        state, message = bridge.ensure_registered(cfg, restart=cfg.get("auto_restart_claude", True))
        try:                                    # Claude Code: Emperor Revit Skills + the connector
            from emperor_claude import claude_code
            command, lead = bridge.command_for(settings.load())
            if command:
                bridge._log(claude_code.setup(command, list(lead) + [bridge.server_path()]))
        except Exception:
            _log_error("claude code")
        if state == "no_python":
            _message(message, MessageBoxIcon.Warning)
        elif state == "error":
            _message("Emperor could not connect Claude Desktop to Revit:\n\n" + message,
                     MessageBoxIcon.Warning)
        elif state in ("registered", "updated") and "open it again" in message:
            _message("Emperor connected Claude Desktop to Revit.\n\n" + message,
                     MessageBoxIcon.Information)
    except Exception:
        _log_error("auto-register")


if bridge is not None:
    _t = threading.Thread(target=_auto_register)
    _t.daemon = True
    _t.start()
