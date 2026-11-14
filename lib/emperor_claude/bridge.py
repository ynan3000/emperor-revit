# -*- coding: utf-8 -*-
"""Emperor Claude Connector - Claude Desktop registration and status helpers.

NOTE: never call the listener's HTTP endpoints from inside Revit's UI thread -
the request is answered on that same thread, so it would wait on itself.
Only a plain TCP check is used to see whether the listener is up.
"""
import os
import glob
import json
import shutil
import socket
import subprocess

from emperor_claude import settings

SERVER_KEY = "Emperor-Revit"          # name shown in Claude Desktop / Claude Code
LEGACY_KEYS = ("emperor-revit",)      # older Emperor versions - removed when found
EXT_NAME = "emperor-revit"            # id of the Claude Desktop extension (manifest name)
MIN_PYTHON = 308  # 3.8


def extension_root():
    here = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def server_path():
    return os.path.join(extension_root(), "mcp_server", "emperor_mcp_server.py")


def port_open(port, timeout=1.0):
    try:
        s = socket.create_connection(("localhost", int(port)), timeout)
        s.close()
        return True
    except Exception:
        return False


def listener_port():
    """Port of the running listener, from the session file written by Revit."""
    info = settings.read_session()
    if info and info.get("port") and port_open(info["port"]):
        return int(info["port"])
    return None


# ------------------------------------------------------------------ Python 3 discovery
def _text(raw):
    try:
        return raw.decode("utf-8", "ignore")
    except Exception:
        return "%s" % raw


def _run_quiet(cmd):
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs["startupinfo"] = si
    except Exception:
        pass
    try:
        proc = subprocess.Popen(cmd, **kwargs)
        out, _err = proc.communicate()
        return proc.returncode, _text(out).strip()
    except Exception:
        return -1, ""


def _python_ok(exe):
    if not exe or not os.path.isfile(exe) or "windowsapps" in exe.lower():
        return False
    code, out = _run_quiet([exe, "-c", "import sys;print(sys.version_info[0]*100+sys.version_info[1])"])
    try:
        return code == 0 and int(out.split()[-1]) >= MIN_PYTHON
    except Exception:
        return False


def _launcher_ok():
    """True when the Windows Python launcher 'py -3' starts a Python 3.8+."""
    code, out = _run_quiet(["py", "-3", "-c", "import sys;print(sys.version_info[0]*100+sys.version_info[1])"])
    try:
        return code == 0 and int(out.split()[-1]) >= MIN_PYTHON
    except Exception:
        return False


def find_python():
    """Full path of a usable Python 3 (3.8+), or None. Used for the status line only;
    Claude Desktop is started through 'py -3' whenever the launcher exists (see command_for)."""
    cfg = settings.load()
    cached = cfg.get("python_exe")
    if cached and _python_ok(cached):
        return cached

    candidates = []
    code, out = _run_quiet(["py", "-3", "-c", "import sys;print(sys.executable)"])
    if code == 0 and out:
        candidates.append(out.splitlines()[-1].strip())
    local = os.environ.get("LOCALAPPDATA") or ""
    program = os.environ.get("ProgramFiles") or ""
    for pattern in (os.path.join(local, "Python", "pythoncore-*", "python.exe"),   # Python install manager
                    os.path.join(local, "Programs", "Python", "Python3*", "python.exe"),
                    os.path.join(program, "Python3*", "python.exe"),
                    os.path.join(local, "Python", "bin", "python.exe")):
        candidates.extend(sorted(glob.glob(pattern), reverse=True))
    code, out = _run_quiet(["where", "python"])
    if code == 0:
        candidates.extend([l.strip() for l in out.splitlines() if l.strip()])

    for exe in candidates:
        if _python_ok(exe):
            return exe
    return None


def private_exe():
    """Emperor's own private Python (see private_python.py), already in place - no download here."""
    try:
        from emperor_claude import private_python
        return private_python.existing()
    except Exception:
        return None


def command_for(cfg):
    """(command, leading args) Claude Desktop uses to start the MCP server.

    1. Emperor's private Python (official embeddable build, nothing installed on Windows) - preferred.
    2. The Windows launcher 'py -3' when a Python is installed.
    3. A full python.exe path when the launcher is missing."""
    exe = private_exe()
    if exe:
        return exe, []
    if cfg.get("launcher") == "py" or _launcher_ok():
        return "py", ["-3"]
    exe = cfg.get("python_exe") or find_python()
    if exe:
        return exe, []
    return None, []


# ------------------------------------------------------------------ Claude Desktop config
CONFIG_NAME = "claude_desktop_config.json"
_SKIP_DIRS = set(["microsoft", "google", "mozilla", "temp", "cache", "caches", "code cache",
                  "gpucache", "node_modules", "packages", "programs", "nvidia", "intel",
                  "crashdumps", "d3dscache", "autodesk", "pyrevit", "squirrel-temp"])


def _is_live(path):
    """The file Claude Desktop really uses also stores its own settings ("preferences")."""
    try:
        data = _read_config(path)
        return isinstance(data, dict) and "preferences" in data
    except Exception:
        return False


def _walk_for(root, max_depth, deadline, out):
    import time
    if not root or not os.path.isdir(root):
        return
    base_depth = root.rstrip("\\/").count(os.sep)
    for folder, dirs, files in os.walk(root):
        if time.time() > deadline:
            return
        depth = folder.count(os.sep) - base_depth
        if CONFIG_NAME in files:
            p = os.path.join(folder, CONFIG_NAME)
            if p not in out and _is_live(p):
                out.append(p)
        if depth >= max_depth:
            del dirs[:]
        else:
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS]


def _live_configs():
    """Config files that hold Claude Desktop's own settings.

    The location differs between Claude Desktop builds (standard installer, Microsoft Store /
    MSIX, newer versions), so it is found by searching the user's app-data folders for
    claude_desktop_config.json with Claude's settings inside. The result is remembered in
    the connector settings and re-checked every time."""
    import time
    found = []
    cfg = settings.load()
    for p in cfg.get("claude_live_configs") or []:
        if os.path.isfile(p) and _is_live(p) and p not in found:
            found.append(p)
    if found:
        return found
    appdata = os.environ.get("APPDATA") or ""
    local = os.environ.get("LOCALAPPDATA") or ""
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    deadline = time.time() + 20
    # Store packages of Claude first (deep), then the usual app-data folders
    for pkg in glob.glob(os.path.join(local, "Packages", "*")):
        if "claude" in os.path.basename(pkg).lower():
            _walk_for(pkg, 6, deadline, found)
    _walk_for(appdata, 3, deadline, found)
    _walk_for(local, 3, deadline, found)
    _walk_for(home, 2, deadline, found)
    if found:
        cfg["claude_live_configs"] = found
        settings.save(cfg)
    return found


def claude_config_paths():
    """Every claude_desktop_config.json Claude Desktop may read on this PC.

    - standard installer:         %APPDATA%\\Claude\\claude_desktop_config.json
    - Microsoft Store / MSIX app: %LOCALAPPDATA%\\Packages\\<any package>\\LocalCache\\Roaming\\Claude\\...
      (the Store app reads its own private copy; the package name differs between builds,
      so every package folder is searched, not only Claude_*)
    """
    appdata = os.environ.get("APPDATA") or ""
    local = os.environ.get("LOCALAPPDATA") or ""
    found = []

    def add(p):
        if p and p not in found:
            found.append(p)

    standard = os.path.join(appdata, "Claude", "claude_desktop_config.json")
    if os.path.isfile(standard) or os.path.isdir(os.path.dirname(standard)):
        add(standard)
    for live in _live_configs():
        add(live)
    for sub in (("LocalCache", "Roaming", "Claude"), ("LocalCache", "Local", "Claude")):
        for folder in glob.glob(os.path.join(local, "Packages", "*", *sub)):
            if "claude" in os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(folder)))).lower() \
                    or os.path.isfile(os.path.join(folder, "claude_desktop_config.json")):
                add(os.path.join(folder, "claude_desktop_config.json"))
    return found


def _describe(path):
    """Short note for the log: exists / size / looks like the file Claude Desktop uses."""
    try:
        if not os.path.isfile(path):
            return "%s (no file yet)" % path
        data = _read_config(path)
        live = isinstance(data, dict) and "preferences" in data
        has = bool(((data or {}).get("mcpServers") or {}).get(SERVER_KEY))
        return "%s (Claude settings inside: %s, emperor-revit: %s)" % (path, live, has)
    except Exception as ex:
        return "%s (unreadable: %s)" % (path, ex)



def _norm(path):
    try:
        return os.path.normcase(os.path.normpath(path))
    except Exception:
        return path


def _is_server_script(arg):
    return isinstance(arg, (str, type(u""))) and arg.lower().endswith("emperor_mcp_server.py")


def entry_points_here(entry):
    """True when a config entry runs THIS extension's emperor_mcp_server.py (any command)."""
    try:
        for a in entry.get("args") or []:
            if _is_server_script(a) and _norm(a) == _norm(server_path()):
                return True
    except Exception:
        pass
    return False


def server_entry(cfg):
    command, lead = command_for(cfg)
    if not command:
        return None
    return {"command": command, "args": list(lead) + [server_path()]}


def _repaired_entry(existing):
    """Keep the user's own command / args and only move the server path to this extension.
    Returns None when the existing entry cannot be repaired that way."""
    if not isinstance(existing, dict) or not existing.get("command"):
        return None
    args = list(existing.get("args") or [])
    hits = [k for k, a in enumerate(args) if _is_server_script(a)]
    if len(hits) != 1:
        return None
    args[hits[0]] = server_path()
    fixed = dict(existing)
    fixed["args"] = args
    return fixed


def snippet(cfg):
    entry = server_entry(cfg) or {"command": "py", "args": ["-3", server_path()]}
    return json.dumps({"mcpServers": {SERVER_KEY: entry}}, indent=2)


def _read_config(path):
    if not os.path.isfile(path):
        return {}
    with open(path, "rb") as f:
        raw = _text(f.read()).lstrip(u"\ufeff").strip()
    return json.loads(raw) if raw else {}


def is_registered(cfg):
    paths = claude_config_paths()
    if not paths:
        return False, "Claude Desktop was not found on this PC"
    for path in paths:
        try:
            entry = (_read_config(path).get("mcpServers") or {}).get(SERVER_KEY)
        except Exception:
            continue
        if entry and entry_points_here(entry):
            return True, "Registered in Claude Desktop (%s)" % " ".join(
                [entry.get("command") or ""] + list(entry.get("args") or [])[:-1]).strip()
    return False, "Not registered in Claude Desktop yet"


def _log(text):
    """Registration log: %APPDATA%\\Emperor\\claude_connector_register.log (kept small)."""
    try:
        import time
        path = os.path.join(settings.settings_dir(), "claude_connector_register.log")
        if os.path.isfile(path) and os.path.getsize(path) > 200000:
            os.remove(path)
        with open(path, "ab") as f:
            f.write(("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text)).encode("utf-8"))
    except Exception:
        pass


def _plan(paths, desired, launcher, force):
    """[(path, existing, new_entry)] for every config file that needs a change.
    With Emperor's private Python an entry is only "working" when it already uses that python.exe."""
    want_cmd = desired.get("command") if (desired and private_exe() and
                                          _norm(desired.get("command") or "") == _norm(private_exe())) else None
    changes = []
    for path in paths:
        try:
            data = _read_config(path)
        except Exception as ex:
            _log("%s is not valid JSON, left untouched: %s" % (path, ex))
            continue
        if not isinstance(data, dict):
            continue
        servers = data.get("mcpServers")
        existing = servers.get(SERVER_KEY) if isinstance(servers, dict) else None
        legacy = isinstance(servers, dict) and any(k in servers for k in LEGACY_KEYS)
        if existing and entry_points_here(existing) and not force and not legacy and \
                (want_cmd is None or _norm(existing.get("command") or "") == _norm(want_cmd)):
            continue                                   # working entry: leave it alone
        new_entry = None
        if existing and not force and not launcher:
            new_entry = _repaired_entry(existing)      # no launcher: keep the user's own command
        if new_entry is None:
            new_entry = desired
        if new_entry is None or existing == new_entry:
            continue
        changes.append((path, existing, new_entry))
    return changes


def _write(path, new_entry):
    """Re-read the file right before writing (Claude Desktop may just have saved it)."""
    data = _read_config(path) if os.path.isfile(path) else {}
    if not isinstance(data, dict):
        data = {}
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    backup = path + ".emperor.bak"
    if os.path.isfile(path) and not os.path.isfile(backup):
        shutil.copyfile(path, backup)
    for k in LEGACY_KEYS:
        servers.pop(k, None)
    if new_entry is None:
        servers.pop(SERVER_KEY, None)
    else:
        servers[SERVER_KEY] = new_entry
    data["mcpServers"] = servers
    with open(path, "wb") as f:
        f.write(json.dumps(data, indent=2).encode("utf-8"))


def mcpb_path():
    """The Claude Desktop extension shipped with Emperor (shows the Emperor icon in Claude Desktop)."""
    return os.path.join(extension_root(), "claude_desktop", "Emperor Revit.mcpb")


def desktop_extension_installed():
    """Folder of the installed 'Emperor Revit' Claude Desktop extension, or None."""
    roots = set()
    for p in claude_config_paths():
        d = os.path.dirname(p)
        roots.add(d)
        roots.add(os.path.dirname(d))
    for root in roots:
        try:
            for name in os.listdir(root):
                if "extension" not in name.lower():
                    continue
                folder = os.path.join(root, name)
                if not os.path.isdir(folder):
                    continue
                for sub in os.listdir(folder):
                    man = os.path.join(folder, sub, "manifest.json")
                    if os.path.isfile(man):
                        try:
                            with open(man, "rb") as f:
                                if json.loads(_text(f.read()).lstrip(u"\ufeff")).get("name") == EXT_NAME:
                                    return os.path.join(folder, sub)
                        except Exception:
                            pass
        except Exception:
            pass
    return None


def remember_server_path():
    """The extension's launcher starts the server path saved here (so it follows Emperor updates)."""
    try:
        cfg = settings.load()
        if cfg.get("server_path") != server_path():
            cfg["server_path"] = server_path()
            settings.save(cfg)
    except Exception:
        pass


def ensure_registered(cfg, force=False, restart=False):
    """Make sure Claude Desktop knows the MCP server.

    Claude Desktop keeps this config file in memory and writes it back (for example when it
    quits or saves a preference), which wipes an entry added while it was running. So when a
    change is needed and Claude Desktop is running, it is CLOSED FIRST, the file is written,
    and (restart=True) Claude Desktop is opened again.

    - An entry that already runs this extension's server is never touched (unless force=True).
    - A missing / old / broken entry is written as  py -3 <...\\Emperor.extension\\mcp_server\\
      emperor_mcp_server.py>  (python.exe <server> only when the Windows launcher is missing).

    Returns (state, message); state is one of
    ok / registered / updated / no_claude / no_python / error.
    """
    paths = claude_config_paths()
    if not paths:
        _log("Claude Desktop config folder not found")
        return "no_claude", "Claude Desktop does not seem to be installed yet."

    cfg = settings.load()
    remember_server_path()
    ext = desktop_extension_installed()
    if ext:
        stale = []
        for path in paths:
            try:
                servers = _read_config(path).get("mcpServers") or {}
                entry = servers.get(SERVER_KEY) or [servers.get(k) for k in LEGACY_KEYS if servers.get(k)]
                if entry:
                    stale.append((path, entry, None))
            except Exception:
                pass
        if not stale:
            return "ok", "Claude Desktop uses the Emperor Revit extension."
        _log("extension installed (%s) - removing the old config entry from: %s" % (ext, ", ".join(c[0] for c in stale)))
        return _apply_changes(stale, restart, "removed")
    try:                                      # Emperor's private Python (downloaded once, ~11 MB)
        from emperor_claude import private_python
        private = private_python.ensure(download=True)
    except Exception as ex:
        private = None
        _log("private python failed: %s" % ex)
    if private and cfg.get("python_exe") != private:
        cfg["python_exe"] = private
        settings.save(cfg)
    launcher = True if private else _launcher_ok()
    if not private and launcher and cfg.get("launcher") != "py":
        cfg["launcher"] = "py"
        settings.save(cfg)
    exe = private or find_python()
    if exe and cfg.get("python_exe") != exe:
        cfg["python_exe"] = exe
        settings.save(cfg)
    desired = server_entry(cfg)
    if desired is None:
        _log("no Python 3 found (launcher=%s)" % launcher)
        return "no_python", ("Emperor could not prepare its own Python for the connector (it is downloaded "
                             "once from python.org, about 11 MB - is this PC offline or is python.org blocked?)."
                             "\n\nConnect to the internet and restart Revit, or install Python 3 from "
                             "python.org (tick the 'py launcher'), then restart Revit.")

    _log("config files:\n    " + "\n    ".join(_describe(p) for p in paths))
    changes = _plan(paths, desired, launcher, force)
    _log("needs change: %s" % (", ".join(c[0] for c in changes) or "none"))
    if not changes and not force:
        return "ok", "Already registered."

    return _apply_changes(changes, restart, None, paths, desired, launcher, force)


def _apply_changes(changes, restart, mode=None, paths=None, desired=None, launcher=False, force=False):
    """Close Claude Desktop when needed, write (or remove, new_entry None) the entries, reopen it."""
    was_running = False
    main_path = None
    procs = _desktop_processes()
    if procs and (changes or (force and restart)):
        was_running = True
        main_path = procs[0][1]
        stopped, why = _stop_desktop()
        _log("Claude Desktop closed before writing: %s %s (%s)" % (stopped, why, main_path))
        if not stopped:
            return "error", why
        again = _plan(paths, desired, launcher, force) if mode is None else []   # it may have saved on exit
        _log("needs change after close: %s" % (", ".join(c[0] for c in again) or "none"))
        # never skip the write: merge both plans (same file listed once)
        seen = set(c[0] for c in again)
        changes = again + [c for c in changes if c[0] not in seen]

    state, notes = "ok", []
    for path, existing, new_entry in changes:
        try:
            _write(path, new_entry)
            check = (_read_config(path).get("mcpServers") or {}).get(SERVER_KEY)
            if check == new_entry:
                state = mode or ("registered" if existing is None else "updated")
                if new_entry is None:
                    notes.append(path)
                    _log("removed and verified %s" % path)
                else:
                    notes.append("%s\n    %s %s" % (path, new_entry.get("command"), " ".join(new_entry.get("args") or [])))
                    _log("wrote and verified %s: %s" % (path, json.dumps(new_entry)))
            else:
                state = "error"
                notes.append("%s was written but the entry is not there when read back." % path)
                _log("verify FAILED %s: read back %s" % (path, json.dumps(check)))
        except Exception as ex:
            notes.append("%s could not be written (%s)" % (path, ex))
            _log("write failed %s: %s" % (path, ex))
            state = "error"

    if was_running and restart:
        try:
            ok = _launch_desktop(main_path)
            notes.append("Claude Desktop was restarted." if ok else
                         "Claude Desktop was closed - open it again to finish.")
            _log("Claude Desktop reopened: %s" % ok)
            if ok and mode is None:   # check again in the background (never block Revit's UI thread)
                import threading
                t = threading.Thread(target=_verify_after_launch, args=(paths, desired, launcher))
                t.daemon = True
                t.start()
        except Exception as ex:
            notes.append("Claude Desktop was closed - open it again to finish (%s)." % ex)
            _log("reopen failed: %s" % ex)
    elif was_running:
        notes.append("Claude Desktop was closed - open it again to finish.")

    if state == "removed":
        return "updated", "Claude Desktop now uses the Emperor Revit extension; the old entry was removed from:\n" + "\n".join(notes)
    if state in ("registered", "updated"):
        return state, "Registered in:\n" + "\n".join(notes)
    if state == "error":
        return state, "\n".join(notes)
    return "ok", "Already registered." + ("\n" + "\n".join(notes) if notes else "")


def _verify_after_launch(paths, desired, launcher, wait_seconds=20):
    """Claude Desktop can rewrite its config while starting. Check again after it started;
    if the entry was wiped, close it, write once more and reopen (one retry only)."""
    import time
    time.sleep(wait_seconds)
    lost = _plan(paths, desired, launcher, False)
    if not lost:
        _log("entry still present %d s after restart" % wait_seconds)
        return
    _log("entry WIPED after restart in: %s - writing again" % ", ".join(c[0] for c in lost))
    procs = _desktop_processes()
    main_path = procs[0][1] if procs else None
    stopped, why = _stop_desktop()
    if not stopped:
        _log("second close failed: %s" % why)
        return
    for path, _existing, new_entry in lost:
        try:
            _write(path, new_entry)
            _log("rewrote %s" % path)
        except Exception as ex:
            _log("rewrite failed %s: %s" % (path, ex))
    if main_path:
        _log("Claude Desktop reopened again: %s" % _launch_desktop(main_path))


# ------------------------------------------------------------------ restart Claude Desktop
_DESKTOP_MARKERS = ("\\anthropicclaude\\", "\\programs\\claude\\", "\\program files\\claude\\")


def _is_desktop_exe(path):
    """Claude Desktop only - never Claude Code (claude.exe in .local\\bin, npm, etc.)."""
    p = (path or "").lower()
    if not p.endswith("claude.exe"):
        return False
    if "\\windowsapps\\" in p and "claude" in p.split("\\windowsapps\\", 1)[1].split("\\", 1)[0]:
        return True                                    # Store build, any package name
    return any(m in p for m in _DESKTOP_MARKERS)


def _desktop_processes():
    """[(process, exe path)] of the running Claude Desktop app."""
    found = []
    try:
        from System.Diagnostics import Process
        for proc in Process.GetProcessesByName("claude"):
            try:
                path = proc.MainModule.FileName
            except Exception:
                path = ""
            if not path:   # packaged (Store) apps can refuse MainModule: ask Windows instead
                code, out = _run_quiet(["powershell", "-NoProfile", "-Command",
                                        "(Get-Process -Id %d).Path" % proc.Id])
                path = (out or "").strip() if code == 0 else ""
            if _is_desktop_exe(path):
                found.append((proc, path))
    except Exception:
        pass
    return found


def _store_app_id():
    """AppUserModelID of the Microsoft Store build of Claude, or None."""
    code, out = _run_quiet(["powershell", "-NoProfile", "-Command",
                            "(Get-StartApps | Where-Object { $_.Name -eq 'Claude' } | "
                            "Select-Object -First 1).AppID"])
    out = (out or "").strip()
    return out if code == 0 and out else None


def _launch_desktop(old_path):
    local = os.environ.get("LOCALAPPDATA") or ""
    launcher = os.path.join(local, "AnthropicClaude", "claude.exe")   # standard installer
    if os.path.isfile(launcher):
        subprocess.Popen([launcher])
        return True
    if old_path and "\\windowsapps\\" in old_path.lower():
        app_id = _store_app_id()
        if app_id:
            subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + app_id])
            return True
    if old_path and os.path.isfile(old_path):
        subprocess.Popen([old_path])
        return True
    app_id = _store_app_id()
    if app_id:
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + app_id])
        return True
    return False


def _stop_desktop(wait_seconds=15):
    """Close every Claude Desktop process. Returns (stopped, message)."""
    import time
    procs = _desktop_processes()
    if not procs:
        return True, "not running"
    for proc, _path in procs:
        try:
            proc.CloseMainWindow()
        except Exception:
            pass
    time.sleep(2)
    for proc, _path in procs:
        try:
            if not proc.HasExited:
                proc.Kill()
        except Exception:
            pass
    deadline = time.time() + wait_seconds
    while time.time() < deadline and _desktop_processes():
        time.sleep(0.5)
    if _desktop_processes():
        return False, "Claude Desktop did not close. Quit it from the tray icon, then press Reconnect."
    time.sleep(1)
    return True, "closed"


def restart_claude_desktop():
    """Close Claude Desktop and open it again. (state, message)."""
    procs = _desktop_processes()
    if not procs:
        return "not_running", "Claude Desktop was not running; it will load the connector when you open it."
    main_path = procs[0][1]
    stopped, why = _stop_desktop()
    if not stopped:
        return "error", why
    try:
        if _launch_desktop(main_path):
            return "restarted", "Claude Desktop was restarted and now loads the Revit connector."
    except Exception as ex:
        return "closed_only", "Claude Desktop was closed but could not be reopened (%s). Open it again." % ex
    return "closed_only", "Claude Desktop was closed. Open it again to finish."
