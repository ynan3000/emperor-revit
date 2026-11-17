# Emperor for Revit – free pyRevit toolkit for MEP & HVAC engineers

[![Website](https://img.shields.io/badge/website-emperor--revit-b81c24)](https://ynan3000.github.io/emperor-revit/)
[![Download](https://img.shields.io/github/v/release/ynan3000/emperor-revit?label=download&color=b81c24)](https://github.com/ynan3000/emperor-revit/releases/latest)
[![YouTube](https://img.shields.io/badge/YouTube-12%20videos-red)](https://www.youtube.com/playlist?list=PLGEBasj0nHd8)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Emperor** is a free, open-source **pyRevit extension** (Revit add-in) with 16 tools for engineers – and especially
mechanical / **HVAC** engineers: grille align, diffuser array, smart duct and pipe insulation, smart tag without overlaps,
view manager, system box, crop to 3D, room & space manager, link manager, Excel to drafting view, a PDF / DWG exporter
that binds images inside the DWG, and a Revit connector for Claude.

إضافة مجانية ومفتوحة المصدر لـ Revit، لكل المهندسين وخصوصاً مهندسين الميكانيكا.

🌐 Website: https://ynan3000.github.io/emperor-revit/ · ▶ Videos: https://www.youtube.com/playlist?list=PLGEBasj0nHd8

![Emperor for Revit](https://ynan3000.github.io/emperor-revit/img/og.jpg)

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

Every tool has a short video: [Emperor for Revit playlist](https://www.youtube.com/playlist?list=PLGEBasj0nHd8).

## Requirements
- Autodesk Revit with [pyRevit](https://github.com/pyrevitlabs/pyRevit) installed.
- Tested on **Revit 2025** with pyRevit 7. "Bind images as OLE" in the Exporter needs Revit 2025 or newer.
- Claude Connector: Claude Desktop. Emperor downloads its own private Python once (official embeddable
  build from python.org, ~11 MB, not installed on Windows).

## What Emperor does when Revit starts
pyRevit runs Emperor's `startup.py` every time Revit starts (or pyRevit reloads). It never changes your
pyRevit settings. What it does:

- **Shortcut Guard / Sync Views** start only if you turned them ON (Toggles panel).
- **Claude Connector** – starts a small listener on `127.0.0.1` (this PC only, port 48890-48899) that the
  Emperor MCP server talks to. Claude can only *read* the model until you switch **Write access** ON.
- **Claude Connector auto-connect** (ON by default) – in the background, Emperor registers its MCP server
  with Claude so Revit shows up in Claude without any setup. This writes **outside** the extension folder:
  - adds an `Emperor-Revit` entry to `claude_desktop_config.json` (`%APPDATA%\Claude\`, or the Microsoft
    Store app folder) – only if Claude Desktop is installed;
  - if the entry was added or changed, **closes and reopens Claude Desktop** so it picks it up;
  - if Claude Code is installed: runs `claude mcp add --scope user Emperor-Revit ...` and copies the
    *Emperor Revit Skills* skill to `%USERPROFILE%\.claude\skills\`;
  - the first time only, if Emperor's private Python is not there yet: downloads the official embeddable
    Python 3.12 from python.org (~11 MB, kept only if signed by the Python Software Foundation) into
    `%LOCALAPPDATA%\Emperor\python\` – nothing is installed on Windows. This is the only network call;
  - keeps its own settings and logs in `%APPDATA%\Emperor\`.

  To stop it: **Emperor tab > Claude > Claude Connector** → untick
  *"Connect Claude automatically whenever Revit starts"*. Nothing is registered while it is unticked.

## Install
**With the pyRevit CLI:**

    pyrevit extend ui Emperor https://github.com/ynan3000/emperor-revit.git

**Or by hand:**
1. Download `Emperor_v<version>.zip` from the latest release: https://github.com/ynan3000/emperor-revit/releases/latest
   (the ZIP holds the full source code of every tool)
2. Close Revit.
3. Extract the ZIP into your pyRevit extensions folder, so you get `<extensions folder>\Emperor.extension\Emperor.tab\...`
4. Start Revit (or pyRevit > Reload).


## What is new
See [CHANGELOG.md](CHANGELOG.md).

## Source of the DWG library
`lib/dwg/EmperorDwg_1_1.dll` (used only by Exporter > DWG > "Bind images as OLE") is built from
[`src/EmperorDwg/`](src/EmperorDwg): ACadSharp 3.8.51 + a small patch + Emperor's own code.
Rebuild it with `src/EmperorDwg/build.ps1` (Windows) or `build.sh` – see [its README](src/EmperorDwg/README.md).

## License
Free for everyone under the [MIT License](LICENSE): use it, change it and share it - keep the copyright
notice with my name. The DWG library in `lib/dwg/` contains ACadSharp (MIT License, see `lib/dwg/ACadSharp-LICENSE.txt`).

## Author
Yahya Morcy  
LinkedIn: https://www.linkedin.com/in/yahya-morcy/  
Phone: +20 106 506 1251
