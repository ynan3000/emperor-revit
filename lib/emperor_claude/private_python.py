# -*- coding: utf-8 -*-
"""Emperor's own private Python for the Claude Connector - nothing to install for the user.

Claude Desktop starts the connector's MCP server (mcp_server/emperor_mcp_server.py, plain Python 3, standard
library only). Instead of needing Python installed on Windows, Emperor uses the official "embeddable" Python
from python.org: a small zip (about 11 MB) that is only unpacked into a private folder - not installed, no
PATH, no registry, invisible to other programs.

Where it comes from, first match wins:
  1. <Emperor.extension>\\python\\python.exe          an already unpacked copy shipped with Emperor
  2. <Emperor.extension>\\python\\python-*-embed-*.zip a zip shipped with Emperor (unpacked to 3.)
  3. %LOCALAPPDATA%\\Emperor\\python\\python.exe        the private copy
  4. downloaded once from python.org into 3. (official build; python.exe must be signed by the
     Python Software Foundation or it is deleted again)
When none of this works (no internet the first time, blocked download) the connector falls back to a
Python installed on Windows ('py -3' / python.exe), exactly like before.
"""
import glob
import os
import shutil

PY_VERSION = "3.12.10"
EMBED_NAME = "python-%s-embed-amd64.zip" % PY_VERSION
EMBED_URL = "https://www.python.org/ftp/python/%s/%s" % (PY_VERSION, EMBED_NAME)
SIGNER = "Python Software Foundation"


def _extension_root():
    here = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def bundled_dir():
    return os.path.join(_extension_root(), "python")


def private_dir():
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Emperor", "python")


def _log(text):
    try:
        from emperor_claude import bridge
        bridge._log("private python: " + text)
    except Exception:
        pass


def _signer_dotnet(exe):
    import clr
    for ref in ("System.Security.Cryptography", "System.Security.Cryptography.X509Certificates", "System.Security"):
        try:
            clr.AddReference(ref)
        except Exception:
            pass
    from System.Security.Cryptography.X509Certificates import X509Certificate
    return X509Certificate.CreateFromSignedFile(exe).Subject or ""


def _signer_powershell(exe):
    import subprocess
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "$s = Get-AuthenticodeSignature -LiteralPath '%s'; \"$($s.Status)|$($s.SignerCertificate.Subject)\"" % exe.replace("'", "''")]
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs["startupinfo"] = si
    except Exception:
        pass
    out = subprocess.Popen(cmd, **kwargs).communicate()[0]
    try:
        out = out.decode("utf-8", "replace")
    except Exception:
        pass
    status, _sep, subject = (out or "").strip().partition("|")
    if status.strip().lower() not in ("valid", ""):
        return ""                                        # broken / unsigned signature
    return subject


def _signed_by_psf(exe):
    """True when python.exe is signed by the Python Software Foundation, False when it is not,
    None when this PC cannot check signatures at all (the file then still came from python.org over HTTPS)."""
    checked = False
    for reader in (_signer_dotnet, _signer_powershell):
        try:
            subject = reader(exe)
            checked = True
            if SIGNER.lower() in (subject or "").lower():
                return True
        except Exception as ex:
            _log("signature reader %s not available: %s" % (reader.__name__, ex))
    return False if checked else None


def _unzip(zip_path, target):
    import clr
    clr.AddReference("System.IO.Compression.FileSystem")
    from System.IO.Compression import ZipFile
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)
    os.makedirs(target)
    ZipFile.ExtractToDirectory(zip_path, target)


def _download(url, dest):
    import clr
    clr.AddReference("System")
    from System.Net import WebClient, ServicePointManager, SecurityProtocolType
    try:
        ServicePointManager.SecurityProtocol = ServicePointManager.SecurityProtocol | SecurityProtocolType.Tls12
    except Exception:
        pass
    client = WebClient()
    try:
        client.Headers.Add("User-Agent", "Emperor-Revit-Toolkit")
        client.DownloadFile(url, dest)
    finally:
        client.Dispose()


_CHECKED = {}


def _valid(exe, check_signature=True):
    if not os.path.isfile(exe):
        return False
    try:
        stamp = (exe.lower(), os.path.getmtime(exe), os.path.getsize(exe))
    except Exception:
        stamp = None
    if stamp is not None and stamp in _CHECKED:
        return _CHECKED[stamp]
    ok = _valid_uncached(exe, check_signature)
    if stamp is not None:
        _CHECKED[stamp] = ok
    return ok


def _valid_uncached(exe, check_signature=True):
    if check_signature:
        signed = _signed_by_psf(exe)
        if signed is False:
            return False
        if signed is None:
            _log("could not check the signature of %s - accepted (official python.org download)" % exe)
    return True


def existing():
    """Path of a ready private python.exe, or None (no download)."""
    exe = os.path.join(bundled_dir(), "python.exe")
    if _valid(exe):
        return exe
    exe = os.path.join(private_dir(), "python.exe")
    if _valid(exe):
        return exe
    return None


def ensure(download=True):
    """Path of the private python.exe; unpacks a shipped zip or downloads the official one if needed.
    Returns None when that is not possible (the caller then falls back to a Windows Python)."""
    exe = existing()
    if exe:
        return exe
    target = private_dir()
    zips = sorted(glob.glob(os.path.join(bundled_dir(), "python-*-embed-*.zip")), reverse=True)
    tmp = None
    try:
        if zips:
            source = zips[0]
            _log("unpacking shipped %s" % source)
        elif download:
            if not os.path.isdir(os.path.dirname(target)):
                os.makedirs(os.path.dirname(target))
            tmp = os.path.join(os.path.dirname(target), EMBED_NAME + ".part")
            _log("downloading %s" % EMBED_URL)
            _download(EMBED_URL, tmp)
            source = tmp
        else:
            return None
        _unzip(source, target)
        exe = os.path.join(target, "python.exe")
        if not _valid(exe):
            _log("python.exe missing or not signed by the %s - removed" % SIGNER)
            shutil.rmtree(target, ignore_errors=True)
            return None
        _log("ready: %s" % exe)
        return exe
    except Exception as ex:
        _log("not available (%s) - a Python installed on Windows is used instead, if any" % ex)
        try:
            shutil.rmtree(target, ignore_errors=True)
        except Exception:
            pass
        return None
    finally:
        if tmp and os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
