# Recipes (Emperor tools)

Each recipe = the fewest calls that do the job. Names below are Emperor-Revit tool names.

## Check a model / a level
1. `model_check` (level=... or in_active_view=true) -> counts + a few ids per problem.
2. Only if the user wants to see them: `view_snapshot` with element_ids, or select them
   (`run_revit_script`: `uidoc.Selection.SetElementIds(...)`).

## Quantities / schedules in chat
- `summarize_elements` category='Ducts', group_by=['System Type','Size'], sum=['Length'].
- Pipes, fittings, terminals the same way. Group by 'Level' for per-floor tables.

## Model ducts from a PDF or CAD drawing
1. `pdf_read` (or `inspect_cad`) to find the drawing scale / layers.
2. `pdf_to_ducts` / `cad_to_ducts` with preview first, then create. Use the company duct type and
   system names from company_standards.

## Size ducts
`size_ducts` with the target velocity, preview first, then apply.

## Tags
`tag_view` per category (ducts, terminals, duct_accessories ...). It skips tagged elements, avoids
overlaps and uses the spots the user taught Smart Tag ("Learn from my changes"). Use the company's tag
types from company_standards.

## Insulation
`add_insulation` with rules per system (thickness can depend on size: "50:25, 150:40, 50").

## Views, filters, sheets
- Filter / view / sheet names: company prefix + separator, same case, same sheet-number pattern.
- System filters in Emperor style: one filter per system, rule "System Type equals ...".

## Export
`export_sheets_dwg` for DWG. PDFs with black lines: tell the user to use Emperor Exporter
("Black lines in PDF" uses the "Emperor Export" filter and undoes it after each file).

## Rooms and spaces
Emperor Room & Space Manager (ribbon) creates spaces from host / linked rooms per level, matches
height and names; prefer pointing the user to it for bulk work.
