# Expert Prompt Library (21 prompts)

Research-backed prompts for humanization and AI-detection, all in English and
designed to work for BOTH Arabic and English tasks.

## Categories
- **humanization/** (7) — HUMAN-01..07: rewrite text to remove AI fingerprints
  (HUMAN-06 is Turnitin-grade; HUMAN-04 targets flagged vocabulary).
- **detection/** (4) — DETECT-01..04: detect AI text (7-criteria, model id).
- **system/** (3) — SYS-01..03: system prompts (academic writer, detector).
- **pipeline/** (2) — PIPE-01..02: full detect+humanize (PIPE-02 is EN+AR).
- **knowledge/** (5) — KNOW-01..05: reference knowledge (citation methods...).

## Usage
`prompt_library.py`:
- `get_prompt(id)` — full text by id
- `get_humanization_prompt(level)` — basic/standard/vocabulary/rebuild/...
- `get_detection_prompt(depth)` — quick/deep/model/conclusion
- `list_prompts(category?)` — index

44 research-flagged AI-marker words (delve, robust, pivotal, leverage...) were
also extracted into engines/humanizer-core/banned_words_en.json and are
replaced automatically by the text cleaner.

Sources: COLING 2025, ICLR 2024, GPTZero, Turnitin patterns, Kobak et al.
Science Advances 2024.
