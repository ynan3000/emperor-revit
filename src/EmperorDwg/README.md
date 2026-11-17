# EmperorDwg – source of `lib/dwg/EmperorDwg_1_1.dll`

The DLL is used only by **Emperor Exporter > DWG > "Bind images as OLE"** (Revit 2025 and newer, .NET 8).
It replaces the linked raster images of an exported DWG with embedded OLE pictures.

It is one assembly made of:

| Part | Where | License |
|------|-------|---------|
| [ACadSharp](https://github.com/DomCR/ACadSharp) 3.8.51, commit `0acbe974b865afb5ff3b256d5e13a6862574c438` | cloned by the build script | MIT (`lib/dwg/ACadSharp-LICENSE.txt`) |
| Emperor's patch to ACadSharp (3 small fixes, each marked `Emperor patch`) | `acadsharp-emperor.patch` | MIT |
| Emperor's own code (`ImageBinder`, `OleImage`, `Cfb`) | `Emperor/` | MIT |

The patch:
- a layout keeps the order of its viewport list when the drawing is written back (the first viewport stands
  for the paper; a changed order hides the drawing);
- the upper limits of a layout are written (the lower limits were written twice);
- an OLE frame placed in paper space is marked as a paper space object.

## Build
Needs `git` and the .NET 8 SDK (or newer), with access to nuget.org.

    # Windows
    .\build.ps1
    # Linux / macOS
    ./build.sh

The script clones ACadSharp at the commit above, applies the patch, adds `Emperor/`, and builds
`ACadSharp.csproj` for `net8.0` with the assembly name `EmperorDwg_1_1`. Copy the resulting
`EmperorDwg_1_1.dll` to `lib/dwg/`.

The version is in the file name on purpose: a newer Emperor ships a file with a new name, so it can be loaded
in a Revit session that already loaded an older one.
