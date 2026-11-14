# Changelog

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
