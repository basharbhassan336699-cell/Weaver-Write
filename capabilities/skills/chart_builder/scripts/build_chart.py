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


def _reshape_ar(labels):
    """Reshape Arabic labels for correct display; pass through if libs absent."""
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


def build_chart(chart_type, data, output_path, title="", theme_id="academic_navy",
                xlabel="", ylabel="", lang="ar", figsize=(8, 5), dpi=150):
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
    if lang == "ar":
        try:
            import sys
            fonts_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))))),
                "engines", "fonts-core")
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

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(theme["bg"])
    ax.set_facecolor(theme["bg"])
    if ar_family:
        plt.rcParams["font.family"] = ar_family

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
            ax.pie(vals, labels=labels, autopct="%1.1f%%", colors=colors,
                   wedgeprops=wedgeprops, textprops={"color": theme["text"]})
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

        fig.tight_layout()
        fig.savefig(output_path, dpi=dpi, facecolor=theme["bg"],
                    bbox_inches="tight")
        plt.close(fig)
    except Exception as e:
        plt.close(fig)
        return {"ok": False, "error": f"render failed: {e}"}

    return {"ok": True, "output_path": output_path, "type": chart_type,
            "theme": theme_id, "engine": "matplotlib"}


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
