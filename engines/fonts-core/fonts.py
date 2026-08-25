"""
engines/fonts-core/fonts.py — font manager (working module)
===========================================================
Bundled open-source fonts so Weaver Write can render Arabic/English
documents, charts, and slides consistently — WITHOUT relying on the device
having a specific font installed.

Bundled Arabic fonts (all open-source, OFL licensed):
  - Amiri            : classical Naskh, excellent for academic body text.
  - Cairo            : modern geometric sans, great for slides/headings.
  - Tajawal          : clean modern sans (Regular/Bold/Black weights).
  - Noto Naskh Arabic: highly legible, wide coverage.

Note on "Kufyan Arabic Black": this is the font the user prefers in their
decks, but it is a COMMERCIAL font and cannot be bundled/downloaded freely.
When it isn't installed on the device, the closest open substitute is
**Cairo Black** (modern geometric, bold) or **Tajawal Black**. The builders
name Kufyan first and fall back to these automatically.

Latin fonts rely on system defaults (Georgia, Segoe UI, Helvetica) which are
near-universally available.
"""
from __future__ import annotations
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
ARABIC_DIR = os.path.join(_DIR, "arabic")
LATIN_DIR = os.path.join(_DIR, "latin")

# family -> file map (regular + bold where available)
ARABIC_FONTS = {
    "Kufyan Arabic": {
        "regular": "Kufyan-Arabic-Regular.ttf",
        "bold": "Kufyan-Arabic-Regular.ttf",
        "use": "user's preferred font (now bundled: Regular weight)",
    },
    "Amiri": {
        "regular": "Amiri-Regular.ttf", "bold": "Amiri-Bold.ttf",
        "use": "academic body text (classical Naskh)",
    },
    "Cairo": {
        "regular": "Cairo-Variable.ttf", "bold": "Cairo-Variable.ttf",
        "use": "modern slides/headings (geometric sans)",
    },
    "Tajawal": {
        "regular": "Tajawal-Regular.ttf", "bold": "Tajawal-Bold.ttf",
        "black": "Tajawal-Black.ttf",
        "use": "clean modern sans (has Black weight)",
    },
    "Noto Naskh Arabic": {
        "regular": "NotoNaskhArabic-Regular.ttf", "bold": "NotoNaskhArabic-Regular.ttf",
        "use": "highly legible wide-coverage Naskh",
    },
}

# The user's preferred (commercial) font, with open-source fallbacks in order.
PREFERRED_AR = "Kufyan Arabic Black"
FALLBACK_CHAIN = ["Kufyan Arabic", "Cairo", "Tajawal", "Amiri", "Noto Naskh Arabic"]


def font_path(family: str, weight: str = "regular") -> str | None:
    """Return the .ttf path for a bundled Arabic family/weight, or None."""
    spec = ARABIC_FONTS.get(family)
    if not spec:
        return None
    fname = spec.get(weight) or spec.get("regular")
    p = os.path.join(ARABIC_DIR, fname)
    return p if os.path.exists(p) else None


def resolve_arabic_font(preferred: str = None, weight: str = "regular"):
    """
    Resolve an Arabic font to an actual bundled file.
    Tries the preferred family, then the fallback chain. Returns
    (family_name, ttf_path) — path may be None if nothing is bundled.
    """
    order = []
    if preferred and preferred not in order:
        order.append(preferred)
    order += FALLBACK_CHAIN
    for fam in order:
        p = font_path(fam, weight)
        if p:
            return fam, p
    return (preferred or PREFERRED_AR), None


def register_for_matplotlib(preferred: str = None) -> str | None:
    """
    Register a bundled Arabic font with matplotlib and return the family name
    to set as font.family. Falls back through the chain.
    """
    fam, path = resolve_arabic_font(preferred)
    if not path:
        return None
    try:
        from matplotlib import font_manager as fm
        fm.fontManager.addfont(path)
        # also register bold if present
        _, bold = resolve_arabic_font(preferred, "bold")
        if bold and bold != path:
            fm.fontManager.addfont(bold)
        return fam
    except Exception:
        return None


def list_bundled():
    """Return a summary of bundled fonts and their availability."""
    out = {}
    for fam, spec in ARABIC_FONTS.items():
        p = font_path(fam)
        out[fam] = {"available": p is not None, "use": spec["use"]}
    return out




# ─────────────────────────────────────────────────────────────
# System fonts: COMMERCIAL fonts that ship with Word/PowerPoint.
# We cannot bundle them, but they render correctly on the user's
# device because Office already has them. For preview/rendering on
# machines that lack them, we map each to the closest bundled open font.
# ─────────────────────────────────────────────────────────────
SYSTEM_FONTS = {
    # Arabic (commercial)
    "Kufyan Arabic Black":   {"kind": "ar", "fallback": "Cairo",   "weight": "black"},
    "Kufyan Arabic Regular": {"kind": "ar", "fallback": "Kufyan Arabic", "weight": "regular"},
    "Kufyan Arabic":         {"kind": "ar", "fallback": "Kufyan Arabic", "weight": "regular"},
    "Simplified Arabic":     {"kind": "ar", "fallback": "Amiri",   "weight": "regular"},
    "Traditional Arabic":    {"kind": "ar", "fallback": "Amiri",   "weight": "regular"},
    # Latin (commercial, ship with Office/OS)
    "Arial":                 {"kind": "latin", "fallback": "DejaVu Sans"},
    "Times New Roman":       {"kind": "latin", "fallback": "DejaVu Serif"},
    "Calibri":               {"kind": "latin", "fallback": "DejaVu Sans"},
    "Georgia":               {"kind": "latin", "fallback": "DejaVu Serif"},
}


def resolve_named_font(name: str, weight: str = "regular"):
    """
    Resolve ANY requested font name (including commercial ones) to something
    renderable, WITHOUT changing what gets written into the document.

    Returns dict:
      {"requested": name,        # what the document should say (unchanged)
       "render_family": str,     # a family available for local preview/render
       "render_path": str|None,  # bundled ttf path if we have one
       "is_commercial": bool,    # True if the requested font is device-only
       "note": str}

    Key idea: the .docx/.pptx keeps the NAME the user asked for (e.g. "Arial"
    or "Kufyan Arabic Black"); Office on the device renders it correctly. Our
    bundled font is only used for server-side preview/charts when the real
    font isn't present here.
    """
    # bundled Arabic family requested directly
    if name in ARABIC_FONTS:
        fam, path = resolve_arabic_font(name, weight)
        return {"requested": name, "render_family": fam, "render_path": path,
                "is_commercial": False, "note": "bundled open-source font"}

    spec = SYSTEM_FONTS.get(name)
    if spec:
        if spec["kind"] == "ar":
            fam, path = resolve_arabic_font(spec["fallback"], spec.get("weight", weight))
            return {"requested": name, "render_family": fam, "render_path": path,
                    "is_commercial": True,
                    "note": f"commercial font — written as '{name}'; "
                            f"previewed with bundled '{fam}'"}
        # latin commercial -> rely on system; map for preview only
        return {"requested": name, "render_family": spec["fallback"],
                "render_path": None, "is_commercial": True,
                "note": f"commercial Latin font — written as '{name}'; "
                        f"device renders it, preview uses '{spec['fallback']}'"}

    # unknown -> keep the name, try Arabic fallback chain for preview
    fam, path = resolve_arabic_font(name, weight)
    return {"requested": name, "render_family": fam, "render_path": path,
            "is_commercial": False, "note": "unknown font; kept name as-is"}


LATIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "latin")


def list_latin_fonts():
    """Return available Latin font files (from the bundled Canvas set)."""
    if not os.path.isdir(LATIN_DIR):
        return []
    return sorted(f for f in os.listdir(LATIN_DIR)
                  if f.lower().endswith((".ttf", ".otf")))


def latin_font_path(name):
    """Resolve a Latin font file by (partial) name."""
    for f in list_latin_fonts():
        if name.lower() in f.lower():
            return os.path.join(LATIN_DIR, f)
    return None


if __name__ == "__main__":
    import json
    print("Bundled Arabic fonts:")
    print(json.dumps(list_bundled(), ensure_ascii=False, indent=2))
    fam, path = resolve_arabic_font("Kufyan Arabic Black")
    print(f"\nKufyan requested -> resolved to: {fam}")
    print(f"  path: {path}")
