---
name: emperor-revit-skills
description: Work in the Revit project open on this PC through the Emperor connector (Emperor-Revit tools) - reading, checking, modeling, tagging, exporting. Use for any request about Revit, the open model, MEP / HVAC elements, sheets, views or the Emperor plugin.
---

# Emperor Revit Skills

The `Emperor-Revit` MCP tools talk to the Revit project open on the user's PC (Emperor plugin for
pyRevit). This skill is the playbook: how to get answers with few calls and few tokens, and how to
follow the user's company rules.

## Start of every Revit task

1. Call `session_brief` once. It returns the project memory (model facts, the user's saved standards
   and notes), the access switches and **company_standards** - the company's own naming rules.
2. If company_standards says "Not learned yet", call `learn_standards` (action=learn) once, then use its
   summary. Never ask the user for rules the summary already shows.
3. Write access / scripting access OFF? Tell the user which switch to turn on in Emperor > Claude
   Connector; do not try to work around it.

## Follow the company's rules (learned, never assumed)

- Names you create (filters, views, view templates, sheets, systems, parameters) follow
  company_standards: same prefix and separator, same case, same sheet-number pattern
  (`#` digit, `A` letter, `*` varies).
- Reuse the duct / pipe / tag types the company already uses before anything else.
- When the user states a rule ("supply ducts are GI", "filters start with ABC_"), save it:
  `learn_standards` action=set key=... value=... (company-wide) or `project_memory` action=set
  (this project only).
- These rules stay on the user's PC. Never copy them into code comments, files you share, or answers
  for other companies.

## Save tokens

- Prefer one-call tools over element lists: `summarize_elements` (counts / sums grouped by
  parameters), `model_check` (open connectors, no system, zero flow), `project_memory`.
- `query_elements`: always filter (category + level or in_active_view) and ask only for the
  parameters you need. Never pull whole categories "to have a look".
- `view_snapshot`: only when the user must see something; keep the default small size.
- PDFs / CAD: `pdf_read`, `pdf_to_ducts`, `cad_to_ducts` - coordinates never pass through the chat.
- Repeated work: use the HVAC tools (`tag_view`, `add_insulation`, `size_ducts`) or a saved script
  (`list_scripts`, `run_saved_script`) before writing new code. When new code worked, `save_script`.
- Do not repeat tool output back to the user; give the result in a few lines or a small table.

## Changing the model safely

- Big or uncertain changes: run with `dry_run` first, show what would change, then run for real.
- Every change is one undo step in Revit; say so when the user worries.
- `run_revit_script` is IronPython 2.7 inside Revit - see references/revit-api-notes.md.
- If a call returns a job_id, Revit is busy (dialog open or command running): wait, then call
  `job_result`; never send the same change twice.

## Reference files (read only when needed)

- `references/recipes.md` - ready ways to do common HVAC / BIM tasks with the Emperor tools.
- `references/revit-api-notes.md` - IronPython 2.7 + Revit 2024/2025 API pitfalls for scripts.
