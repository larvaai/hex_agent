---
name: hs-mem:document-skills
description: Create, edit, and analyze office files (.docx, .pdf, .pptx, .xlsx). Use to read content, create new files, edit with tracked changes, fill forms, or extract data from Word, PDF, PowerPoint, or Excel.
category: mem
license: AGPL-3.0
keywords: [document-skills, create, edit, analyze, office, files]
when_to_use: "Use to read content, create new files, edit with tracked changes, fill forms, or extract data from Word, PDF, PowerPoint, or Excel."
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit]
argument-hint: "[docx|pdf|pptx|xlsx] [create|edit|extract|analyze]"
metadata:
  owner: harness
  compliance-tier: knowledge
---

# hs-mem:document-skills — office document operations

This skill provides processes and techniques for 4 common document formats.
No fake code; no invented APIs — every technique has a real tool behind it.

## Quick routing

| Format | Primary tasks | Reference drawer |
|---|---|---|
| `.docx` | Create, edit XML, redline | `references/docx.md` |
| `.pdf` | Extract, merge, fill forms | `references/pdf.md` |
| `.pptx` | Create slides, edit templates, thumbnails | `references/pptx.md` |
| `.xlsx` | Data analysis, formulas, formatting | `references/xlsx.md` |

## Boundaries

- Do NOT invent library names or script paths that have not been verified.
- Do NOT reference skill paths outside the harness at runtime — the harness is self-contained.
- If an operation exceeds the scope of one drawer -> suggest using `hs-mem:docs` (project documentation) or
  `hs-create:skill-creator` (packaging a dedicated tool).

## General process

1. **Identify format and task** — if the user is unclear, ask: what file type, read/create/edit?
2. **Load the drawer** — open `references/<format>.md` and read the decision tree.
3. **Check tool availability** — run `which pandoc`, `python -c "import pypdf"`, etc.
   before writing code.
4. **Implement** — follow the process in the drawer; use the appropriate CLI/Python/JS tool.
5. **Verify** — after creating or editing the file: reopen it, check the content, fix any errors.
6. **Code style** — concise code, no unused variables, no unnecessary print statements.

## When to stop and ask

- User has not specified the format -> ask immediately, do not guess.
- Required tool is not installed -> report the install command, do not proceed.
- Complex operation (legal redline, mail-merge, VBA macro) -> confirm scope
  before starting.

## Quick reference drawers

| Drawer | Content |
|---|---|
| `references/docx.md` | Create (python-docx), edit OOXML, redline workflow, text extraction |
| `references/pdf.md` | pypdf/pdfplumber, reportlab, qpdf CLI, OCR, form filling |
| `references/pptx.md` | python-pptx create/edit slides, templates, image rendering |
| `references/xlsx.md` | pandas / openpyxl, formulas, color-coding, recompute |
