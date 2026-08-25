"""
capabilities/prompts/prompt_library.py — prompt library loader (working)
========================================================================
Loads the bundled expert prompts (humanization, AI-detection, knowledge,
system, pipeline) so the pipeline can pull a ready professional prompt by id
instead of hardcoding one.

All prompts are in English and designed to work for BOTH Arabic and English
tasks (several are explicitly bilingual, e.g. PIPE-02, KNOW-05).

Categories:
  humanization/  HUMAN-01..07  — rewrite text to remove AI fingerprints
  detection/     DETECT-01..04 — detect AI-generated text (7-criteria etc.)
  system/        SYS-01..03    — system prompts (academic writer, detector)
  pipeline/      PIPE-01..02   — full detect+humanize pipelines (EN/AR)
  knowledge/     KNOW-01..05   — reference knowledge (citation methods, etc.)

Sources cited inside the prompts: COLING 2025, ICLR 2024, GPTZero, Turnitin
patterns, Kobak et al. Science Advances 2024.
"""
from __future__ import annotations
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
_CATEGORIES = ["humanization", "detection", "system", "pipeline", "knowledge"]


def list_prompts(category=None):
    """List available prompt ids, optionally filtered by category."""
    out = {}
    cats = [category] if category else _CATEGORIES
    for cat in cats:
        d = os.path.join(_DIR, cat)
        if os.path.isdir(d):
            out[cat] = sorted(f[:-4] for f in os.listdir(d) if f.endswith(".txt")
                              and not f.startswith("README"))
    return out


def get_prompt(prompt_id):
    """
    Fetch a prompt's full text by id (e.g. 'HUMAN-06...' or just 'HUMAN-06').
    Searches all categories. Returns the text, or '' if not found.
    """
    for cat in _CATEGORIES:
        d = os.path.join(_DIR, cat)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith(".txt") and (f[:-4] == prompt_id or f.startswith(prompt_id)):
                try:
                    with open(os.path.join(d, f), encoding="utf-8") as fh:
                        return fh.read()
                except Exception:
                    return ""
    return ""


def get_humanization_prompt(level="standard"):
    """Convenience: pick a humanization prompt by desired strength."""
    mapping = {
        "basic": "HUMAN-01",
        "standard": "HUMAN-06",       # Turnitin-grade academic humanization
        "vocabulary": "HUMAN-04",     # targeted AI-word replacement
        "rebuild": "HUMAN-02",        # full rebuild from ideas
        "burstiness": "HUMAN-03",     # inject sentence-length variation
        "voice": "HUMAN-05",          # add personal voice
    }
    return get_prompt(mapping.get(level, "HUMAN-06"))


def get_detection_prompt(depth="deep"):
    """Convenience: pick an AI-detection prompt."""
    mapping = {
        "quick": "DETECT-01",
        "deep": "DETECT-02",          # 7-criteria analysis
        "model": "DETECT-03",         # identify which AI model
        "conclusion": "DETECT-04",
    }
    return get_prompt(mapping.get(depth, "DETECT-02"))


if __name__ == "__main__":
    import json
    print("Available prompts:")
    print(json.dumps(list_prompts(), ensure_ascii=False, indent=2))
    print("\nHUMAN-06 length:", len(get_humanization_prompt("standard")), "chars")
    print("DETECT-02 length:", len(get_detection_prompt("deep")), "chars")
