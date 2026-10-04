# sram-skill

SRAM engineering skills for Claude Code / Orca.

## Skills

| Skill | Trigger | Description |
|---|---|---|
| `pdf-to-md` | `/pdf-to-md <path>` | Convert PDF → Markdown before Claude reads it. Cuts token cost ~60%. Uses markitdown (Microsoft). |
| `3d-printing` | auto (3D print, material, slicer settings, failed print) | FDM guidance for a Bambu Lab X1 Carbon: design-for-print rules, materials, slicer starting points, troubleshooting, plus `stl_check.py` (offline STL printability pre-check). Starting values, not guarantees. |
| `bambu-x1` | auto (printer status, AMS, upload, start/stop) | LAN control of a Bambu X1C over MQTT/FTPS: read-only status incl. AMS, G-code safety validation, upload, pause/resume/cancel, and a human-gated print start. **Not verified on real hardware.** Needs `pip install paho-mqtt`; credentials only via environment variables. |
| `Eng_2D_analysis` | auto (2D drawing, GD&T, title block) | Skill for the separate repo [Eng_2D_analysis](https://github.com/ast91tw3/Eng_2D_analysis): parse vector-PDF engineering drawings to JSON, draft, reverse to 3D. Replace `<PROJECT_ROOT>`/`<PYTHON>` in `SKILL.md` after cloning that repo. Validated only on a few same-source drawings; generalisation unmeasured. |

## Install

Folder skills (`skills/<name>/SKILL.md`) go in `~/.claude/skills/<name>/`:

```powershell
Copy-Item "skillsd-printing","skillsambu-x1","skills\Eng_2D_analysis" "$env:USERPROFILE\.claude\skills\" -Recurse
```

Slash-command style (single `.md`, e.g. `pdf-to-md`) goes in `~/.claude/commands/`:

```powershell
Copy-Item "skills\pdf-to-md\SKILL.md" "$env:USERPROFILE\.claude\commands\pdf-to-md.md"
```

Start a new Claude Code session afterwards so the skills are picked up.

## Requirements

```powershell
pip install markitdown[pdf]   # pdf-to-md
pip install paho-mqtt           # bambu-x1
```
`Eng_2D_analysis` needs PyMuPDF (Parser) and, for drafting, `ezdxf` and FreeCAD `freecadcmd`.
