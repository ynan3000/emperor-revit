# -*- coding: utf-8 -*-

import os

from pyrevit import forms
from System.Windows import Clipboard
from System.Windows.Media import BrushConverter

from emperor_claude import settings, bridge
import emperor_ui

PROFILES = ["all", "modeling", "read"]
_conv = BrushConverter()
OK = _conv.ConvertFromString("#2E7D32")
BAD = _conv.ConvertFromString("#9E9E9E")
WARN = _conv.ConvertFromString("#E65100")


class ConnectorWindow(forms.WPFWindow):
    def __init__(self):
        xaml = os.path.join(os.path.dirname(__file__), "ConnectorWindow.xaml")
        with open(xaml, "rb") as f:
            text = f.read().decode("utf-8")
        forms.WPFWindow.__init__(self, emperor_ui.inject(text), literal_string=True)
        emperor_ui.enable_mouse_glow(self)
        self._loading = True
        self.refresh()
        self._loading = False

    def _show(self, dot, label, brush, text):
        dot.Fill = brush
        label.Text = text

    def refresh(self):
        cfg = settings.load()

        port = bridge.listener_port()
        if port:
            self._show(self.dot_routes, self.txt_routes, OK,
                       "Revit bridge is running (port %s)." % port)
        else:
            self._show(self.dot_routes, self.txt_routes, BAD,
                       "Revit bridge is not running. Reload pyRevit; if it stays off, "
                       "another program may be using ports 48890-48899.")

        exe = cfg.get("python_exe")
        private = bridge.private_exe()
        if private:
            self._show(self.dot_python, self.txt_python, OK,
                       "Emperor's own Python is ready - nothing to install (official python.org build).")
        elif cfg.get("launcher") == "py":
            self._show(self.dot_python, self.txt_python, OK,
                       "Python 3 found - Claude Desktop starts the connector with: py -3")
        elif exe and os.path.isfile(exe):
            self._show(self.dot_python, self.txt_python, OK, "Python 3 found: %s" % exe)
        else:
            self._show(self.dot_python, self.txt_python, BAD,
                       "Python 3 not detected yet - it is searched for when you press Reconnect.")

        if os.path.isfile(bridge.server_path()):
            self._show(self.dot_server, self.txt_server, OK, "MCP server file found.")
        else:
            self._show(self.dot_server, self.txt_server, BAD,
                       "MCP server file missing: %s" % bridge.server_path())

        registered, detail = bridge.is_registered(cfg)
        self._show(self.dot_claude, self.txt_claude, OK if registered else BAD, detail + ".")

        if cfg.get("allow_write"):
            self._show(self.dot_write, self.txt_write, WARN,
                       "Write access ON - Claude can change parameters and export files "
                       "(each change is one undo step).")
            self.btn_write.Content = "Turn write access OFF"
        else:
            self._show(self.dot_write, self.txt_write, OK,
                       "Read-only - Claude can look at the model but not change it.")
            self.btn_write.Content = "Turn write access ON"

        if cfg.get("allow_scripts"):
            self._show(self.dot_script, self.txt_script, WARN,
                       "Scripting ON - Claude can run its own code inside Revit.")
            self.btn_script.Content = "Turn scripting access OFF"
        else:
            self._show(self.dot_script, self.txt_script, OK,
                       "Scripting OFF - Claude can only use the built-in tools.")
            self.btn_script.Content = "Turn scripting access ON"

        self.chk_auto.IsChecked = bool(cfg.get("auto_register", True))
        self.cb_profile.SelectedIndex = PROFILES.index(cfg.get("tool_profile", "all")) \
            if cfg.get("tool_profile", "all") in PROFILES else 0
        self.txt_next.Text = ("Normally nothing to do here: at Revit start Emperor adds the connector "
                              "to Claude Desktop and restarts Claude Desktop by itself. If Claude "
                              "does not see Revit, press Reconnect (it also restarts Claude Desktop), "
                              "then ask Claude: \"Check the Revit connection\".")

    # ---------------------------------------------------------------- events
    def on_connect(self, sender, args):
        state, message = bridge.ensure_registered(settings.load(), force=True, restart=True)
        emperor_ui.alert(message, title="Claude Connector")
        self.refresh()

    def on_install_ext(self, sender, args):
        path = bridge.mcpb_path()
        if not os.path.isfile(path):
            emperor_ui.alert("The extension file is missing:\n%s" % path, title="Claude Connector", warn=True)
            return
        if bridge.desktop_extension_installed():
            state, message = bridge.ensure_registered(settings.load(), restart=True)
            emperor_ui.alert("The Emperor Revit extension is already installed in Claude Desktop.\n\n" + message,
                             title="Claude Connector")
            self.refresh()
            return
        bridge.remember_server_path()
        try:
            from emperor_claude import private_python
            private_python.ensure(download=True)
        except Exception:
            pass
        # .mcpb files are often not linked to Claude Desktop (Store version): show the file and let the
        # user drag it into the Claude Desktop window, which always works.
        import subprocess
        try:
            subprocess.Popen('explorer /select,"%s"' % path)
        except Exception:
            os.startfile(os.path.dirname(path))
        emperor_ui.alert("A folder opens with Emperor Revit.mcpb selected.\n\n"
                         "1. Drag Emperor Revit.mcpb onto the Claude Desktop window - its install window opens - press Install.\n"
                         "   (Or in Claude Desktop: Settings > Extensions > Advanced settings > Install Extension... and pick the file.)\n"
                         "2. Come back and press Reconnect + restart Claude Desktop: Emperor removes its old settings entry so "
                         "the tools are not listed twice, and the Emperor icon shows in Claude Desktop.",
                         title="Claude Connector")

    def on_claude_code(self, sender, args):
        from emperor_claude import claude_code
        command, lead = bridge.command_for(settings.load())
        if not command:
            emperor_ui.alert("Emperor's Python is not ready yet - press Reconnect first.", title="Claude Connector", warn=True)
            return
        text = claude_code.setup(command, list(lead) + [bridge.server_path()])
        emperor_ui.alert(text + "\n\nIn Claude Code the skill is called emperor-revit-skills; it is used by itself for Revit "
                         "work. Restart Claude Code to load it.", title="Claude Connector")

    def on_auto_changed(self, sender, args):
        if self._loading:
            return
        cfg = settings.load()
        cfg["auto_register"] = bool(self.chk_auto.IsChecked)
        settings.save(cfg)

    def on_toggle_write(self, sender, args):
        cfg = settings.load()
        if not cfg.get("allow_write"):
            go = emperor_ui.alert("Let Claude change the model (set parameters, export files)?\n\n"
                             "Claude is told to show a preview and ask you first, but you "
                             "stay responsible for what you approve. Every change is one "
                             "undo step in Revit.",
                             title="Write access", yes=True, no=True)
            if not go:
                return
            cfg["allow_write"] = True
        else:
            cfg["allow_write"] = False
        settings.save(cfg)
        self.refresh()

    def on_toggle_script(self, sender, args):
        cfg = settings.load()
        if not cfg.get("allow_scripts"):
            go = emperor_ui.alert("Let Claude run its own Python scripts inside Revit?\n\n"
                             "A script can do anything the Revit API allows, including "
                             "deleting elements and touching files. Scripts run in one "
                             "undo step, but file changes cannot be undone.",
                             title="Scripting access", yes=True, no=True)
            if not go:
                return
            cfg["allow_scripts"] = True
        else:
            cfg["allow_scripts"] = False
        settings.save(cfg)
        self.refresh()

    def on_copy(self, sender, args):
        cfg = settings.load()
        Clipboard.SetText(bridge.snippet(cfg))
        command, lead = bridge.command_for(cfg)
        emperor_ui.alert("MCP config copied.\n\nPaste it into another client's MCP settings "
                    "(for Claude Code: claude mcp add Emperor-Revit -- %s \"%s\")."
                    % (" ".join([command or "py"] + list(lead)), bridge.server_path()),
                    title="Claude Connector")

    def on_profile_changed(self, sender, args):
        if getattr(self, "_loading", True):
            return
        cfg = settings.load()
        new = PROFILES[max(0, self.cb_profile.SelectedIndex)]
        if cfg.get("tool_profile", "all") == new:
            return
        cfg["tool_profile"] = new
        settings.save(cfg)
        if emperor_ui.alert("Claude Desktop loads its tools when it starts.\n\nRestart Claude Desktop now to use the "
                            "new tool set?", title="Claude Connector", yes=True, no=True):
            state, message = bridge.restart_claude_desktop()
            emperor_ui.alert(message, title="Claude Connector")

    def on_memory(self, sender, args):
        folder = os.path.join(settings.settings_dir(), "projects")
        if not os.path.isdir(folder):
            os.makedirs(folder)
        try:
            os.startfile(folder)
        except Exception as ex:
            emperor_ui.alert("Project Memory folder:\n%s\n\n%s" % (folder, ex), title="Claude Connector")

    def on_refresh(self, sender, args):
        self._loading = True
        self.refresh()
        self._loading = False

    def on_close(self, sender, args):
        self.Close()


ConnectorWindow().show_dialog()
