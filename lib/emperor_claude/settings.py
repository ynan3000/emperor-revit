# -*- coding: utf-8 -*-
"""Emperor Claude Connector - shared settings (stored per Windows user)."""
import os
import json
import uuid

DEFAULTS = {
    "allow_write": False,     # Claude may only READ the model until this is switched ON
    "allow_scripts": False,   # separate switch: lets Claude run its own scripts inside Revit
    "port": 48890,            # first port tried by the local listener (then +1 ... +9)
    "auto_register": True,    # register with Claude Desktop automatically at Revit start
    "auto_restart_claude": True,  # close + reopen Claude Desktop after (re)registering
    "tool_profile": "all",    # tools given to Claude: all / modeling / read (fewer tools = fewer tokens)
    "python_exe": "",         # filled automatically (full path of a Python 3)
    "launcher": "",           # "py" when the Windows launcher 'py -3' works (used for Claude Desktop)
    "token": "",              # secret shared by Revit and the MCP server (created automatically)
}


def settings_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "Emperor")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except OSError:
            pass
    return folder


def settings_path():
    return os.path.join(settings_dir(), "claude_connector.json")


def session_path():
    return os.path.join(settings_dir(), "claude_connector_session.json")


def load():
    data = dict(DEFAULTS)
    try:
        with open(settings_path(), "rb") as f:
            stored = json.loads(f.read().decode("utf-8-sig"))
        if isinstance(stored, dict):
            data.update(stored)
    except Exception:
        pass
    return data


def save(data):
    text = json.dumps(data, indent=2, sort_keys=True)
    with open(settings_path(), "wb") as f:
        f.write(text.encode("utf-8"))


def ensure_token():
    cfg = load()
    if not cfg.get("token"):
        cfg["token"] = uuid.uuid4().hex + uuid.uuid4().hex
        save(cfg)
    return cfg["token"]


def read_session():
    try:
        with open(session_path(), "rb") as f:
            return json.loads(f.read().decode("utf-8-sig"))
    except Exception:
        return None


def write_session(info):
    with open(session_path(), "wb") as f:
        f.write(json.dumps(info, indent=2).encode("utf-8"))
