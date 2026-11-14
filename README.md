# Emperor for Revit

Free Revit toolkit for engineers - and especially mechanical (HVAC) engineers - built on pyRevit.
One **Emperor** tab with the tools below. Full user guide: `docs/Emperor_Instructions.html`
(also the **Help > Instructions** button in Revit).

| Panel        | Tools |
|--------------|-------|
| HVAC         | Grille Align, Horizontal Align, Vertical Align, Diffuser Array, Smart Insulation, Smart Tag |
| Views        | View Manager, System Box, Crop to 3D |
| Room & Space | Room & Space Manager |
| Links        | Link Manager |
| Import       | Excel to Drafting |
| Export       | Emperor Exporter (PDF, DWG with images bound as OLE, DXF, DGN, DWF, IFC, NWC, images) |
| Claude       | Claude Connector (talk to your Revit model from Claude Desktop) |
| Toggles      | Shortcut Guard, Sync Views |
| Help         | Instructions |

## Requirements
- Autodesk Revit with [pyRevit](https://github.com/pyrevitlabs/pyRevit) installed.
- Tested on **Revit 2025** with pyRevit 7. "Bind images as OLE" in the Exporter needs Revit 2025 or newer.
- Claude Connector: Claude Desktop. Emperor downloads its own private Python once (official embeddable
  build from python.org, ~11 MB, not installed on Windows).

## Install
1. Download `Emperor_v<version>.zip` from the latest release: https://github.com/ynan3000/emperor-revit/releases/latest
   (the ZIP holds the full source code of every tool)
2. Close Revit.
3. Extract the ZIP into your pyRevit extensions folder, so you get `<extensions folder>\Emperor.extension\Emperor.tab\...`
4. Start Revit (or pyRevit > Reload).


## What is new
See [CHANGELOG.md](CHANGELOG.md).

## License
Free for everyone under the [MIT License](LICENSE): use it, change it and share it - keep the copyright
notice with my name. The DWG library in `lib/dwg/` contains ACadSharp (MIT License, see `lib/dwg/ACadSharp-LICENSE.txt`).

## Author
Yahya Morcy  
LinkedIn: https://www.linkedin.com/in/yahya-morcy/  
Phone: +20 106 506 1251
