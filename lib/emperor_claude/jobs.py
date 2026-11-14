# -*- coding: utf-8 -*-
"""Emperor Claude Connector - registry of background jobs.

A job is a script that runs on Revit's main thread (through the ExternalEvent) while the
HTTP request that started it has already been answered. Status, result and cancel are
answered by the listener thread, so they work even while the job is running.
IronPython 2.7 and CPython 3 compatible.
"""
import time
import uuid
import threading

MAX_KEEP = 40
MAX_LOG = 60

_lock = threading.Lock()
_jobs = {}
_order = []


class Cancelled(Exception):
    """Raised by checkpoint() when the user / Claude asked the job to stop."""


class Job(object):
    def __init__(self, name, description):
        self.id = uuid.uuid4().hex[:8]
        self.name = name or "inline script"
        self.description = description or ""
        self.status = "queued"          # queued / running / done / failed / cancelled
        self.message = ""
        self.done = 0
        self.total = 0
        self.created = time.time()
        self.started = None
        self.finished = None
        self.cancel_requested = False
        self.result = None
        self.added_ids = []             # elements the job created (for revert_job)
        self.deadline = None            # time limit: checkpoint() stops the job after it
        self.log = []

    def summary(self):
        end = self.finished or time.time()
        return {"job_id": self.id, "name": self.name, "description": self.description,
                "status": self.status, "progress": self.message,
                "done": self.done, "total": self.total,
                "seconds": round(end - (self.started or self.created), 1),
                "cancel_requested": self.cancel_requested}


def create(name, description):
    job = Job(name, description)
    with _lock:
        _jobs[job.id] = job
        _order.append(job.id)
        while len(_order) > MAX_KEEP:
            _jobs.pop(_order.pop(0), None)
    return job


def get(job_id):
    with _lock:
        return _jobs.get(job_id)


def latest():
    with _lock:
        return _jobs.get(_order[-1]) if _order else None


def listing():
    with _lock:
        return [_jobs[i].summary() for i in reversed(_order) if i in _jobs]


def cancel(job_id):
    job = get(job_id)
    if job is None:
        return None
    if job.status in ("queued", "running"):
        job.cancel_requested = True
    return job


def progress(job, message, done=None, total=None):
    if job is None:
        return
    job.message = "%s" % message
    if done is not None:
        job.done = done
    if total is not None:
        job.total = total
    job.log.append("%s" % message)
    if len(job.log) > MAX_LOG:
        del job.log[0:len(job.log) - MAX_LOG]


def checkpoint(job):
    """Call inside long loops: lets the job be cancelled between steps."""
    if job is None:
        return
    if job.cancel_requested:
        raise Cancelled("cancelled by request")
    if job.deadline is not None and time.time() > job.deadline:
        raise Cancelled("time limit reached (max_seconds) - the job was stopped and rolled back")
