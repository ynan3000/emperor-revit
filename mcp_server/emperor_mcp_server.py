#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Emperor Claude Connector - MCP server (stdio, standard library only).

Claude Desktop starts this script. It exposes Revit tools to Claude and forwards
each call to the local listener the Emperor plugin runs inside Revit.
No pip packages are needed - any Python 3.8+ works.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom          # noqa: E402  (same folder)
import pdf_lines     # noqa: E402

SERVER_NAME = "Emperor-Revit"
SERVER_VERSION = "1.6.0"

TIMEOUT = int(os.environ.get("EMPEROR_TIMEOUT", "300"))
MAX_CHARS = 60000
# Claude Desktop gives up on a tool call after about 60 s, so script tools wait at most this long
# and then hand back a job id instead of blocking.
WAIT_DEFAULT = int(os.environ.get("EMPEROR_WAIT", "40"))


class RevitError(Exception):
    pass


def log(text):
    sys.stderr.write("[emperor-revit] %s\n" % text)
    sys.stderr.flush()


# --------------------------------------------------------------------------- Revit bridge
def _session():
    """Port and secret written by the Emperor plugin when Revit starts."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "Emperor", "claude_connector_session.json")
    try:
        with open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8-sig"))
    except Exception:
        return None


def _call_once(method, path, payload, info):
    url = "http://localhost:%s/emperor%s" % (info["port"], path)
    headers = {"Accept": "application/json", "X-Emperor-Token": info.get("token", "")}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        text = resp.read().decode("utf-8", "replace")
        return json.loads(text) if text.strip() else {}


def call_revit(method, path, payload=None):
    """Call the listener. If Revit was restarted (new port / token) the session file is re-read and the call retried."""
    last = None
    for attempt in range(3):
        info = _session()
        if not info or not info.get("port"):
            last = RevitError("Revit is not running, or the Emperor plugin is not loaded in it "
                              "(no session found). Open Revit with pyRevit and the Emperor "
                              "Claude Connector extension, then try again.")
        else:
            try:
                return _call_once(method, path, payload, info)
            except urllib.error.HTTPError as ex:
                text = ex.read().decode("utf-8", "replace")
                try:
                    detail = json.loads(text).get("error", text)
                except Exception:
                    detail = text
                if ex.code == 401 and attempt < 2:      # token changed: Revit restarted
                    last = RevitError("Revit answered HTTP 401: %s" % str(detail)[:200])
                    time.sleep(1.5)
                    continue
                raise RevitError("Revit answered HTTP %s: %s" % (ex.code, str(detail)[:800]))
            except (urllib.error.URLError, ConnectionError, OSError) as ex:
                last = RevitError("Cannot reach Revit on port %s (%s). If Revit was closed or "
                                  "restarted, try again in a few seconds; otherwise reload pyRevit."
                                  % (info["port"], ex))
        if attempt < 2:
            time.sleep(1.5)
    raise last


# --------------------------------------------------------------------------- tool catalogue
def _schema(props=None, required=None):
    return {"type": "object", "properties": props or {}, "required": required or []}


IDS = {"type": "array", "items": {"type": "integer"},
       "description": "Revit element ids (integers)."}

TOOLS = [
    {"name": "revit_status", "method": "GET", "path": "/status",
     "description": "Check the connection to Revit: version, open project, active view, and whether write access is ON.",
     "schema": _schema()},
    {"name": "get_project_info", "method": "GET", "path": "/project",
     "description": "Project information: name, number, client, address, status, file path, workshared or cloud model.",
     "schema": _schema()},
    {"name": "list_levels", "method": "GET", "path": "/levels",
     "description": "All levels with id and elevation in meters, lowest first.",
     "schema": _schema()},
    {"name": "list_sheets", "method": "GET", "path": "/sheets",
     "description": "All sheets with number, name, id and number of placed views.",
     "schema": _schema()},
    {"name": "list_views", "method": "GET", "path": "/views",
     "description": "All views (no templates or sheets) with type, level and assigned view template.",
     "schema": _schema()},
    {"name": "list_links", "method": "GET", "path": "/links",
     "description": "Revit links: load status, pinned, attachment type, and every instance with its workset and pinned state.",
     "schema": _schema()},
    {"name": "count_elements_by_category", "method": "GET", "path": "/categories",
     "description": "Model element counts per category (top 80). Use it to see what the model contains.",
     "schema": _schema()},
    {"name": "get_selection", "method": "GET", "path": "/selection",
     "description": "Elements currently selected in Revit (id, category, family and type, name).",
     "schema": _schema()},
    {"name": "query_elements", "method": "POST", "path": "/elements/query",
     "description": "List elements of one category, optionally with chosen parameter values. "
                    "Category is matched by name, e.g. 'Mechanical Equipment', 'Ducts', 'Pipes', 'Air Terminals'.",
     "schema": _schema({
         "category": {"type": "string", "description": "Revit category name."},
         "parameters": {"type": "array", "items": {"type": "string"},
                        "description": "Parameter names to return for each element (instance, then type)."},
         "name_contains": {"type": "string", "description": "Keep elements whose name or type contains this text."},
         "limit": {"type": "integer", "description": "Max elements returned (default 100, max 1000)."},
         "level": {"type": "string", "description": "Only elements on this level."},
         "in_active_view": {"type": "boolean", "description": "Only elements visible in the active view."},
     }, ["category"])},
    {"name": "get_parameters", "method": "POST", "path": "/parameters/get",
     "description": "Read parameters of specific elements. Leave 'names' empty to list every parameter (use for discovery, few elements).",
     "schema": _schema({
         "element_ids": IDS,
         "names": {"type": "array", "items": {"type": "string"}, "description": "Parameter names to read."},
     }, ["element_ids"])},
    {"name": "set_parameter", "method": "POST", "path": "/parameters/set",
     "description": "MODIFIES THE MODEL. Set one instance parameter on many elements (one undo step in Revit). "
                    "Requires write access ON. dry_run defaults to true and only shows the plan: always show the plan "
                    "to the user and get their OK before calling again with dry_run=false. Numbers are read in the "
                    "project's display units.",
     "schema": _schema({
         "element_ids": IDS,
         "name": {"type": "string", "description": "Instance parameter name."},
         "value": {"description": "New value (text, number, or yes/no)."},
         "dry_run": {"type": "boolean", "description": "true = preview only (default)."},
     }, ["element_ids", "name", "value"])},
    {"name": "list_cad_imports", "method": "GET", "path": "/cad/list",
     "description": "CAD files (DWG/DXF) linked or imported in the project: id, name, linked or imported, view-specific.",
     "schema": _schema()},
    {"name": "inspect_cad", "method": "POST", "path": "/cad/inspect",
     "description": "Read a CAD link's geometry: every layer with line/polyline/arc counts, total length and extents, in "
                    "meters in Revit project coordinates. Pass 'layers' with include_segments=true to also get the "
                    "straight segments [x1,y1,x2,y2] of those layers (arcs are tessellated). CAD text is not available.",
     "schema": _schema({
         "import_id": {"type": "integer", "description": "Id from list_cad_imports."},
         "layers": {"type": "array", "items": {"type": "string"},
                    "description": "Layer names whose segments should be returned."},
         "include_segments": {"type": "boolean", "description": "Return segments for the layers above."},
         "max_segments": {"type": "integer", "description": "Segment cap (default 2000, max 6000)."},
     }, ["import_id"])},
    {"name": "list_mep_types", "method": "GET", "path": "/mep/types",
     "description": "Duct types, mechanical (duct) system types, air terminal types and levels available in the project.",
     "schema": _schema()},
    {"name": "create_ducts", "method": "POST", "path": "/mep/ducts",
     "description": "MODIFIES THE MODEL. Create straight ducts from segments in meters (Revit project coordinates, "
                    "e.g. from inspect_cad or a calibrated PDF). Each row is [x1,y1,x2,y2] (size from width_mm+height_mm "
                    "or diameter_mm), [x1,y1,x2,y2,width_mm,height_mm] (rectangular) or [x1,y1,x2,y2,diameter_mm] "
                    "(round), so one call can hold many sizes. Segments are split at T-junctions (a branch must END "
                    "on the main's centerline) and joined with unions, transitions (different sizes), elbows, tees "
                    "and crosses. Revit warning dialogs are answered automatically and returned in revit_messages. "
                    "One undo step. Requires write access ON. Names are matched against list_mep_types. "
                    "Max 1500 segments per call.",
     "schema": _schema({
         "segments": {"type": "array", "items": {"type": "array", "items": {"type": "number"}},
                      "description": "Rows of [x1,y1,x2,y2(,width,height | ,diameter)] in meters."},
         "duct_type": {"type": "string", "description": "Duct type name."},
         "system_type": {"type": "string", "description": "Mechanical system type name, e.g. Supply Air."},
         "level": {"type": "string", "description": "Level name."},
         "offset_m": {"type": "number", "description": "Height above the level in meters (default 2.7)."},
         "width_mm": {"type": "number"}, "height_mm": {"type": "number"}, "diameter_mm": {"type": "number"},
         "connect_fittings": {"type": "boolean", "description": "Create fittings where ducts meet (default true)."},
     }, ["segments", "duct_type", "system_type", "level"])},
    {"name": "list_grids", "method": "GET", "path": "/grids",
     "description": "All grids with name and start/end points in meters (Revit project coordinates). "
                    "Use grid intersections to calibrate a PDF or drawing to the model.",
     "schema": _schema()},
    {"name": "list_family_types", "method": "POST", "path": "/family/types",
     "description": "Family types loaded in the project (e.g. air terminals, mechanical equipment), with id, category and "
                    "placement kind. OneLevelBased types can be placed with place_family.",
     "schema": _schema({
         "category": {"type": "string", "description": "e.g. 'Air Terminals', 'Mechanical Equipment'."},
         "name_contains": {"type": "string"},
         "limit": {"type": "integer", "description": "Default 100, max 500."},
     })},
    {"name": "load_family", "method": "POST", "path": "/family/load",
     "description": "MODIFIES THE MODEL. Load a family (.rfa) from a path on the Revit PC into the project. Requires write access ON.",
     "schema": _schema({"path": {"type": "string", "description": "Full path to the .rfa file."}}, ["path"])},
    {"name": "place_family", "method": "POST", "path": "/family/place",
     "description": "MODIFIES THE MODEL. Place many instances of one level-based family type (diffusers, fans, equipment) at "
                    "x,y positions in meters. family_type is 'Family : Type' (a unique part is enough). One undo step. "
                    "Requires write access ON. Face-based or work-plane families fail and are reported.",
     "schema": _schema({
         "family_type": {"type": "string"},
         "level": {"type": "string"},
         "placements": {"type": "array",
                        "items": {"type": "object", "properties": {
                            "x": {"type": "number"}, "y": {"type": "number"},
                            "offset_m": {"type": "number"}, "rotation_deg": {"type": "number"}},
                            "required": ["x", "y"]},
                        "description": "Positions in meters; optional height above level and rotation."},
         "offset_m": {"type": "number", "description": "Default height above the level in meters."},
     }, ["family_type", "level", "placements"])},
    {"name": "run_revit_script", "kind": "job", "method": "POST", "path": "/job/start",
     "description": "ADVANCED, MODIFIES THE MODEL. Run IronPython 2.7 code inside Revit. Variables: doc, uidoc, uiapp, DB, UI, List, os, json, "
                    "P (params dict) and a preloaded helper library (M/F meters<->feet, nm, eid, one, levels, link, link_rooms, host_bbox, "
                    "wall_faces_index, ceiling_boxes, phys, nearest_conn, pipe_chain, clashes, Attempt = sub-transaction that rolls back on error, "
                    "unpin_and_delete, progress(msg, done, total), checkpoint() for cancel). print() output is returned (capped); set 'result' to "
                    "return a value. Runs in one transaction (one undo step). dry_run=true rolls everything back and reports. Runs as a background job: "
                    "after wait_seconds (default 40) you get a job_id instead of a timeout - then use job_status / job_result. "
                    "Requires Scripting access ON in the Claude Connector window.",
     "schema": _schema({
         "code": {"type": "string", "description": "Python (IronPython 2.7) source."},
         "description": {"type": "string", "description": "Short label for the undo entry."},
         "use_transaction": {"type": "boolean", "description": "Wrap in one transaction (default true)."},
         "dry_run": {"type": "boolean", "description": "Roll everything back and only report (default false)."},
         "params": {"type": "object", "description": "Passed to the script as P."},
         "max_output": {"type": "integer", "description": "Max characters of printed output returned (default 8000)."},
         "wait_seconds": {"type": "integer", "description": "Wait for the result this long before returning a job_id (default 40, 0 = at once)."},
         "max_seconds": {"type": "integer", "description": "Time limit: the job is stopped and rolled back at its next checkpoint() after this (default 900)."},
     }, ["code"])},
    {"name": "session_brief", "method": "POST", "path": "/brief",
     "description": "START HERE. One call that returns the saved PROJECT MEMORY (levels, links, duct/pipe types, systems, "
                    "insulation and terminal types, plan views, the user's standards and notes, and what changed since the "
                    "last visit) plus the active view, access switches and saved scripts. Replaces many discovery calls. 'append_note' adds one line to the project notes (standing rules, e.g. 'FCUs keep rotation 90'); "
                    "'replace_notes' rewrites them.",
     "schema": _schema({
         "append_note": {"type": "string", "description": "One line to add to the project notes file."},
         "replace_notes": {"type": "string", "description": "Replace the whole notes file."},
     })},
    {"name": "run_saved_script", "kind": "job", "method": "POST", "path": "/job/start",
     "description": "MODIFIES THE MODEL (unless dry_run). Run a saved script or built-in recipe by name (see list_scripts). "
                    "'params' arrive in the script as the dict P. dry_run=true runs everything and rolls it back, returning what "
                    "WOULD happen. Runs as a background job: if it takes longer than wait_seconds you get a job_id - use "
                    "job_status / job_result. Requires Scripting access ON.",
     "schema": _schema({
         "name": {"type": "string", "description": "Script or recipe name."},
         "params": {"type": "object", "description": "Parameters passed to the script as P."},
         "dry_run": {"type": "boolean", "description": "Roll everything back and only report (default false)."},
         "max_output": {"type": "integer", "description": "Max characters of printed output returned (default 8000)."},
         "wait_seconds": {"type": "integer", "description": "How long to wait for the result before returning a job_id (default 40, 0 = return at once)."},
     }, ["name"])},
    {"name": "list_scripts", "method": "GET", "path": "/script/list",
     "description": "Saved scripts and built-in recipes with one-line descriptions and their parameters.",
     "schema": _schema()},
    {"name": "get_script", "method": "POST", "path": "/script/get",
     "description": "Read the source of a saved script or recipe.",
     "schema": _schema({"name": {"type": "string"}}, ["name"])},
    {"name": "save_script", "method": "POST", "path": "/script/save",
     "description": "Save an IronPython script under a name so it can be re-run with run_saved_script without sending the code again. "
                    "Start the code with '# DESC: what it does' and '# PARAM: name - meaning' lines. Requires Scripting access ON.",
     "schema": _schema({
         "name": {"type": "string", "description": "Letters, digits, _ and - only."},
         "code": {"type": "string"},
         "description": {"type": "string", "description": "Used as the # DESC line if the code has none."},
     }, ["name", "code"])},
    {"name": "job_status", "method": "POST", "path": "/job/status",
     "description": "Progress of a background job (state, progress text, done/total, seconds). Omit id for the latest job. Works while Revit is busy.",
     "schema": _schema({"id": {"type": "string", "description": "job_id (default: latest job)."}})},
    {"name": "job_result", "method": "POST", "path": "/job/result",
     "description": "Result of a background job once it is done (ready=false while it still runs). Omit id for the latest job.",
     "schema": _schema({"id": {"type": "string"}})},
    {"name": "cancel_job", "method": "POST", "path": "/job/cancel",
     "description": "Ask a running job to stop at its next checkpoint. Work already done stays (one undo step reverts it).",
     "schema": _schema({"id": {"type": "string"}})},
    {"name": "list_jobs", "method": "POST", "path": "/job/list",
     "description": "Recent background jobs with their state.",
     "schema": _schema()},
    {"name": "revert_job", "method": "POST", "path": "/job/revert",
     "description": "MODIFIES THE MODEL. Delete the elements a finished job created. Modified or deleted elements are NOT restored "
                    "(use Ctrl+Z in Revit for a full undo). Requires Write and Scripting access.",
     "schema": _schema({"id": {"type": "string"}}, ["id"])},
    {"name": "view_snapshot", "kind": "image", "method": "POST", "path": "/snapshot",
     "description": "Get a PNG picture of a Revit view, zoomed to some elements, so you can SEE the result (orientation, collisions, tags). "
                    "Give element_ids (zoom to them) or center_x/center_y in meters, optionally view_name (default: the active view). "
                    "Does not change the model; the view's zoom is restored afterwards. Revit may briefly switch views.",
     "schema": _schema({
         "element_ids": IDS,
         "view_name": {"type": "string", "description": "A plan, section or 3D view; default is the active view."},
         "center_x": {"type": "number", "description": "Meters (project coordinates) - alternative to element_ids."},
         "center_y": {"type": "number"},
         "half_size_m": {"type": "number", "description": "Half the width of the area for center_x/center_y (default 6)."},
         "margin_m": {"type": "number", "description": "Extra margin around the elements (default 2)."},
         "pixels": {"type": "integer", "description": "Longest side in pixels (300-2400, default 700 - raise only when detail is needed; images cost many tokens)."},
     })},
    {"name": "export_sheets_dwg", "method": "POST", "path": "/export/dwg",
     "description": "WRITES FILES. Export sheets to DWG, one file per sheet named '<number>-<name>.dwg'. "
                    "Requires write access ON. Confirm the sheet list and folder with the user first.",
     "schema": _schema({
         "sheet_numbers": {"type": "array", "items": {"type": "string"}, "description": "Sheet numbers to export."},
         "folder": {"type": "string", "description": "Output folder (created if missing), e.g. C:\\\\Exports\\\\DWG."},
         "xref_views": {"type": "boolean",
                        "description": "Export views on sheets and links as external references (default true)."},
     }, ["sheet_numbers", "folder"])},
    # ------------------------------------------------------------------ v1.5: memory, summaries, HVAC tools
    {"name": "project_memory", "method": "POST", "path": "/memory",
     "description": "This project's saved memory: model facts (levels, links, duct/pipe types and systems, insulation and "
                    "terminal types, plan views) + the user's STANDARDS and NOTES, kept between chats. Read it instead of "
                    "rediscovering the model. When the user states a project rule (e.g. supply duct type, ceiling height, "
                    "naming), save it: action=set key=... value=... . action: get (default) | set | unset | note | clear_notes | refresh.",
     "schema": _schema({
         "action": {"type": "string", "enum": ["get", "set", "unset", "note", "clear_notes", "refresh"]},
         "key": {"type": "string", "description": "Standard name, e.g. 'supply duct type'."},
         "value": {"description": "Standard value."},
         "note": {"type": "string", "description": "One line for action=note."},
     })},
    {"name": "learn_standards", "method": "POST", "path": "/standards",
     "description": "The company's own rules, learned from its models: filter prefix + separator, system names and "
                    "abbreviations, sheet number pattern, view / template naming, duct / pipe / tag types in use. "
                    "Kept privately on this PC per company (Project Information organisation) and grown with every project. "
                    "action=learn (read this model, default) | get | set key value (a rule the user states) | unset key. "
                    "Follow the summary whenever you name or create views, filters, sheets, systems or tags.",
     "schema": _schema({
         "action": {"type": "string", "enum": ["learn", "get", "set", "unset"]},
         "key": {"type": "string"}, "value": {"description": "Rule value for action=set."},
         "details": {"type": "boolean", "description": "Also return everything that was read (default false)."},
     })},
    {"name": "summarize_elements", "method": "POST", "path": "/summary",
     "description": "Counts (and optional sums) of a category grouped by parameters - one small table instead of long "
                    "element lists. e.g. category='Ducts', group_by=['System Type','Size'], sum=['Length']. "
                    "group_by may use 'Level'. Filters: level, in_active_view, element_ids.",
     "schema": _schema({
         "category": {"type": "string"},
         "group_by": {"type": "array", "items": {"type": "string"}, "description": "Default ['Family and Type']."},
         "sum": {"type": "array", "items": {"type": "string"}, "description": "Numeric parameters to add up (display units)."},
         "level": {"type": "string"}, "in_active_view": {"type": "boolean"}, "element_ids": IDS,
     }, ["category"])},
    {"name": "model_check", "method": "POST", "path": "/check",
     "description": "HVAC / piping model check in one call: open (unconnected) connectors per category, ducts and pipes "
                    "without a system, air terminals without a system or with zero flow. Returns counts + capped ids. "
                    "Filters: level, in_active_view.",
     "schema": _schema({"level": {"type": "string"}, "in_active_view": {"type": "boolean"},
                        "max_ids": {"type": "integer", "description": "Ids returned per check (default 25)."}})},
    {"name": "size_ducts", "method": "POST", "path": "/size_ducts",
     "description": "Size ducts from their calculated airflow and a target velocity. Round: diameter; rectangular: width "
                    "for the current (or given) height. Rounded up to step_mm. dry_run defaults to TRUE (preview table) - "
                    "show it to the user, then call with dry_run=false (needs write access, one undo step). "
                    "Needs airflow on the ducts (terminals with flow, connected system).",
     "schema": _schema({
         "velocity_ms": {"type": "number", "description": "Target velocity m/s (default 5)."},
         "system_name": {"type": "string", "description": "Only ducts of this system type."},
         "element_ids": IDS, "level": {"type": "string"}, "in_active_view": {"type": "boolean"},
         "height_mm": {"type": "number", "description": "Fixed height for rectangular ducts."},
         "step_mm": {"type": "number", "description": "Rounding step (default 50)."},
         "min_mm": {"type": "number", "description": "Smallest size (default 100)."},
         "dry_run": {"type": "boolean"},
     })},
    {"name": "tag_view", "method": "POST", "path": "/tag",
     "description": "MODIFIES THE MODEL. Smart Tag: tag elements in a view (default active view), skipping tagged ones, "
                    "short ducts/pipes and moving tags to free spots. categories: ducts, flex_ducts, pipes, flex_pipes, "
                    "terminals, equipment, duct_accessories, pipe_accessories, plumbing_fixtures. tag_types: optional "
                    "{category: 'part of Family : Type'}. Requires write access. One undo step.",
     "schema": _schema({
         "view_name": {"type": "string"},
         "categories": {"type": "array", "items": {"type": "string"}},
         "tag_types": {"type": "object"},
         "orientation": {"type": "string", "enum": ["auto", "horizontal", "vertical"]},
         "skip_tagged": {"type": "boolean"}, "avoid_overlap": {"type": "boolean"}, "leader": {"type": "boolean"},
         "min_length_mm": {"type": "number"}, "offset_mm": {"type": "number", "description": "Gap from the element edge, paper mm (default 2)."},
         "skip_zero_flow": {"type": "boolean", "description": "Skip ducts with 0 L/s (default true)."},
         "place_anyway": {"type": "boolean", "description": "Place tags even without a free spot (default false)."},
         "always_horizontal": {"type": "boolean", "description": "Every tag horizontal (default false)."},
         "use_learned": {"type": "boolean", "description": "Try the tag spots learned from the user first (default true)."},
         "element_ids": IDS,
     })},
    {"name": "add_insulation", "method": "POST", "path": "/insulate",
     "description": "Smart Insulation: add / update / remove duct and pipe insulation by system type. rules: "
                    "[{kind:'duct'|'pipe', system:'Supply Air', insulation:'<insulation type>', thickness:'25' or "
                    "'50:25, 150:40, 50' (by size mm)}]. mode: update (default) | add | remove. parts: curves, fittings, "
                    "accessories, flex. scope: 'model' (default) | 'view'; or element_ids. dry_run defaults to TRUE; "
                    "dry_run=false needs write access (one undo step).",
     "schema": _schema({
         "rules": {"type": "array", "items": {"type": "object"}},
         "mode": {"type": "string", "enum": ["update", "add", "remove"]},
         "parts": {"type": "array", "items": {"type": "string"}},
         "scope": {"type": "string", "enum": ["model", "view"]},
         "element_ids": IDS, "dry_run": {"type": "boolean"},
     }, ["rules"])},
    # ------------------------------------------------------------------ v1.5: drawings -> ducts (run on this PC)
    {"name": "pdf_read", "kind": "local",
     "description": "Read a PDF drawing as VECTORS on this PC (no images, far fewer tokens). mode='summary' (start here): "
                    "line groups by colour and width with counts, lengths and extents + text samples (grid bubbles, "
                    "duct sizes). mode='lines': segments of chosen colours/widths/region. mode='text': text with positions. "
                    "Coordinates are PDF points unless 'calibration' is given: {points:[[px,py,mx,my],[px,py,mx,my]]} "
                    "(two known spots, e.g. grid intersections from list_grids) or {scale:100, origin:[px,py,mx,my]} -> meters "
                    "in Revit project coordinates. Parsed pages are cached, so repeated calls are fast.",
     "schema": _schema({
         "path": {"type": "string", "description": "Full path of the PDF on the user's PC."},
         "page": {"type": "integer", "description": "1-based (default 1)."},
         "mode": {"type": "string", "enum": ["summary", "lines", "text"]},
         "colors": {"type": "array", "items": {"type": "string"}, "description": "Keep these stroke colours, e.g. ['#0000FF']."},
         "min_width_pt": {"type": "number"}, "max_width_pt": {"type": "number"},
         "region": {"type": "array", "items": {"type": "number"}, "description": "[x0,y0,x1,y1] in output units."},
         "min_length": {"type": "number", "description": "Drop shorter segments (output units)."},
         "text_contains": {"type": "string"},
         "calibration": {"type": "object"},
         "max_items": {"type": "integer", "description": "Default 1500."},
     }, ["path"])},
    {"name": "pdf_to_ducts", "kind": "local",
     "description": "Drawing -> ducts in ONE call, without sending coordinates through the chat: reads the PDF lines of the "
                    "chosen colours/widths, turns double lines into centerlines with their width, joins tees and elbows, "
                    "calibrates to meters and creates the ducts (create_ducts). dry_run defaults to TRUE: returns counts, "
                    "size table and a sample only. Then call with dry_run=false (needs write access). "
                    "calibration is required ({points:[[px,py,mx,my],[px,py,mx,my]]} recommended).",
     "schema": _schema({
         "path": {"type": "string"}, "page": {"type": "integer"},
         "colors": {"type": "array", "items": {"type": "string"}},
         "min_width_pt": {"type": "number"}, "max_width_pt": {"type": "number"},
         "region": {"type": "array", "items": {"type": "number"}, "description": "[x0,y0,x1,y1] in meters (after calibration)."},
         "calibration": {"type": "object"},
         "double_lines": {"type": "boolean", "description": "Ducts drawn as two lines (default true). false = single centerlines."},
         "min_width_mm": {"type": "number", "description": "Smallest duct width to accept as a pair (default 80)."},
         "max_width_mm": {"type": "number", "description": "Largest duct width (default 1600)."},
         "width_mm": {"type": "number", "description": "Width for single-line drawings."},
         "height_mm": {"type": "number", "description": "Rectangular duct height (default 300)."},
         "round": {"type": "boolean", "description": "Round ducts: diameter = drawn width."},
         "step_mm": {"type": "number", "description": "Size rounding (default 50)."},
         "min_length_m": {"type": "number", "description": "Skip shorter ducts (default 0.3)."},
         "duct_type": {"type": "string"}, "system_type": {"type": "string"}, "level": {"type": "string"},
         "offset_m": {"type": "number"}, "dry_run": {"type": "boolean"},
     }, ["path", "calibration", "duct_type", "system_type", "level"])},
    {"name": "cad_to_ducts", "kind": "local",
     "description": "Same as pdf_to_ducts for a linked / imported DWG: reads the segments of the given layers from Revit "
                    "(already in meters), double lines -> centerlines with widths, joins tees / elbows, creates the ducts. "
                    "dry_run defaults to TRUE. Get import_id and layer names from list_cad_imports / inspect_cad.",
     "schema": _schema({
         "import_id": {"type": "integer"},
         "layers": {"type": "array", "items": {"type": "string"}},
         "region": {"type": "array", "items": {"type": "number"}},
         "double_lines": {"type": "boolean"}, "min_width_mm": {"type": "number"}, "max_width_mm": {"type": "number"},
         "width_mm": {"type": "number"}, "height_mm": {"type": "number"}, "round": {"type": "boolean"},
         "step_mm": {"type": "number"}, "min_length_m": {"type": "number"},
         "duct_type": {"type": "string"}, "system_type": {"type": "string"}, "level": {"type": "string"},
         "offset_m": {"type": "number"}, "dry_run": {"type": "boolean"},
     }, ["import_id", "layers", "duct_type", "system_type", "level"])},
]
TOOL_INDEX = dict((t["name"], t) for t in TOOLS)

# Tool profiles (Claude Connector window > "Tools given to Claude"). Every tool description is sent with
# every message, so a smaller set saves tokens in every chat.
READ_TOOLS = {"revit_status", "get_project_info", "list_levels", "list_sheets", "list_views", "list_links",
              "count_elements_by_category", "get_selection", "query_elements", "get_parameters", "list_cad_imports",
              "inspect_cad", "list_mep_types", "list_grids", "list_family_types", "session_brief", "view_snapshot",
              "project_memory", "summarize_elements", "model_check", "pdf_read", "learn_standards"}
MODELING_TOOLS = READ_TOOLS | {"set_parameter", "create_ducts", "load_family", "place_family", "size_ducts",
                               "tag_view", "add_insulation", "pdf_to_ducts", "cad_to_ducts", "export_sheets_dwg"}


def _settings():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    try:
        with open(os.path.join(base, "Emperor", "claude_connector.json"), "rb") as f:
            return json.loads(f.read().decode("utf-8-sig"))
    except Exception:
        return {}


def _profile():
    p = (_settings().get("tool_profile") or "all").lower()
    return p if p in ("all", "modeling", "read") else "all"


def tool_list():
    prof = _profile()
    allowed = None if prof == "all" else (MODELING_TOOLS if prof == "modeling" else READ_TOOLS)
    return [{"name": t["name"], "description": t["description"], "inputSchema": t["schema"]}
            for t in TOOLS if allowed is None or t["name"] in allowed]


# --------------------------------------------------------------------------- compact output
def _tabulate(value):
    """Lists of 4+ dicts with the same keys become {columns, rows}: the keys are sent once, not per item."""
    if isinstance(value, dict):
        return dict((k, _tabulate(v)) for k, v in value.items())
    if isinstance(value, list):
        if len(value) >= 4 and all(isinstance(x, dict) for x in value):
            keys = list(value[0].keys())
            if all(list(x.keys()) == keys for x in value):
                return {"columns": keys, "rows": [[_tabulate(x[k]) for k in keys] for x in value]}
        return [_tabulate(x) for x in value]
    if isinstance(value, float):
        return round(value, 4)
    return value


def _trim_traces(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "trace" and isinstance(v, str) and len(v) > 700:
                out[k] = "..." + v[-700:]
            else:
                out[k] = _trim_traces(v)
        return out
    if isinstance(value, list):
        return [_trim_traces(x) for x in value]
    return value


def _dump(result):
    text = json.dumps(_tabulate(_trim_traces(result)), ensure_ascii=False, separators=(",", ":"))
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n... [truncated - narrow the request]"
    return text


def _run_job(tool, arguments):
    payload = dict(arguments or {})
    wait = payload.pop("wait_seconds", None)
    wait = WAIT_DEFAULT if wait is None else max(0, int(wait))
    started = call_revit("POST", "/job/start", payload)
    job_id = started.get("job_id")
    deadline = time.time() + wait
    while True:
        res = call_revit("POST", "/job/result", {"id": job_id})
        if res.get("ready"):
            out = res.get("result") or {}
            out["job_id"] = job_id
            out["seconds"] = res.get("seconds")
            if res.get("status") == "cancelled":
                out["cancelled"] = True
            return _dump(out)
        if time.time() >= deadline:
            res["note"] = ("Still running in Revit (Revit's window is busy until it ends). Ask again with job_status / "
                           "job_result using this job_id; cancel_job stops it at its next checkpoint.")
            return _dump(res)
        time.sleep(0.6)


def _run_image(tool, arguments):
    args = dict(arguments or {})
    args.setdefault("pixels", 700)
    info = call_revit(tool["method"], tool["path"], args)
    path = info.get("path")
    content = [{"type": "text", "text": _dump(dict((k, v) for k, v in info.items() if k != "path"))}]
    if path and os.path.isfile(path):
        with open(path, "rb") as f:
            raw = f.read()
        content.append({"type": "image", "data": base64.b64encode(raw).decode("ascii"), "mimeType": "image/png"})
        try:
            os.remove(path)
            os.rmdir(os.path.dirname(path))
        except OSError:
            pass
    return content


# --------------------------------------------------------------------------- drawings -> ducts (local)
_PAGE_CACHE = {}


def _page(path, page):
    path = os.path.expandvars(os.path.expanduser(path or ""))
    if not os.path.isfile(path):
        raise RevitError("PDF not found: %s (give the full path of the file on this PC)." % path)
    key = (os.path.abspath(path), os.path.getmtime(path), int(page or 1))
    if key not in _PAGE_CACHE:
        if len(_PAGE_CACHE) > 6:
            _PAGE_CACHE.clear()
        try:
            pdf = pdf_lines.PdfFile(path)
            segs, texts, info = pdf_lines.read_page(pdf, pdf.page(int(page or 1)))
            info["pages"] = len(pdf.pages())
        except pdf_lines.PdfError as ex:
            raise RevitError(str(ex))
        _PAGE_CACHE[key] = (segs, texts, info)
    return _PAGE_CACHE[key]


def _hex_close(a, b, tol=24):
    try:
        a, b = a.lstrip("#"), b.lstrip("#")
        return all(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) <= tol for i in (0, 2, 4))
    except Exception:
        return False


def _filter(segs, args):
    colors = [c.upper() for c in (args.get("colors") or [])]
    wmin, wmax = args.get("min_width_pt"), args.get("max_width_pt")
    out = []
    for s in segs:
        if colors and not any(_hex_close(s[4], c) for c in colors):
            continue
        if wmin is not None and s[5] < float(wmin) - 1e-6:
            continue
        if wmax is not None and s[5] > float(wmax) + 1e-6:
            continue
        out.append(s)
    return out


def _in_region(seg, region):
    if not region:
        return True
    x0, y0, x1, y1 = [float(v) for v in region[:4]]
    lo_x, hi_x, lo_y, hi_y = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
    return (lo_x <= seg[0] <= hi_x and lo_y <= seg[1] <= hi_y) or (lo_x <= seg[2] <= hi_x and lo_y <= seg[3] <= hi_y)


def _calibration(args, required=False):
    cal = args.get("calibration") or {}
    if required and not (cal.get("points") or cal.get("scale")):
        raise RevitError("calibration is required: {points:[[px,py,mx,my],[px,py,mx,my]]} (two known spots, e.g. grid "
                         "intersections: PDF position from pdf_read mode=text, model position from list_grids) or "
                         "{scale:100, origin:[px,py,mx,my]}.")
    try:
        return geom.Calibration(points=cal.get("points"), scale=cal.get("scale"), origin=cal.get("origin"))
    except ValueError as ex:
        raise RevitError(str(ex))


def _len(s):
    return ((s[2] - s[0]) ** 2 + (s[3] - s[1]) ** 2) ** 0.5


def pdf_read(args):
    segs, texts, info = _page(args.get("path"), args.get("page"))
    cal = _calibration(args)
    unit = "m" if cal.mode != "none (PDF points)" else "pt"
    mode = (args.get("mode") or "summary").lower()
    region = args.get("region")
    cap = max(10, min(int(args.get("max_items") or 1500), 6000))
    out = {"page": int(args.get("page") or 1), "units": unit, "calibration": cal.describe()}
    out.update(info)
    if mode == "text":
        want = (args.get("text_contains") or "").lower()
        rows = []
        for x, y, t, size in texts:
            px, py = cal.pt(x, y)
            if want and want not in t.lower():
                continue
            if region and not _in_region((px, py, px, py), region):
                continue
            rows.append([round(px, 3), round(py, 3), t, size])
            if len(rows) >= cap:
                break
        out.update({"text_count": len(texts), "columns": ["x", "y", "text", "size_pt"], "rows": rows})
        return out
    chosen = _filter(segs, args)
    cal_segs = [cal.seg(s) + (s[4], s[5]) for s in chosen]
    if region:
        cal_segs = [s for s in cal_segs if _in_region(s, region)]
    if mode == "summary":
        groups = {}
        for s in cal_segs:
            g = groups.setdefault((s[4], s[5]), [0, 0.0, [1e18, 1e18, -1e18, -1e18]])
            g[0] += 1
            g[1] += _len(s)
            b = g[2]
            b[0], b[1] = min(b[0], s[0], s[2]), min(b[1], s[1], s[3])
            b[2], b[3] = max(b[2], s[0], s[2]), max(b[3], s[1], s[3])
        rows = sorted(([c, w, n, round(L, 2), [round(v, 2) for v in b]] for (c, w), (n, L, b) in groups.items()),
                      key=lambda r: -r[3])[:40]
        import re as _re
        grids = [t for t in texts if _re.fullmatch(r"[A-Z]{1,2}'?|\d{1,2}'?", t[2].strip())]
        sizes = [t for t in texts if _re.search(r"\d{2,4}\s*[xX×]\s*\d{2,4}|Ø\s*\d{2,4}|\bDN\s*\d+", t[2])]
        out.update({
            "segments": len(cal_segs), "texts": len(texts),
            "line_groups": {"columns": ["color", "width_pt", "count", "length", "extent[x0,y0,x1,y1]"], "rows": rows},
            "possible_grid_labels": [[round(v, 2) for v in cal.pt(x, y)] + [t] for x, y, t, _ in grids[:40]],
            "possible_size_labels": [[round(v, 2) for v in cal.pt(x, y)] + [t] for x, y, t, _ in sizes[:40]],
            "next": "Pick the duct colour/width from line_groups, calibrate with two grid intersections, then "
                    "pdf_to_ducts (dry_run first). Use mode='lines' only if you must see the geometry.",
        })
        return out
    min_len = float(args.get("min_length") or 0)
    merged = []
    by_style = {}
    for s in cal_segs:
        by_style.setdefault((s[4], s[5]), []).append(s[:4])
    tol = 0.002 if unit == "m" else 0.3
    for (c, w), group in by_style.items():
        for m in geom.merge_collinear(group, tol=tol):
            if _len(m) >= min_len:
                merged.append([round(v, 3) for v in m] + [c, w])
    one_style = len(by_style) == 1
    rows = [r[:4] if one_style else r for r in merged[:cap]]
    out.update({"segments": len(merged), "returned": len(rows),
                "columns": ["x1", "y1", "x2", "y2"] + ([] if one_style else ["color", "width_pt"]), "rows": rows})
    if one_style and by_style:
        out["style"] = list(by_style.keys())[0]
    if len(merged) > cap:
        out["note"] = "More segments than max_items - narrow with colors / width / region."
    return out


def _ducts_from_segments(segs_m, args, source):
    """segs_m: [(x1,y1,x2,y2)] in meters. Builds duct rows and (unless dry_run) creates them in Revit."""
    double = args.get("double_lines", True)
    step = float(args.get("step_mm") or 50)
    height = float(args.get("height_mm") or 300)
    is_round = bool(args.get("round"))
    min_len = float(args.get("min_length_m") or 0.3)
    merged = geom.merge_collinear(segs_m, tol=0.003)
    unpaired = []
    if double is False or str(double).lower() == "false":
        w = float(args.get("width_mm") or 300) / 1000.0
        lines = [tuple(s) + (w,) for s in merged]
    else:
        lines, unpaired = geom.pair_double_lines(merged, float(args.get("min_width_mm") or 80) / 1000.0,
                                                 float(args.get("max_width_mm") or 1600) / 1000.0)
    lines = geom.snap_ends(lines)
    rows, sizes = [], {}
    for l in lines:
        L = _len(l)
        if L < min_len:
            continue
        w = geom.round_size(l[4], step)
        if is_round:
            row = [round(l[0], 3), round(l[1], 3), round(l[2], 3), round(l[3], 3), w]
            label = "%d dia" % w
        else:
            row = [round(l[0], 3), round(l[1], 3), round(l[2], 3), round(l[3], 3), w, height]
            label = "%dx%d" % (w, height)
        rows.append(row)
        st = sizes.setdefault(label, [0, 0.0])
        st[0] += 1
        st[1] += L
    out = {"source": source, "input_segments": len(segs_m), "after_merge": len(merged),
           "ducts": len(rows), "total_length_m": round(sum(_len(r) for r in rows), 2),
           "unpaired_lines": len(unpaired),
           "sizes": {"columns": ["size_mm", "count", "length_m"],
                     "rows": sorted(([k, v[0], round(v[1], 2)] for k, v in sizes.items()), key=lambda r: -r[2])}}
    if rows:
        xs = [r[0] for r in rows] + [r[2] for r in rows]
        ys = [r[1] for r in rows] + [r[3] for r in rows]
        out["extent_m"] = [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]
    dry = args.get("dry_run", True)
    if dry is True or str(dry).lower() == "true":
        out["dry_run"] = True
        out["sample_rows"] = rows[:8]
        out["note"] = ("Preview only - nothing created. Check the sizes / extent with the user (the extent should sit "
                       "inside the building - compare with list_grids). Then call again with dry_run=false.")
        return out
    created, results = 0, []
    for i in range(0, len(rows), 1400):
        payload = {"segments": rows[i:i + 1400], "duct_type": args.get("duct_type"),
                   "system_type": args.get("system_type"), "level": args.get("level")}
        if args.get("offset_m") is not None:
            payload["offset_m"] = args.get("offset_m")
        res = call_revit("POST", "/mep/ducts", payload)
        created += int(res.get("ducts_created") or 0)
        res.pop("duct_ids_sample", None)
        results.append(res)
    out["ducts_created"] = created
    out["revit"] = results if len(results) > 1 else results[0]
    return out


def pdf_to_ducts(args):
    segs, _texts, _info = _page(args.get("path"), args.get("page"))
    cal = _calibration(args, required=True)
    chosen = _filter(segs, args)
    if not chosen:
        raise RevitError("No lines match the colours / widths given. Run pdf_read mode=summary to see the line groups.")
    segs_m = [cal.seg(s) for s in chosen]
    if args.get("region"):
        segs_m = [s for s in segs_m if _in_region(s, args.get("region"))]
    out = _ducts_from_segments(segs_m, args, "pdf page %s" % (args.get("page") or 1))
    out["calibration"] = cal.describe()
    return out


def cad_to_ducts(args):
    res = call_revit("POST", "/cad/inspect", {"import_id": args.get("import_id"), "layers": args.get("layers") or [],
                                               "include_segments": True, "max_segments": 6000})
    segs = [tuple(s[:4]) for s in (res.get("segments") or [])]
    if not segs:
        raise RevitError("No segments on those layers. Check the layer names with inspect_cad.")
    if args.get("region"):
        segs = [s for s in segs if _in_region(s, args.get("region"))]
    out = _ducts_from_segments(segs, args, "cad %s layers %s" % (args.get("import_id"), args.get("layers")))
    if res.get("truncated"):
        out["warning"] = "The CAD had more than 6000 segments on those layers - use region to work in parts."
    return out


LOCAL = {"pdf_read": pdf_read, "pdf_to_ducts": pdf_to_ducts, "cad_to_ducts": cad_to_ducts}


def run_tool(name, arguments):
    """Returns a list of MCP content items."""
    tool = TOOL_INDEX.get(name)
    if tool is None:
        raise RevitError("Unknown tool: %s" % name)
    kind = tool.get("kind")
    if kind == "local":
        return [{"type": "text", "text": _dump(LOCAL[name](arguments or {}))}]
    if kind == "job":
        return [{"type": "text", "text": _run_job(tool, arguments)}]
    if kind == "image":
        return _run_image(tool, arguments)
    payload = arguments if tool["method"] == "POST" else None
    if tool["method"] == "POST" and payload is None:
        payload = {}
    return [{"type": "text", "text": _dump(call_revit(tool["method"], tool["path"], payload))}]


# --------------------------------------------------------------------------- MCP protocol
def _result(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


_ICON_CACHE = []


def _server_icons():
    """Emperor icon for the client (MCP serverInfo.icons). Empty when the file is missing."""
    if not _ICON_CACHE:
        icons = []
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            icons.append({"src": "data:image/png;base64," + data, "mimeType": "image/png", "sizes": ["256x256"]})
        except Exception:
            pass
        _ICON_CACHE.append(icons)
    return _ICON_CACHE[0]


def handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return _result(mid, {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": dict({"name": SERVER_NAME, "title": "Emperor-Revit", "version": SERVER_VERSION,
                                "websiteUrl": "https://www.linkedin.com/in/yahya-morcy/"},
                               **({"icons": _server_icons()} if _server_icons() else {})),
            "instructions": "Tools for the Revit project open on the user's PC (Emperor plugin). "
                            "Save tokens: start with session_brief (it includes the saved project memory: model facts, the "
                            "user's standards and notes); save every project rule the user states with project_memory "
                            "action=set. Prefer summarize_elements / model_check over long element lists, ask query_elements "
                            "only for the parameters you need, keep view_snapshot small. For PDFs use pdf_read (vectors, not "
                            "images) and pdf_to_ducts / cad_to_ducts so coordinates never pass through the chat. Use dry_run "
                            "first for big changes and save scripts that worked with save_script. Lists come as "
                            "{columns, rows} tables. Tools marked MODIFIES THE MODEL need the user's confirmation first.",
        })
    if method == "ping":
        return _result(mid, {})
    if method == "tools/list":
        return _result(mid, {"tools": tool_list()})
    if method == "tools/call":
        try:
            content = run_tool(params.get("name"), params.get("arguments"))
            return _result(mid, {"content": content, "isError": False})
        except RevitError as ex:
            return _result(mid, {"content": [{"type": "text", "text": str(ex)}], "isError": True})
    if mid is None:
        return None  # notification (e.g. notifications/initialized) - no reply
    return _error(mid, -32601, "Method not found: %s" % method)


def main():
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    log("started")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        try:
            reply = handle(msg)
        except Exception as ex:  # never crash the server
            log("error: %s" % ex)
            reply = _error(msg.get("id"), -32603, str(ex)) if msg.get("id") is not None else None
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
