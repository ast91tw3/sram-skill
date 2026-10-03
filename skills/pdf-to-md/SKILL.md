---
name: pdf-to-md
description: >-
  Convert a PDF to Markdown before Claude reads it — avoids multi-image PDF
  token cost, cuts token usage 50-70%. Outputs a .md file alongside the PDF
  and returns the path for Claude to Read instead.
  Triggers: pdf, parse pdf, read pdf, translate pdf, pdf to markdown, pdf to md,
  解析PDF, 翻譯PDF, PDF轉MD, 讀PDF.
---

# pdf-to-md — PDF → Markdown (token-efficient)

**Why use this instead of reading the PDF directly:**
Claude converts each PDF page to an image internally → pays image tokens + text tokens.
Converting to Markdown first cuts token cost 50–70% and speeds up every subsequent read.

## Usage

Invoke this skill before reading any PDF:

```
/pdf-to-md <pdf_path>
```

Or ask: "先把這個 PDF 轉成 MD" / "parse this PDF to markdown" / "translate PDF before reading"

## What this skill does

1. **Checks** markitdown is installed (`pip install markitdown[pdf]` if missing)
2. **Converts** the PDF to Markdown using markitdown
3. **Saves** the output as `<same_name>.md` in the same folder as the PDF
4. **Returns** the `.md` file path — Claude then uses `Read` on that file, not the PDF

## Rules

- Always run this skill before `Read`-ing a PDF, unless the user explicitly wants raw PDF
- If the PDF is already converted (`.md` exists and is newer than the PDF), skip conversion and return the existing `.md` path
- Preserve the original PDF — never delete or overwrite it
- If conversion fails, fall back to native `Read` on the PDF and warn about token cost
- For multi-PDF jobs, convert all first, then read in sequence

## Execution steps (follow exactly)

### Step 1 — Check / install markitdown

```python
import importlib.util
if importlib.util.find_spec('markitdown') is None:
    import subprocess, sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'markitdown[pdf]', '-q'])
```

Run via `PowerShell` or `Bash`.

### Step 2 — Check if up-to-date .md already exists

```python
import os
pdf_path = r'<PDF_PATH>'           # absolute path
md_path  = os.path.splitext(pdf_path)[0] + '.md'

if os.path.exists(md_path) and os.path.getmtime(md_path) >= os.path.getmtime(pdf_path):
    print(f'SKIP: {md_path} is up to date')
else:
    print('CONVERT')
```

If `SKIP`: return `md_path` to Claude. If `CONVERT`: proceed to Step 3.

### Step 3 — Convert

```python
from markitdown import MarkItDown
md = MarkItDown()
result = md.convert(pdf_path)
with open(md_path, 'w', encoding='utf-8') as f:
    f.write(result.text_content)
print(f'OK: {md_path}  ({len(result.text_content):,} chars)')
```

### Step 4 — Report and hand off

After successful conversion, respond with:

```
PDF → MD 完成
路徑: <md_path>
大小: <chars> chars  (~<tokens> tokens，原 PDF 估計節省 ~<savings>%)
```

Token estimate: `chars / 4` ≈ tokens.
Savings estimate: PDFs average 2.5× the token cost of equivalent Markdown → savings ≈ 60%.

Then immediately `Read` the `.md` file instead of the PDF.

## Inline one-liner (for quick use in other skills/TL)

```python
from markitdown import MarkItDown; import os
pdf = r'<PATH>'
out = os.path.splitext(pdf)[0] + '.md'
MarkItDown().convert(pdf).text_content  # assign to var or write to out
```
