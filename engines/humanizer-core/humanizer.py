"""
engines/humanizer-core/humanizer.py — synonym-based humanization (working)
==========================================================================
Reduces AI-signature phrasing by replacing flagged words/phrases with more
human alternatives, drawing on a large bundled dictionary:

  AI_WORDS_EN (550)  / AI_WORDS_AR (131)   — AI-signature -> human options
  GENERAL_EN  (~95K) / GENERAL_AR (~9.6K)  — general synonyms for variety
  WORDNET_EXTRA_EN (~4.9K)                 — extra English synonyms

Design goals:
  - AI-signature terms are replaced FIRST and most aggressively (they're the
    real "tells"); general synonyms are applied lightly for variety.
  - Longest phrases match before single words (so "it is important to note
    that" is handled before "important").
  - Deterministic-but-varied: a seeded RNG picks among options so reruns are
    stable yet the text isn't monotone.
  - CITATIONS ARE NEVER TOUCHED: callers pass already-protected text (with
    placeholder tokens) — see rewrite_ar.py / rewrite_en.py.

This module does the replacement; the skill scripts handle citation
protection and integrity checks around it.
"""
from __future__ import annotations
import os
import re
import random

_DIR = os.path.dirname(os.path.abspath(__file__))
_dicts = {"AI_WORDS_EN": {}, "AI_WORDS_AR": {}, "GENERAL_EN": {},
          "GENERAL_AR": {}, "WORDNET_EXTRA_EN": {}}
_loaded = False


def _load():
    global _loaded
    if _loaded:
        return
    import importlib.util
    path = os.path.join(_DIR, "dictionary.py")
    spec = importlib.util.spec_from_file_location("hz_dictionary", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k in _dicts:
        _dicts[k] = getattr(mod, k, {}) or {}
    _loaded = True


def _pick(options, rng):
    """Pick a non-empty replacement; allow '' (deletion) only sometimes."""
    opts = [o for o in options if isinstance(o, str)]
    if not opts:
        return None
    choice = rng.choice(opts)
    return choice


def _replace_phrases(text, table, rng, rate=1.0, lang="en"):
    """
    Replace keys of `table` found in `text` with a chosen synonym.
    Longest keys first. `rate` in [0,1] is the probability of replacing a
    given match (1.0 = always, for AI words; lower for general variety).
    Case-insensitive matching for Latin; the replacement preserves the
    original's leading capitalization.
    """
    if not table:
        return text
    keys = sorted(table.keys(), key=len, reverse=True)
    is_arabic_lang = (lang == "ar")

    for key in keys:
        if not key:
            continue
        repl = _pick(table[key], rng)
        if repl is None:
            continue

        latin_key = bool(re.fullmatch(r"[A-Za-z' -]+", key))
        # Arabic dictionaries only apply to Arabic text and vice-versa
        if is_arabic_lang and latin_key:
            continue
        if not is_arabic_lang and not latin_key:
            continue

        if latin_key:
            # word-boundary + case-insensitive for Latin
            pattern = re.compile(r"\b" + re.escape(key) + r"\b", re.IGNORECASE)
        else:
            # Arabic: match with boundaries that respect Arabic letters
            # (avoid replacing inside a longer word)
            pattern = re.compile(r"(?<![\u0600-\u06FF])" + re.escape(key) +
                                 r"(?![\u0600-\u06FF])")

        def _sub(m):
            if rng.random() > rate:
                return m.group(0)
            original = m.group(0)
            # preserve leading capital for Latin
            if latin_key and original[:1].isupper() and repl:
                return repl[:1].upper() + repl[1:]
            return repl

        text = pattern.sub(_sub, text)
    return text


def humanize(text, lang="ar", seed=42, general_rate=0.25, file_type="docx",
             clean_fingerprints=True):
    """
    Humanize `text`:
      1) clean AI visual/linguistic fingerprints (dashes, decorative symbols,
         language-mix glitches) — file-type aware (skipped for pptx visuals),
      2) replace AI-signature words/phrases (always) — curated, reliable,
      3) apply general-synonym variety (general_rate, ON by default).
    Citations must already be protected by the caller. Returns new text.
    (Use humanize_report() to also get the list of issues found.)
    """
    return humanize_report(text, lang, seed, general_rate, file_type,
                           clean_fingerprints)["text"]


def humanize_report(text, lang="ar", seed=42, general_rate=0.25,
                    file_type="docx", clean_fingerprints=True):
    """Same as humanize() but returns {"text", "issues", "tells"}."""
    _load()
    rng = random.Random(seed)
    issues, tells = [], []

    # 1) fingerprint cleaning (visual + language-mix), file-type aware
    if clean_fingerprints:
        try:
            import os, sys
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            from text_cleaner import clean_text
            c = clean_text(text, lang=lang, file_type=file_type)
            text, issues, tells = c["text"], c["issues"], c["tells"]
        except Exception:
            pass

    # 2) + 3) synonym replacement
    if lang == "ar":
        text = _replace_phrases(text, _dicts["AI_WORDS_AR"], rng, rate=1.0, lang="ar")
        if general_rate > 0:
            text = _replace_phrases(text, _dicts["GENERAL_AR"], rng,
                                    rate=general_rate, lang="ar")
    else:
        text = _replace_phrases(text, _dicts["AI_WORDS_EN"], rng, rate=1.0, lang="en")
        if general_rate > 0:
            text = _replace_phrases(text, _dicts["WORDNET_EXTRA_EN"], rng,
                                    rate=general_rate, lang="en")
            text = _replace_phrases(text, _dicts["GENERAL_EN"], rng,
                                    rate=general_rate * 0.5, lang="en")
    return {"text": text, "issues": issues, "tells": tells}


def stats():
    _load()
    return {k: len(v) for k, v in _dicts.items()}


if __name__ == "__main__":
    print("Dictionary sizes:", stats())
    demo_en = "It is important to note that the implications are far-reaching."
    demo_ar = "يُعدّ هذا الموضوع مهماً، وعلاوة على ذلك فإنه يمثل تحدياً."
    print("EN:", demo_en, "->", humanize(demo_en, "en"))
    print("AR:", demo_ar, "->", humanize(demo_ar, "ar"))
