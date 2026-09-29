"""
build_chart.py — professional themed charts (working script)
============================================================
Comprehensive chart builder matching the quality Claude produces in files.

Chart types: bar, grouped_bar, stacked_bar, line, multi_line, area,
scatter, pie, donut, histogram, horizontal_bar, radar.

Themes: reuses the presentation theme palettes (themes.json) so a chart
embedded in a deck/report visually matches the slides. Also standalone
palettes. Arabic labels are reshaped for correct RTL rendering when the
arabic-reshaper/python-bidi libraries are available.

Output: PNG (for embedding in docx/pptx) or SVG.

Requires: pip install matplotlib  (+ arabic-reshaper python-bidi for Arabic labels)
"""
from __future__ import annotations
import argparse
import json
import os

_THEMES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "pptx_builder", "themes", "themes.json")


def _load_theme(theme_id):
    """Load a palette from the shared presentation themes, with a fallback.
    If theme_id looks like a hex color (custom), build a theme from it."""
    # custom color: 6-hex like "6B8E23" or "#6B8E23"
    cand = str(theme_id).lstrip("#")
    if len(cand) == 6 and all(c in "0123456789abcdefABCDEF" for c in cand):
        try:
            import sys, os
            pg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "..", "pptx_builder", "scripts")
            pg = os.path.abspath(pg)
            if pg not in sys.path:
                sys.path.insert(0, pg)
            from palette_generator import custom_theme
            t = custom_theme(cand)
            return {"primary": "#" + t["primary"], "accent": "#" + t["accent"],
                    "text": "#" + t["text"], "bg": "#" + t["bg"]}
        except Exception:
            pass
    try:
        with open(_THEMES_PATH, encoding="utf-8") as f:
            themes = json.load(f)["themes"]
        if theme_id in themes:
            t = themes[theme_id]
            return {
                "primary": "#" + t["primary"], "accent": "#" + t["accent"],
                "text": "#" + t.get("text", "222222"),
                "bg": "#" + t.get("bg", "FFFFFF"),
            }
    except Exception:
        pass
    return {"primary": "#1B2A4A", "accent": "#C8A04A",
            "text": "#222222", "bg": "#FFFFFF"}


def _palette(theme, n):
    """
    Build n distinct-but-harmonious series colors.
    Uses the shared palette_generator so chart colors coordinate with the
    presentation theme yet stay visually separable (bars/slices don't blend).
    """
    try:
        import sys, os
        pg_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "pptx_builder", "scripts")
        if pg_dir not in sys.path:
            sys.path.insert(0, pg_dir)
        from palette_generator import chart_series_colors
        # chart_series_colors expects hex WITHOUT '#'; theme values here have '#'
        clean = {"primary": theme["primary"].lstrip("#"),
                 "accent": theme["accent"].lstrip("#")}
        return chart_series_colors(clean, n)
    except Exception:
        # fallback: simple interpolation between primary and accent
        import matplotlib.colors as mc
        import numpy as np
        p = np.array(mc.to_rgb(theme["primary"]))
        a = np.array(mc.to_rgb(theme["accent"]))
        if n <= 1:
            return [theme["primary"]]
        return [mc.to_hex((1 - i/(n-1)) * p + (i/(n-1)) * a) for i in range(n)]


def _native_shaping():
    """True when matplotlib shapes and orders RTL text itself (built with
    libraqm, matplotlib >= 3.11). Measured: reshaping + get_display on top of
    that reverses the text a second time (backwards, unjoined letters)."""
    try:
        from matplotlib import ft2font
        return bool(getattr(ft2font, "__libraqm_version__", ""))
    except Exception:
        return False


# Which path draws Arabic correctly — MEASURED at run time, not inferred from
# the version. The user's phone reported "Arabic in charts comes out cut and
# from the left": whether matplotlib shapes Arabic itself depends on how it
# was built, so the only safe answer is to draw a test and look at it.
#   order:   "ا ب" -> two glyph blocks; alef (the narrower) must be on the RIGHT
#   joining: "ببب" -> ONE connected block (unjoined = three separate blocks)
_SHAPING = {}                 # font family -> "native" | "reshape"
_ACTIVE = {"mode": None}      # set by build_chart for the chart being drawn


def _ink_runs(text, family=None):
    """Column runs of ink [(start, width)] for `text` drawn with Agg."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import numpy as np
    fig = Figure(figsize=(4, 1), dpi=100)
    FigureCanvasAgg(fig)
    kw = {"fontfamily": family} if family else {}
    fig.text(0.05, 0.3, text, fontsize=40, **kw)
    fig.canvas.draw()
    ink = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].min(axis=2) < 128
    runs, start = [], None
    for x, v in enumerate(list(ink.any(axis=0)) + [False]):
        if v and start is None:
            start = x
        elif not v and start is not None:
            runs.append((start, x - start))
            start = None
    return runs


def _draws_right(to_display, family=None):
    r = _ink_runs(to_display("\u0627 \u0628"), family)          # ا ب
    if len(r) != 2 or not r[1][1] < r[0][1]:
        return False
    return len(_ink_runs(to_display("\u0628\u0628\u0628"), family)) == 1   # ببب


def _shaping_mode(family=None):
    """'native' (pass text as is) or 'reshape' (arabic-reshaper + bidi),
    whichever draws Arabic right on THIS machine. Cached per font."""
    key = family or ""
    if key in _SHAPING:
        return _SHAPING[key]
    mode = None
    try:
        if _draws_right(lambda t: t, family):
            mode = "native"
        else:
            try:
                import arabic_reshaper
                from bidi.algorithm import get_display
                if _draws_right(lambda t: get_display(arabic_reshaper.reshape(t)),
                                family):
                    mode = "reshape"
            except ImportError:
                pass
    except Exception:
        mode = None
    if mode is None:
        mode = "native" if _native_shaping() else "reshape"
    _SHAPING[key] = mode
    return mode


def _reshape_ar(labels):
    """Reshape Arabic labels for correct display; pass through if libs absent
    or if matplotlib already shapes Arabic natively."""
    _mode = _ACTIVE.get("mode")
    if _mode == "native" or (_mode is None and _native_shaping()):
        return [str(l) for l in labels]
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        out = []
        for l in labels:
            s = str(l)
            if any('\u0600' <= c <= '\u06FF' for c in s):
                s = get_display(arabic_reshaper.reshape(s))
            out.append(s)
        return out
    except ImportError:
        return [str(l) for l in labels]


# engines/fonts-core — the repo root is FOUR levels above this file's folder
# (scripts -> chart_builder -> skills -> capabilities -> root). The old
# expression climbed one level too few (…/capabilities/engines/fonts-core,
# which does not exist), so standalone charts silently fell back to
# DejaVu Sans; it only worked when a caller had put fonts-core on sys.path.
_FONTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))), "engines", "fonts-core")


def _font_for_chart(font, lang):
    """(family list for rcParams, note) for a requested font name.

    Bundled -> its own file; a commercial name we don't ship (Arial,
    Simplified Arabic...) -> the closest bundled stand-in. Arabic text always
    has an Arabic fallback, so a Latin-only font never leaves boxes."""
    import sys
    if _FONTS_DIR not in sys.path:
        sys.path.insert(0, _FONTS_DIR)
    from matplotlib import font_manager as fm
    fams, note = [], ""
    if font:
        from font_catalog import find_font, file_for, catalog
        e = find_font(font)
        if e and not e.get("bundled") and e.get("stand_in"):
            note = "'%s' is not bundled; chart drawn with '%s'" % (
                e["family"], e["stand_in"])
            e = next((c for c in catalog() if c["family"] == e["stand_in"]), None)
            if e:
                e = dict(e, weight="regular")
        path = file_for(e) if e and e.get("files") else None
        if path:
            fm.fontManager.addfont(path)
            for extra in (e["files"].get("bold"),):
                if extra and extra != path:
                    fm.fontManager.addfont(extra)
            fams.append(fm.FontProperties(fname=path).get_name())
        elif e:
            note = note or "'%s' is not bundled; default font used" % e["family"]
    try:
        from fonts import register_for_matplotlib
        ar = register_for_matplotlib("Kufyan Arabic Black")
        if ar and ar not in fams:
            fams.append(ar)                   # Arabic fallback, always present
    except Exception:
        pass
    if lang != "ar" and not font:
        fams = []                             # English default: as before
    return fams, note


def build_chart(chart_type, data, output_path, title="", theme_id="academic_navy",
                xlabel="", ylabel="", lang="ar", figsize=(8, 5), dpi=150,
                font=None):
    """
    Render a themed chart. `data` shape depends on chart_type:
      bar/pie/donut/hist:   {"labels": [...], "values": [...]}
      grouped_bar/stacked:  {"labels": [...], "series": {"name": [...], ...}}
      line/area:            {"x": [...], "y": [...]}  or {"labels","values"}
      multi_line:           {"x": [...], "series": {"name": [...], ...}}
      scatter:              {"x": [...], "y": [...]}
      radar:                {"labels": [...], "values": [...]}
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return {"ok": False, "error": "matplotlib not available (pip install matplotlib)"}

    theme = _load_theme(theme_id)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Register a bundled Arabic font so Arabic labels render in a real
    # Arabic typeface (Kufyan preferred -> Cairo/Tajawal/Amiri fallback).
    ar_family = None
    _font_note = ""
    if font:
        try:
            _fams, _font_note = _font_for_chart(font, lang)
            ar_family = _fams or None
        except Exception:
            ar_family = None
    if lang == "ar" and not ar_family:
        try:
            import sys
            fonts_dir = _FONTS_DIR
            if fonts_dir not in sys.path:
                sys.path.insert(0, fonts_dir)
            from fonts import register_for_matplotlib
            ar_family = register_for_matplotlib("Kufyan Arabic Black")
        except Exception:
            ar_family = None

    plt.rcParams["axes.edgecolor"] = theme["text"]
    plt.rcParams["text.color"] = theme["text"]
    plt.rcParams["axes.labelcolor"] = theme["text"]
    plt.rcParams["xtick.color"] = theme["text"]
    plt.rcParams["ytick.color"] = theme["text"]

    # The font BEFORE the axes exist: the axes capture it when created. Set
    # after (as it was), every chart took the PREVIOUS chart's font — and a
    # single chart (one per process, as office.py draws) got DejaVu Sans.
    plt.rcParams["font.family"] = (ar_family if ar_family
                                   else matplotlib.rcParamsDefault["font.family"])
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(theme["bg"])
    ax.set_facecolor(theme["bg"])
    if ar_family:
        plt.rcParams["font.family"] = ar_family
    import logging as _lg
    _lg.getLogger("matplotlib.font_manager").setLevel(_lg.ERROR)
    # Arabic anywhere in the chart -> decide the drawing path by measurement
    _blob = " ".join(str(x) for x in [title, xlabel, ylabel] + list(
        data.get("labels", []) or []) + list((data.get("series") or {}).keys()))
    if lang == "ar" or any("\u0600" <= c <= "\u06FF" for c in _blob):
        _fam0 = ar_family[0] if isinstance(ar_family, list) else ar_family
        _ACTIVE["mode"] = _shaping_mode(_fam0)
    rtl = (lang == "ar")

    try:
        labels = _reshape_ar(data.get("labels", []))

        if chart_type in ("bar", "horizontal_bar"):
            vals = data.get("values", [])
            colors = _palette(theme, len(vals))
            if chart_type == "horizontal_bar":
                ax.barh(labels, vals, color=colors)
            else:
                ax.bar(labels, vals, color=colors)

        elif chart_type == "grouped_bar":
            series = data.get("series", {})
            x = np.arange(len(labels))
            n = len(series)
            w = 0.8 / max(n, 1)
            colors = _palette(theme, n)
            for i, (name, vals) in enumerate(series.items()):
                ax.bar(x + i*w - 0.4 + w/2, vals, w,
                       label=_reshape_ar([name])[0], color=colors[i])
            ax.set_xticks(x); ax.set_xticklabels(labels)
            ax.legend()

        elif chart_type == "stacked_bar":
            series = data.get("series", {})
            colors = _palette(theme, len(series))
            bottom = np.zeros(len(labels))
            for i, (name, vals) in enumerate(series.items()):
                ax.bar(labels, vals, bottom=bottom,
                       label=_reshape_ar([name])[0], color=colors[i])
                bottom += np.array(vals)
            ax.legend()

        elif chart_type in ("line", "area"):
            x = data.get("x", labels or list(range(len(data.get("values", data.get("y", []))))))
            y = data.get("y", data.get("values", []))
            ax.plot(x, y, marker="o", color=theme["primary"], linewidth=2.5)
            if chart_type == "area":
                ax.fill_between(range(len(y)), y, color=theme["accent"], alpha=0.3)

        elif chart_type == "multi_line":
            x = data.get("x", [])
            colors = _palette(theme, len(data.get("series", {})))
            for i, (name, vals) in enumerate(data.get("series", {}).items()):
                ax.plot(x, vals, marker="o", label=_reshape_ar([name])[0],
                        color=colors[i], linewidth=2.5)
            ax.legend()

        elif chart_type == "scatter":
            ax.scatter(data.get("x", []), data.get("y", []),
                       color=theme["primary"], s=60, alpha=0.7,
                       edgecolors=theme["accent"])

        elif chart_type in ("pie", "donut"):
            vals = data.get("values", [])
            colors = _palette(theme, len(vals))
            wedgeprops = {"width": 0.42} if chart_type == "donut" else {}
            _dir = {"startangle": 90, "counterclock": False} if rtl else {}
            ax.pie(vals, labels=labels, autopct="%1.1f%%", colors=colors,
                   wedgeprops=wedgeprops, textprops={"color": theme["text"]},
                   **_dir)
            ax.axis("equal")

        elif chart_type == "histogram":
            ax.hist(data.get("values", []), bins=data.get("bins", 10),
                    color=theme["primary"], edgecolor=theme["accent"])

        elif chart_type == "radar":
            vals = data.get("values", [])
            n = len(labels)
            angles = np.linspace(0, 2*np.pi, n, endpoint=False).tolist()
            vals2 = vals + vals[:1]; angles2 = angles + angles[:1]
            ax = plt.subplot(111, polar=True)
            ax.plot(angles2, vals2, color=theme["primary"], linewidth=2)
            ax.fill(angles2, vals2, color=theme["accent"], alpha=0.3)
            ax.set_xticks(angles); ax.set_xticklabels(labels)
            if rtl:                       # clockwise from the top
                ax.set_theta_offset(np.pi / 2)
                ax.set_theta_direction(-1)

        else:
            plt.close(fig)
            return {"ok": False, "error": f"unknown chart type: {chart_type}"}

        if title:
            ax.set_title(_reshape_ar([title])[0], color=theme["primary"],
                         fontsize=15, fontweight="bold", pad=15)
        if xlabel:
            ax.set_xlabel(_reshape_ar([xlabel])[0])
        if ylabel:
            ax.set_ylabel(_reshape_ar([ylabel])[0])

        # RTL: put y-axis on the right for Arabic
        if lang == "ar" and chart_type not in ("pie", "donut", "radar"):
            ax.yaxis.set_label_position("right")
            ax.yaxis.tick_right()
        # RTL design: the first category on the RIGHT (read right-to-left),
        # horizontal bars grow from the right with the first on top, and the
        # legend marker sits after its text. Numeric axes (scatter, histogram)
        # keep their natural direction.
        if rtl:
            if chart_type in ("bar", "grouped_bar", "stacked_bar", "line",
                              "area", "multi_line"):
                ax.invert_xaxis()
            elif chart_type == "horizontal_bar":
                ax.invert_xaxis()
                ax.invert_yaxis()
            if ax.get_legend() is not None:
                ax.legend(markerfirst=False, loc="best")

        fig.tight_layout()
        fig.savefig(output_path, dpi=dpi, facecolor=theme["bg"],
                    bbox_inches="tight")
        plt.close(fig)
    except Exception as e:
        plt.close(fig)
        return {"ok": False, "error": f"render failed: {e}"}

    finally:
        _ACTIVE["mode"] = None

    return {"ok": True, "output_path": output_path, "type": chart_type,
            "theme": theme_id, "engine": "matplotlib",
            "font": (ar_family[0] if isinstance(ar_family, list) and ar_family
                     else ar_family), "font_note": _font_note}


CHART_TYPES = ["bar", "horizontal_bar", "grouped_bar", "stacked_bar", "line",
               "area", "multi_line", "scatter", "pie", "donut", "histogram", "radar"]


def _main():
    p = argparse.ArgumentParser(description="Build a themed chart")
    p.add_argument("--json", required=True)
    p.add_argument("--output", default="chart.png")
    p.add_argument("--type", default="bar", choices=CHART_TYPES)
    p.add_argument("--theme", default="academic_navy")
    p.add_argument("--lang", default="ar")
    args = p.parse_args()
    with open(args.json, encoding="utf-8") as f:
        d = json.load(f)
    r = build_chart(args.type, d, args.output, title=d.get("title", ""),
                    theme_id=args.theme, lang=args.lang)
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    _main()
