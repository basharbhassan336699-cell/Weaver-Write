"""
palette_generator.py — dynamic harmonious palettes (working script)
===================================================================
Two jobs:

1) custom_theme(base_hex, lang) — take ANY color the user gives and build a
   COMPLETE, harmonious, readable theme around it (primary + accent +
   background + text, all contrast-checked). Lets the user pick any color
   without breaking design quality.

2) chart_series_colors(theme, n) — produce N VISUALLY DISTINCT colors that
   still belong to the theme's family, so charts stay readable (each bar /
   slice is separable) AND coordinated with the deck. This avoids the
   "all one color -> chart invisible" problem while keeping harmony.

Pure standard-library color math (colorsys); no heavy deps.
"""
from __future__ import annotations
import colorsys


# ── hex <-> helpers ──────────────────────────────────────────
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "".join(f"{max(0,min(255,round(c*255))):02X}" for c in rgb)


def _luminance(rgb):
    """Relative luminance for contrast (WCAG-ish)."""
    def ch(c):
        return c/12.92 if c <= 0.03928 else ((c+0.055)/1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb)
    return 0.2126*r + 0.7152*g + 0.0722*b


def _contrast(rgb1, rgb2):
    l1, l2 = _luminance(rgb1), _luminance(rgb2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _readable_text(bg_rgb):
    """Pick dark or light text that reads on the given background."""
    dark = (0.13, 0.13, 0.13)
    light = (0.98, 0.98, 0.98)
    return dark if _contrast(bg_rgb, dark) >= _contrast(bg_rgb, light) else light


# ── 1) build a full theme from any base color ────────────────
def custom_theme(base_hex, lang="ar", name="custom"):
    """
    Build a complete harmonious theme dict (same shape as themes.json entries)
    from a single base color. The accent is a complementary-ish hue; the
    background is a very light tint; text is contrast-checked.
    """
    r, g, b = _hex_to_rgb(base_hex)
    h, l, s = colorsys.rgb_to_hls(r, g, b)

    # primary: the base, nudged to a confident mid-dark lightness
    primary_rgb = colorsys.hls_to_rgb(h, min(max(l, 0.22), 0.42), max(s, 0.35))
    # accent: rotate hue ~150° (near-complementary) for a lively pairing
    accent_rgb = colorsys.hls_to_rgb((h + 150/360) % 1.0, 0.55, max(s, 0.5))
    # title background: a dark version of the primary hue
    bg_title_rgb = colorsys.hls_to_rgb(h, 0.16, max(s, 0.3))
    # content background: a very light tint of the hue
    bg_rgb = colorsys.hls_to_rgb(h, 0.96, min(s, 0.25))

    text_rgb = _readable_text(bg_rgb)
    text_on_dark_rgb = (0.98, 0.98, 0.98)

    return {
        "label_ar": f"مخصّص ({name})", "label_en": f"Custom ({name})",
        "primary": _rgb_to_hex(primary_rgb),
        "accent": _rgb_to_hex(accent_rgb),
        "bg": _rgb_to_hex(bg_rgb),
        "bg_title": _rgb_to_hex(bg_title_rgb),
        "text": _rgb_to_hex(text_rgb),
        "text_on_dark": _rgb_to_hex(text_on_dark_rgb),
        "font_ar": "Kufyan Arabic Black", "font_en": "Georgia",
        "mood": ["مخصّص", "custom", name],
        "_generated": True,
    }


# ── 2) distinct-but-harmonious chart series colors ───────────
def chart_series_colors(theme, n):
    """
    Return N visually DISTINCT colors coordinated with the theme.

    Strategy: anchor on the theme's primary hue, then walk the hue wheel in
    balanced steps (analogous + complementary spread) while keeping saturation
    and lightness in a readable band. This guarantees adjacent bars/slices are
    tell-apart-able, unlike a light->dark ramp of one hue.
    """
    if n <= 0:
        return []
    pr = _hex_to_rgb(theme["primary"])
    h0, l0, s0 = colorsys.rgb_to_hls(*pr)
    accent = _hex_to_rgb(theme.get("accent", theme["primary"]))
    ha, la, sa = colorsys.rgb_to_hls(*accent)

    if n == 1:
        return ["#" + theme["primary"]]
    if n == 2:
        return ["#" + theme["primary"], "#" + theme["accent"]]

    # spread hues across the wheel starting near the primary, biased so the
    # accent hue is included; keep S/L in a legible range for good separation.
    colors = []
    sat = min(max((s0 + sa) / 2, 0.45), 0.8)
    lit = min(max((l0 + la) / 2, 0.40), 0.60)
    # use a golden-angle-ish step but normalized to n for even spacing
    for i in range(n):
        hue = (h0 + (i / n)) % 1.0
        # alternate lightness slightly to boost adjacent-contrast
        ll = lit + (0.08 if i % 2 else -0.05)
        ll = min(max(ll, 0.30), 0.68)
        colors.append("#" + _rgb_to_hex(colorsys.hls_to_rgb(hue, ll, sat)))
    return colors


def _main():
    import argparse, json
    p = argparse.ArgumentParser(description="Palette generator")
    p.add_argument("--base", help="base hex for a custom theme, e.g. 6B8E23")
    p.add_argument("--series", type=int, help="N distinct chart colors from a theme")
    p.add_argument("--name", default="custom")
    args = p.parse_args()
    if args.base:
        print(json.dumps(custom_theme(args.base, name=args.name), ensure_ascii=False, indent=2))
    if args.series:
        # demo using a default navy/gold theme
        demo = {"primary": "1B2A4A", "accent": "C8A04A"}
        print(chart_series_colors(demo, args.series))


if __name__ == "__main__":
    _main()
