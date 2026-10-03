# sram-skill

SRAM engineering skills for Claude Code / Orca.

## Skills

| Skill | Trigger | Description |
|---|---|---|
| `pdf-to-md` | `/pdf-to-md <path>` | Convert PDF → Markdown before Claude reads it. Cuts token cost ~60%. Uses markitdown (Microsoft). |

## Install

```powershell
Copy-Item "skills\*" "$env:USERPROFILE\.claude\commands\" -Recurse -Force
```

Or copy individual skill `.md` files to `~/.claude/commands/`.

## Requirements

```powershell
pip install markitdown[pdf]
```
