# -*- coding: utf-8 -*-
"""Emperor Claude Connector - Claude Code setup.

1. installs the "Emperor Revit Skills" skill into  %USERPROFILE%\\.claude\\skills\\emperor-revit-skills
   (copied again only when Emperor ships a newer text)
2. registers the emperor-revit MCP server for Claude Code (user scope) with Claude Code's own command:
   claude mcp add --scope user emperor-revit -- <python> <server>
Nothing happens when Claude Code is not installed. Log: %APPDATA%\\Emperor\\claude_connector_register.log
"""
import os
import glob
import shutil
import subprocess

SKILL_NAME = 'emperor-revit-skills'
SERVER_KEY = 'Emperor-Revit'
LEGACY_KEYS = ('emperor-revit',)


def _log(text):
    try:
        from emperor_claude import bridge
        bridge._log('claude code: ' + text)
    except Exception:
        pass


def _home():
    return os.environ.get('USERPROFILE') or os.path.expanduser('~')


def claude_exe():
    """Path of the Claude Code command, or None."""
    home = _home()
    candidates = [os.path.join(home, '.local', 'bin', 'claude.exe'),
                  os.path.join(os.environ.get('APPDATA') or '', 'npm', 'claude.cmd')]
    candidates += glob.glob(os.path.join(os.environ.get('LOCALAPPDATA') or '', 'Programs', 'claude*', 'claude.exe'))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    code, out = _run(['where', 'claude'])
    if code == 0 and out.strip():
        return out.strip().splitlines()[0].strip()
    return None


def installed():
    return claude_exe() is not None or os.path.isdir(os.path.join(_home(), '.claude'))


def _run(cmd, timeout_hint=None):
    kwargs = {'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs['startupinfo'] = si
    except Exception:
        pass
    try:
        p = subprocess.Popen(cmd, **kwargs)
        out = p.communicate()[0]
        try:
            out = out.decode('utf-8', 'replace')
        except Exception:
            pass
        return p.returncode, out or u''
    except Exception as ex:
        return -1, u'%s' % ex


def _skill_source():
    here = os.path.abspath(__file__)
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(root, 'claude_skill', SKILL_NAME)


def _same_tree(a, b):
    for base, _dirs, files in os.walk(a):
        for f in files:
            src = os.path.join(base, f)
            dst = os.path.join(b, os.path.relpath(src, a))
            try:
                if not os.path.isfile(dst):
                    return False
                with open(src, 'rb') as x, open(dst, 'rb') as y:
                    if x.read() != y.read():
                        return False
            except Exception:
                return False
    return True


def install_skill():
    """Copy the skill into Claude Code. Returns 'installed' / 'updated' / 'current' / 'no_claude_code' / 'error: ...'."""
    if not installed():
        return 'no_claude_code'
    src = _skill_source()
    if not os.path.isdir(src):
        return 'error: skill files missing in Emperor'
    dst = os.path.join(_home(), '.claude', 'skills', SKILL_NAME)
    try:
        if os.path.isdir(dst) and _same_tree(src, dst):
            return 'current'
        state = 'updated' if os.path.isdir(dst) else 'installed'
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        _log('skill %s -> %s' % (state, dst))
        return state
    except Exception as ex:
        _log('skill copy failed: %s' % ex)
        return 'error: %s' % ex


def register_mcp(command, args):
    """Register emperor-revit for Claude Code (user scope). Returns 'ok' / 'registered' / 'no_claude_code' / 'error: ...'."""
    exe = claude_exe()
    if exe is None:
        return 'no_claude_code'
    for old in LEGACY_KEYS:                       # older Emperor versions used a lowercase name
        if _run([exe, 'mcp', 'get', old])[0] == 0:
            _run([exe, 'mcp', 'remove', '--scope', 'user', old])
            _log('removed old connector name %s' % old)
    code, out = _run([exe, 'mcp', 'get', SERVER_KEY])
    wanted = [command] + list(args)
    if code == 0 and all((a.lower() in out.lower()) for a in wanted):
        return 'ok'
    if code == 0:
        _run([exe, 'mcp', 'remove', '--scope', 'user', SERVER_KEY])
    code, out = _run([exe, 'mcp', 'add', '--scope', 'user', SERVER_KEY, '--'] + wanted)
    if code == 0:
        _log('connector registered: %s' % ' '.join(wanted))
        return 'registered'
    _log('claude mcp add failed (%s): %s' % (code, out[-400:]))
    return 'error: %s' % out.strip()[-300:]


def setup(command, args):
    """Skill + connector for Claude Code. Returns a short text for the UI."""
    if not installed():
        return 'Claude Code is not installed on this PC.'
    s = install_skill()
    m = register_mcp(command, args)
    return 'Claude Code - skill: %s, connector: %s' % (s, m)
