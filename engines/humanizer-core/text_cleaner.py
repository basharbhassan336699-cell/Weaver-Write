"""
engines/humanizer-core/text_cleaner.py — AI-fingerprint cleaner (working)
=========================================================================
Detects and removes the visual/linguistic "tells" of AI-generated text so
the output reads as human-written. This runs as part of the writing/rewrite
layer, silently (the user is never told it ran).

Two concerns, handled separately:

1) VISUAL SYMBOLS (file-type aware):
   - In Word/PDF (prose documents): em/en dashes, decorative bullets, arrows,
     stars, pipes, backticks, box-drawing chars are FORBIDDEN and get
     replaced/removed.
   - In PowerPoint: these are ALLOWED (slides legitimately use them), so the
     cleaner leaves them alone.
   - In Excel: left to context (light cleaning only).

2) LANGUAGE-MIX GLITCHES (all file types):
   - A Latin word spliced into Arabic text ("في حين Remains الوطن") or an
     Arabic letter spliced into a Latin word ("Caر", "بياناT"), or stray
     CJK characters dropped into Arabic/Latin text. These are detected and
     removed/flagged.

The dash logic follows the exact rules requested:
   "—"                      -> "-"
   "استخدم—اللغة"           -> "استخدم اللغة"   (glue between words -> space)
   "استخدم — اللغة"         -> "استخدم اللغة"   (spaced glue -> single space)
   "—في حين يبقى الوطن—"    -> "-في حين يبقى الوطن-"  (quote-like -> hyphen)
"""
from __future__ import annotations
import os
import re

# ── character classes ────────────────────────────────────────
_ARABIC = r"\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF"
_LATIN = r"A-Za-z"
_CJK = r"\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF"  # Chinese/Japanese/Korean

# Long dashes and box-drawing runs
_DASH_CHARS = "—–―"                    # em, en, horizontal bar
_BOX_CHARS = "─━═╌╍┄┅┈┉"              # box-drawing horizontals

# Decorative symbols forbidden in prose documents (Word/PDF)
# Decorative symbols forbidden in prose documents (Word/PDF)
# NOTE: « » (U+00AB/BB) are NOT here — they are legitimate Arabic quotation
# marks (used for hadith quotes and normal Arabic quoting), so they are kept.
_DECORATIVE = "★☆✓✗✦✧●◆◇■□▪▫➜➔➤"
_ARROWS = "→←↑↓↔⇒⇐⇔➜"
_BULLETS = "•·‣⁃"
_REPLACEMENT_JUNK = "\ufffd"           # � replacement character


def _clean_dashes(text: str) -> str:
    """Apply the requested dash rules to Arabic/Latin prose."""
    dash = f"[{re.escape(_DASH_CHARS)}]"
    box = f"[{re.escape(_BOX_CHARS)}]+"
    any_long = f"(?:{dash}|{box})"

    letter = f"[{_ARABIC}{_LATIN}]"

    # 1) spaced glue between two words:  word — word  -> word word
    text = re.sub(rf"({letter})\s*{any_long}\s*({letter})", r"\1 \2", text)

    # 2) quote-like wrapping:  —phrase—  ->  -phrase-
    #    (a long dash directly touching the start/end of a run of text)
    text = re.sub(any_long, "-", text)

    # 3) collapse any doubled hyphens/spaces produced above
    text = re.sub(r"-{2,}", "-", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def _clean_decorative(text: str) -> str:
    """Remove decorative symbols/arrows/stars/pipes/backticks from prose."""
    # pipes used as separators:  A | B | C  -> A، B، C  (Arabic) / A, B, C
    text = re.sub(r"\s*\|\s*", "، ", text)
    # backticks
    text = text.replace("`", "")
    # decorative sets
    for ch in _DECORATIVE + _ARROWS + _BULLETS + _REPLACEMENT_JUNK:
        text = text.replace(ch, "")
    # collapse spaces left behind by removed symbols, and trim line edges
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"(?m)^[ \t]+", "", text)
    text = re.sub(r"[ \t]+$", "", text)
    return text


def _fix_language_mix(text: str, lang: str) -> list:
    """
    Detect language-mix glitches. Returns a list of (span, kind) issues and a
    cleaned text. We remove:
      - CJK chars embedded in Arabic/Latin text (always junk here)
      - a single Arabic letter glued inside a Latin word ("Caر","بياناT")
    We FLAG (not auto-translate) whole Latin words inside Arabic prose,
    because deletion could drop meaning — those are reported for review,
    except obvious 1-2 char glue which is removed.
    """
    issues = []

    # remove stray CJK anywhere (not expected in AR/EN academic text)
    if re.search(f"[{_CJK}]", text):
        issues.append(("cjk", "stray CJK characters removed"))
        text = re.sub(f"[{_CJK}]+", "", text)

    # Arabic letter(s) gluing inside a Latin word:  Ca<ar>  or  <lat>بياناT
    #   -> strip the foreign letters from within the token
    def _strip_mixed_token(m):
        tok = m.group(0)
        ar_count = len(re.findall(f"[{_ARABIC}]", tok))
        lat_count = len(re.findall(f"[{_LATIN}]", tok))
        # majority script wins; strip the minority letters
        if lat_count >= ar_count:
            return re.sub(f"[{_ARABIC}]", "", tok)
        return re.sub(f"[{_LATIN}]", "", tok)

    mixed_token = re.compile(rf"\b[{_LATIN}{_ARABIC}]*"
                             rf"(?:[{_LATIN}][{_ARABIC}]|[{_ARABIC}][{_LATIN}])"
                             rf"[{_LATIN}{_ARABIC}]*\b")
    if mixed_token.search(text):
        issues.append(("mixed_token", "mixed-script tokens normalized"))
        text = mixed_token.sub(_strip_mixed_token, text)

    # FLAG whole Latin words embedded in Arabic prose (don't delete — may be
    # meaningful; report so the writer can translate/replace them). We only
    # flag when the surrounding text is clearly Arabic.
    if lang == "ar":
        ar_letters = len(re.findall(f"[{_ARABIC}]", text))
        lat_words = re.findall(rf"(?<![{_LATIN}])[{_LATIN}]{{2,}}(?![{_LATIN}])", text)
        # ignore tokens that are inside protected citation placeholders
        lat_words = [w for w in lat_words if "CITE" not in w]
        if ar_letters > 20 and lat_words:
            issues.append(("latin_in_arabic",
                           "Latin words inside Arabic prose: "
                           + ", ".join(lat_words[:5])))

    return [text, issues]


# ── linguistic tells (soft — reported, lightly reduced) ──────
_AR_TELLS = [
    "علاوة على ذلك", "علاوةً على ذلك", "فضلا عن ذلك", "فضلاً عن ذلك",
    "وتجدر الإشارة", "تجدر الإشارة", "في المحصلة", "خلاصة القول",
    "ومن الجدير بالذكر", "من الجدير بالذكر",
]
_EN_TELLS = [
    "Certainly,", "Furthermore,", "Moreover,", "In conclusion,",
    "It is important to note that", "It's important to note that",
    "It is worth noting that",
]


def find_linguistic_tells(text: str, lang: str) -> list:
    """Report AI-tell phrases present (for the humanizer to vary/reduce)."""
    tells = _AR_TELLS if lang == "ar" else _EN_TELLS
    return [t for t in tells if t in text]


# ── main entry ───────────────────────────────────────────────
def clean_text(text: str, lang: str = "ar", file_type: str = "docx") -> dict:
    """
    Clean AI fingerprints from `text`.

    file_type: "docx"/"pdf" -> full visual cleaning (dashes, symbols).
               "pptx"        -> visual symbols ALLOWED (skip that step).
               "xlsx"        -> light (language-mix only).

    Returns {"text": cleaned, "issues": [...], "tells": [...]}.
    """
    issues = []
    prose_doc = file_type in ("docx", "pdf", "md", "txt")

    # 1) language-mix glitches (all file types)
    text, mix_issues = _fix_language_mix(text, lang)
    issues += mix_issues

    # 2) visual symbols — only for prose documents, NOT slides
    if prose_doc:
        before = text
        text = _clean_dashes(text)
        text = _clean_decorative(text)
        if text != before:
            issues.append(("visual", "dashes/decorative symbols normalized"))
    elif file_type == "xlsx":
        # light: only collapse long dashes to hyphen, keep other symbols
        text = re.sub(f"[{re.escape(_DASH_CHARS)}]", "-", text)

    # 3) replace research-flagged AI-marker words (English)
    if lang == "en":
        text = replace_banned_words(text, lang="en")

    # 4) report linguistic tells (handled by the humanizer's synonym pass)
    tells = find_linguistic_tells(text, lang)

    return {"text": text, "issues": issues, "tells": tells}


# ── research-backed banned AI words (COLING 2025 / ICLR 2024 / GPTZero) ──
import json as _json
_BANNED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "banned_words_en.json")
_BANNED_EN = {}
try:
    with open(_BANNED_PATH, encoding="utf-8") as _f:
        _BANNED_EN = _json.load(_f)
except Exception:
    _BANNED_EN = {}


def replace_banned_words(text, lang="en", rng=None):
    """Replace research-flagged AI-marker words with scholarly alternatives."""
    if lang != "en" or not _BANNED_EN:
        return text
    import random as _random
    rng = rng or _random.Random(42)
    for word, alts in _BANNED_EN.items():
        if not alts:
            continue
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        def _sub(m, alts=alts):
            repl = rng.choice(alts)
            orig = m.group(0)
            if orig[:1].isupper():
                return repl[:1].upper() + repl[1:]
            return repl
        text = pattern.sub(_sub, text)
    return text


if __name__ == "__main__":
    tests = [
        ("استخدم—اللغة العربية", "ar", "docx"),
        ("استخدم — اللغة العربية", "ar", "docx"),
        ("—في حين يبقى الوطن—", "ar", "docx"),
        ("هذا نص — مع شرطة", "ar", "docx"),
        ("في حين Remains الوطن", "ar", "docx"),
        ("عندي Caر و بياناT هنا", "ar", "docx"),
        ("نص فيه 中文 دخيل", "ar", "docx"),
        ("الخيارات: كتاب | مقالة | موقع", "ar", "docx"),
        ("★ عنوان ✓ مهم → انظر", "ar", "docx"),
        ("slides can use — dashes and → arrows", "en", "pptx"),
    ]
    for t, lang, ft in tests:
        r = clean_text(t, lang, ft)
        print(f"[{ft}] {t!r}")
        print(f"    -> {r['text']!r}")
        if r["issues"]:
            print(f"    issues: {[i[0] for i in r['issues']]}")
        print()


# ── verification: detect any remaining AI fingerprints ───────
def verify_clean(text: str, lang: str = "ar", file_type: str = "docx") -> dict:
    """
    Check whether `text` still contains AI fingerprints (used by layer 7).
    Returns {"clean": bool, "found": [...]} — for prose docs; for pptx the
    visual-symbol check is skipped.
    """
    found = []
    prose = file_type in ("docx", "pdf", "md", "txt")

    if prose:
        if re.search(f"[{re.escape(_DASH_CHARS + _BOX_CHARS)}]", text):
            found.append("long_dash")
        for group, label in ((_DECORATIVE, "decorative"), (_ARROWS, "arrow"),
                             (_BULLETS, "bullet")):
            if any(c in text for c in group):
                found.append(label)
        if "`" in text:
            found.append("backtick")
        if "|" in text:
            found.append("pipe")

    # language mix (all types)
    if re.search(f"[{_CJK}]", text):
        found.append("cjk")
    if re.search(rf"[{_LATIN}][{_ARABIC}]|[{_ARABIC}][{_LATIN}]", text):
        found.append("mixed_token")

    # linguistic tells (all types)
    tells = find_linguistic_tells(text, lang)
    if tells:
        found.append(f"tells:{len(tells)}")

    return {"clean": len(found) == 0, "found": found}


# ── decision table: which cleaning applies to which file type ─
CLEANING_DECISION = {
    "docx": {"dashes": True,  "decorative": True,  "lang_mix": True,  "tells": True},
    "pdf":  {"dashes": True,  "decorative": True,  "lang_mix": True,  "tells": True},
    "md":   {"dashes": True,  "decorative": True,  "lang_mix": True,  "tells": True},
    "pptx": {"dashes": False, "decorative": False, "lang_mix": True,  "tells": True},
    "xlsx": {"dashes": True,  "decorative": False, "lang_mix": True,  "tells": False},
    "email":{"dashes": False, "decorative": False, "lang_mix": True,  "tells": False},
}
