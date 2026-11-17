EmperorDwg_1_1.dll - used by Emperor Exporter > DWG > "Bind images as OLE".

It contains:
  * ACadSharp 3.8.51 (https://github.com/DomCR/ACadSharp), MIT License - see ACadSharp-LICENSE.txt.
    Reads and writes DWG files. Built for .NET 8 (Revit 2025 and newer) with three small changes,
    all marked "Emperor patch" in the source:
      - a layout keeps the order of its viewport list when the drawing is written back
        (the first viewport of the list stands for the paper; a changed order hides the drawing);
      - the upper limits of a layout are written (the lower limits were written twice);
      - an OLE frame placed in paper space is marked as a paper space object.
  * EmperorDwg (Emperor's own code): replaces the linked raster images of a DWG with embedded
    OLE pictures.

The file name carries the version on purpose: a newer Emperor ships a file with a new name, so it can
be loaded in a Revit session that already loaded the older one.

Source code: src/EmperorDwg/ in the repository (https://github.com/ynan3000/emperor-revit/tree/main/src/EmperorDwg),
with build scripts (build.ps1 / build.sh).
