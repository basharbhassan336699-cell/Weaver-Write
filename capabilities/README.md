# capabilities/ — capability layer for Weaver Write

Structure mirrors the Claude pattern: three clear layers + supporting components.

## Language policy

- **Code, comments, docstrings, README, tool/skill descriptions** → English
- **System prompts** (`system_prompts/`) → Arabic (they steer the model's Arabic output)
- **Content templates** → bilingual (`*_ar` / `*_en`)
- **Triggers** → bilingual (Arabic + English) so any task in any language matches
- **Output-facing strings** (e.g. the "المراجع"/"References" heading) → switch by task language

## Structure

```
capabilities/
├── __init__.py              ← CapabilityRegistry (central index)
├── README.md
│
├── tools/                   ← Layer 1: programmed tools
│   ├── __init__.py          ← BaseTool + ToolResult (unified interface)
│   ├── registry.json        ← tool registry (name, description, triggers, layers)
│   ├── tool_academic_search.py
│   ├── tool_web_extract.py
│   ├── tool_doc_read.py
│   ├── tool_credibility_check.py
│   ├── tool_memory_store.py
│   └── tool_doc_export.py
│
├── skills/                  ← Layer 2: skills (each skill a folder)
│   └── <skill>/
│       ├── SKILL.md         ← instructions + frontmatter (description, triggers)
│       ├── scripts/         ← skill scripts
│       └── templates/       ← ready templates (bilingual)
│
├── libraries/               ← Layer 3: library documentation
│   └── registry.json        ← name, purpose, using tools
│
├── system_prompts/          ← system instructions (Arabic — one file per context)
│   ├── main.md
│   ├── layer_understand.md
│   ├── layer_write.md
│   ├── layer_verify.md
│   └── layer_humanize.md
│
├── scripts/                 ← shared general scripts
│   ├── citation_validator.py
│   ├── to_pdf_preview.py
│   └── structure_validator.py
│
└── templates/               ← shared general templates
```

## How it works (same principle as Claude)

1. The system creates `CapabilityRegistry()` and calls `load_all()`
2. It reads every tool description (from registry.json) and skill (from SKILL.md)
3. On an incoming task: it matches the task text against each capability's `triggers`
4. It invokes the tool via its unified `run()`, or opens the full `SKILL.md`

## Layers and pipeline wiring

| Layer | Available capabilities |
|-------|------------------------|
| 2 (input) | doc_read, web_extract |
| 4 (search) | academic_search, web_extract, memory_store |
| 5 (credibility) | credibility_check |
| 6 (writing) | skills: research_intro, literature_review... |
| 6.5 (humanize) | arabic_rewriter, english_rewriter |
| 7 (verify) | academic_search (verify mode) |
| 8 (export) | doc_export → docx/pptx/xlsx/pdf_builder |
| 8 (office) | word, powerpoint, excel, pdf (via office-core) |
| 2 (input) | pdf (tables/OCR), doc_read |

## Office tools (office-core)

Four additional tools wrap the vendored office libraries:

| Tool | Build | Read | Special |
|------|-------|------|---------|
| word | python-docx / docx(JS) | markitdown / mammoth | RTL |
| powerpoint | python-pptx / pptxgenjs | markitdown | Kufyan font |
| excel | openpyxl | openpyxl / pandas | SUM formulas |
| pdf | pypdf / reportlab | pdfplumber | tables + OCR (no GPU) |

Vendored libraries live in `engines/office-core/vendored/` and load without
a system install (Termux-friendly). Heavy libraries (pandas, pandoc, pypdf,
reportlab, python-docx, python-pptx) come via
`engines/office-core/requirements.txt`.

## Script maturity

- **Working**: format_apa.py, rewrite_ar.py, rewrite_en.py, build_docx.py,
  citation_validator.py, to_pdf_preview.py, structure_validator.py
- **Scaffolds with a stable interface**: the rest (ready to fill in without
  changing the interface)
