# Changelog

## v1.6.3
- **Newer Revit versions**: every place that read an element id now uses pyRevit's own helper
  (`ElementId.Value` on Revit 2024+, `IntegerValue` on older), including Excel to Drafting pictures, which could
  fail on Revit 2026. Grille Align no longer falls back to the old `DisplayUnitType` API. The code passes
  pyRevit's Revit API compatibility checker (Revit 2021-2027) with no errors or warnings.
- **Source of the DWG library**: `src/EmperorDwg/` holds the code of `lib/dwg/EmperorDwg_1_1.dll`
  (ACadSharp 3.8.51 + Emperor's patch + Emperor's own code) and scripts to rebuild it.
- Every button now has an `en_us` title and tooltip and a help link to its section on the website.
- `extension.json` lists the repository `url` and the website.
- README explains everything Emperor does when Revit starts (Claude Connector auto-connect) and how to turn it off.

## v1.6.2
- **Emperor Exporter 3.2.1 - Black lines in PDF** now covers whole sheets: drafting views and legends (general
  notes, legend symbols, line styles coloured in the view) print black, and coloured text and dimensions print
  black. Pictures and coloured fills keep their colours. Everything is undone after each file, as before.

## v1.6.1
- **View Manager 1.1**: levels that already have a view - tick Skip, Rename the existing view, or Create a new
  view (no more question for every level). New **Separator** box (default "-") between prefix, level name and
  suffix. Settings of View Manager 1.0 are carried over ("Ask me" becomes Skip).

## v1.6.0
- **Emperor Exporter 3.2 - DWG: "Bind images as OLE"** (Formats tab > DWG > Images). Title block logos and
  other pictures are stored inside the exported DWG as OLE objects and the separate image files are deleted -
  one file per sheet, no image references. AutoCAD is not needed. Revit 2025 and newer.
  Uses ACadSharp (MIT License, see `lib/dwg/`).

## v1.5.1
- **Shortcut Guard** now really starts with Revit when it was left ON. On Revit 2025 it failed while Revit
  was loading and had to be clicked again in every session.

## v1.5.0
- **View Manager** (Views panel): plan views per level with prefix / suffix, several view types at once,
  skip / rename / ask for levels that already have a view, templates for new views and for ticked views.
- HVAC tools (Grille / Horizontal / Vertical Align, Diffuser Array) no longer use `ElementId.IntegerValue`,
  which Revit 2026 removed.
- Claude Connector 1.6.1: a request that timed out because Revit was busy is taken back instead of
  running later.
- Smart Insulation: the library file is plain ASCII again (a stray character could stop it from loading).
- Removed the unused `lib/grille_align_core.py`.
