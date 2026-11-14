# -*- coding: utf-8 -*-
"""Emperor Claude Connector - local listener that runs inside Revit.

The MCP server (started by Claude Desktop) calls this listener over HTTP on
localhost. Requests are queued and executed on Revit's main thread through an
ExternalEvent, which is the only safe way to touch the Revit API.

Safety: loopback only, a secret token header is required, and any request that
carries a browser Origin header is refused (so web pages cannot talk to it).
"""
import os
import json
import time
import threading
import traceback

import clr

clr.AddReference("System")          # HttpListener lives here
clr.AddReference("RevitAPIUI")
from System import AppDomain
from System.IO import StreamReader
from System.Net import HttpListener
from System.Text import Encoding
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent

from pyrevit import HOST_APP

from emperor_claude import settings, core, jobs

TIMEOUT_SECONDS = 300
_APPDOMAIN_KEY = "EmperorClaudeListener"
_lock = threading.Lock()
_queue = []
_state = {"event": None, "handler": None}


class _Job(object):
    def __init__(self, method, path, body):
        self.method = method
        self.path = path
        self.body = body
        self.done = threading.Event()
        self.status = 500
        self.data = {"error": "request was not processed"}
        self.abandoned = False      # the caller stopped waiting (timeout): never run it later


class _Handler(IExternalEventHandler):
    __namespace__ = "EmperorClaudeConnector"

    def Execute(self, uiapp):
        while True:
            with _lock:
                job = _queue.pop(0) if _queue else None
            if job is None:
                break
            if job.abandoned:
                job.done.set()
                continue
            try:
                job.status, job.data = core.dispatch(job.method, job.path, job.body)
            except Exception as ex:
                job.status = 500
                job.data = {"error": "%s" % ex, "trace": traceback.format_exc()[-1500:]}
            _close_background_job(job)
            job.done.set()

    def GetName(self):
        return "Emperor Claude Connector"


def _close_background_job(item):
    """A background job whose script never ran (guard, no project, crash) must not stay 'queued'."""
    try:
        jid = (item.body or {}).get("_job_id")
    except Exception:
        jid = None
    if not jid:
        return
    j = jobs.get(jid)
    if j is not None and j.status in ("queued", "running"):
        j.status = "failed"
        j.finished = time.time()
        j.result = {"ok": False, "error": (item.data or {}).get("error", "the job did not run")}


def _job_route(path, body):
    """Job routes are answered right here (listener thread) so they work while Revit is busy."""
    if path == "/job/start":
        guard = core.script_guard()
        if guard:
            return guard
        if not (body.get("code") or body.get("name")):
            return 400, {"error": "Give either 'code' or the 'name' of a saved script / recipe."}
        j = jobs.create(body.get("name"), body.get("description"))
        payload = dict(body)
        payload["_job_id"] = j.id
        with _lock:
            _queue.append(_Job("POST", "/script/run", payload))
        _state["event"].Raise()
        return 202, {"job_id": j.id, "status": j.status}
    if path == "/job/list":
        return 200, {"jobs": jobs.listing()}
    j = jobs.get(body.get("id")) if body.get("id") else jobs.latest()
    if j is None:
        return 404, {"error": "No such job (jobs are forgotten when Revit restarts)."}
    if path == "/job/status":
        data = j.summary()
        data["recent_progress"] = j.log[-8:]
        return 200, data
    if path == "/job/result":
        data = j.summary()
        if j.status in ("queued", "running"):
            data["ready"] = False
            data["recent_progress"] = j.log[-8:]
            return 200, data
        data["ready"] = True
        data["result"] = j.result
        return 200, data
    if path == "/job/cancel":
        jobs.cancel(j.id)
        data = j.summary()
        data["note"] = "Cancel requested: the job stops at its next checkpoint() call (scripts without one finish normally)."
        return 200, data
    return 404, {"error": "Unknown job route: %s" % path}


def _reply(ctx, status, data):
    try:
        payload = Encoding.UTF8.GetBytes(json.dumps(data))
        resp = ctx.Response
        resp.StatusCode = int(status)
        resp.ContentType = "application/json; charset=utf-8"
        resp.ContentLength64 = len(payload)
        resp.OutputStream.Write(payload, 0, len(payload))
    except Exception:
        pass
    finally:
        try:
            ctx.Response.Close()
        except Exception:
            pass


def _handle(ctx, token):
    try:
        req = ctx.Request
        headers = req.Headers
        host = ((headers["Host"] or "").split(":")[0]).lower()
        if headers["Origin"] is not None or host not in ("localhost", "127.0.0.1"):
            return _reply(ctx, 403, {"error": "forbidden"})
        if headers["X-Emperor-Token"] != token:
            return _reply(ctx, 401, {"error": "bad token - reload pyRevit / restart the MCP server"})

        path = req.Url.AbsolutePath
        for prefix in ("/routes/emperor", "/emperor"):
            if path.startswith(prefix):
                path = path[len(prefix):]
                break
        method = req.HttpMethod

        body = {}
        if method == "POST":
            raw = StreamReader(req.InputStream, Encoding.UTF8).ReadToEnd()
            if raw and raw.strip():
                body = json.loads(raw)

        if path.startswith("/job/") and path != "/job/revert":
            status, data = _job_route(path, body)
            return _reply(ctx, status, data)

        job = _Job(method, path, body)
        with _lock:
            _queue.append(job)
        _state["event"].Raise()
        job.done.wait(TIMEOUT_SECONDS)
        if not job.done.is_set():
            # Revit was busy the whole time: take the request back so it does not run (and change
            # the model) minutes later, after Claude was already told that it failed.
            job.abandoned = True
            with _lock:
                if job in _queue:
                    _queue.remove(job)
            return _reply(ctx, 504, {"error": "Revit did not answer in time. A dialog or a running "
                                              "command may be blocking it - close it and try again."})
        _reply(ctx, job.status, job.data)
    except Exception as ex:
        _reply(ctx, 500, {"error": "%s" % ex})


def _serve(listener, token):
    while True:
        try:
            ctx = listener.GetContext()
        except Exception:
            break  # listener stopped (Revit closing or pyRevit reload)
        t = threading.Thread(target=_handle, args=(ctx, token))
        t.daemon = True
        t.start()


def _stop_previous():
    try:
        old = AppDomain.CurrentDomain.GetData(_APPDOMAIN_KEY)
        if old is not None:
            old.Stop()
            old.Close()
    except Exception:
        pass
    try:
        AppDomain.CurrentDomain.SetData(_APPDOMAIN_KEY, None)
    except Exception:
        pass


def start():
    """Start the listener. Returns the port, or None if no port could be bound."""
    _stop_previous()
    cfg = settings.load()
    token = settings.ensure_token()
    first = int(cfg.get("port") or 48890)

    listener, port = None, None
    for candidate in range(first, first + 10):
        for hosts in (("localhost", "127.0.0.1"), ("localhost",)):
            trial = HttpListener()
            for h in hosts:
                trial.Prefixes.Add("http://%s:%d/" % (h, candidate))
            try:
                trial.Start()
                listener, port = trial, candidate
                break
            except Exception:
                try:
                    trial.Close()
                except Exception:
                    pass
        if listener is not None:
            break
    if listener is None:
        return None

    AppDomain.CurrentDomain.SetData(_APPDOMAIN_KEY, listener)
    _state["handler"] = _Handler()
    _state["event"] = ExternalEvent.Create(_state["handler"])

    thread = threading.Thread(target=_serve, args=(listener, token))
    thread.daemon = True
    thread.start()

    settings.write_session({
        "port": port,
        "token": token,
        "pid": os.getpid(),
        "revit": str(HOST_APP.version),
        "started": int(time.time()),
    })
    return port
