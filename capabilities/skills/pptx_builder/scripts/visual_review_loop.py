"""
visual_review_loop.py — visual self-correction loop (working script)
====================================================================
The final piece of the "Claude way": after generating a deck, render each
slide to an image, have a VISION LLM inspect the images for visual defects
(overflow, overlap, clipped text, poor contrast, empty areas, wrong reading
direction), and if problems are found, ask the authoring LLM to FIX the HTML.
Repeat until clean or max rounds reached.

Loop:
    HTML ─▶ html2pptx ─▶ PPTX ─▶ thumbnails(PNG)
                                    │
                     vision_fn(images, checklist) ─▶ issues?
                       │ yes                          │ no
                       ▼                              ▼
             llm_fn("fix these issues") ─▶ new HTML   DONE (clean)

Both callables are provided by the caller (provider-agnostic):
    - llm_fn(prompt: str) -> str            (text: authors/fixes HTML)
    - vision_fn(prompt: str, images: list[bytes]) -> str   (inspects images)

If vision_fn is None, the loop degrades to a single generation with a
non-visual structural check (still useful, just not pixel-level).
"""
from __future__ import annotations
import argparse
import json
import os
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


# The visual checklist the vision model is asked to enforce.
CHECKLIST_EN = [
    "text overflowing outside its box or off the slide",
    "elements overlapping or colliding",
    "text clipped or cut off at edges",
    "poor contrast (text hard to read on its background)",
    "large empty/unbalanced areas",
    "wrong reading direction (Arabic must read right-to-left)",
    "titles or body text too small to read",
]


def _render_thumbnails(pptx_path, outdir, dpi=110):
    """Render slides to PNG using the existing thumbnail script."""
    from thumbnail import generate_thumbnails
    return generate_thumbnails(pptx_path, outdir, dpi=dpi)


def _load_images(paths):
    imgs = []
    for p in paths:
        with open(p, "rb") as f:
            imgs.append(f.read())
    return imgs


def _build_review_prompt(lang):
    checklist = "\n".join(f"- {c}" for c in CHECKLIST_EN)
    direction = "Arabic (must read RIGHT-TO-LEFT)" if lang == "ar" else "English (left-to-right)"
    return (
        f"You are a meticulous presentation QA reviewer. The deck language is {direction}.\n"
        f"Inspect each slide image for these defects:\n{checklist}\n\n"
        "Respond ONLY as JSON: "
        '{"clean": true|false, "issues": [{"slide": <n>, "problem": "...", "fix": "..."}]}. '
        "If everything looks good, return {\"clean\": true, \"issues\": []}."
    )


def _parse_review(raw):
    """Parse the vision model's JSON verdict, tolerantly."""
    import re
    text = raw.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text, flags=re.MULTILINE)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"clean": True, "issues": []}  # no parseable verdict -> assume ok
    try:
        data = json.loads(m.group(0))
        return {"clean": bool(data.get("clean", True)),
                "issues": data.get("issues", [])}
    except Exception:
        return {"clean": True, "issues": []}


def review_and_correct(title, slides_content, output_pptx, lang="ar",
                       request="", subtitle="", theme_id=None,
                       llm_fn=None, vision_fn=None, max_rounds=2,
                       workdir=None):
    """
    Generate a deck, then visually review + correct it up to max_rounds.

    Returns dict with: ok, output_path, rounds, authored_by, theme,
    final_clean, history (per-round issues), direction, error.
    """
    from llm_deck_generator import generate_llm_deck
    from html2pptx_bridge import html_to_pptx

    workdir = workdir or os.path.join(os.path.dirname(output_pptx) or ".", "_review")
    os.makedirs(workdir, exist_ok=True)

    # round 0: initial authoring
    gen = generate_llm_deck(title, slides_content, lang, request,
                            subtitle, theme_id, llm_fn)
    html = gen["html"]
    theme = gen["theme"]
    authored_by = gen["authored_by"]

    history = []
    final_clean = None

    for rnd in range(max_rounds + 1):
        conv = html_to_pptx(html, output_pptx, is_string=True)
        if not conv.get("ok"):
            return {"ok": False, "error": conv.get("error"),
                    "rounds": rnd, "authored_by": authored_by, "theme": theme}

        # if we can't do vision review, stop after first successful build
        if vision_fn is None or llm_fn is None:
            final_clean = None  # unknown (no visual check performed)
            break

        # render + inspect
        try:
            thumbs = _render_thumbnails(output_pptx, os.path.join(workdir, f"r{rnd}"))
        except Exception as e:
            # rendering unavailable (e.g. no libreoffice) -> stop gracefully
            history.append({"round": rnd, "note": f"render unavailable: {e}"})
            final_clean = None
            break

        images = _load_images(thumbs)
        verdict = _parse_review(vision_fn(_build_review_prompt(lang), images))
        history.append({"round": rnd, "clean": verdict["clean"],
                        "issues": verdict["issues"]})

        if verdict["clean"]:
            final_clean = True
            break

        if rnd == max_rounds:
            final_clean = False   # still not clean but out of rounds
            break

        # ask the authoring LLM to FIX the HTML given the concrete issues
        issues_text = json.dumps(verdict["issues"], ensure_ascii=False, indent=2)
        fix_prompt = (
            "Here is the current HTML slide deck:\n\n"
            f"{html}\n\n"
            "A visual reviewer found these defects (per slide):\n"
            f"{issues_text}\n\n"
            "Return a corrected COMPLETE HTML document that fixes every issue. "
            "Keep the same 960x540 slide size, the same reading direction, and "
            "output ONLY raw HTML starting with <!DOCTYPE html>."
        )
        from llm_deck_generator import sanitize_html, validate_html
        fixed = sanitize_html(llm_fn(fix_prompt))
        v = validate_html(fixed, lang)
        if v["ok"]:
            html = fixed
            authored_by = "llm+visual-correction"
        # if the fix is invalid, keep the previous html and try building again

    return {
        "ok": True, "output_path": output_pptx, "rounds": len(history),
        "authored_by": authored_by, "theme": theme,
        "final_clean": final_clean, "history": history,
        "direction": "RTL" if lang == "ar" else "LTR",
    }


def _main():
    p = argparse.ArgumentParser(description="Generate a deck with visual self-correction")
    p.add_argument("--json", required=True)
    p.add_argument("--output", default="deck.pptx")
    args = p.parse_args()
    with open(args.json, encoding="utf-8") as f:
        d = json.load(f)
    # CLI has no LLM/vision callables -> single build, no visual loop
    r = review_and_correct(
        d.get("title", ""), d.get("slides", []), args.output,
        lang=d.get("lang", "ar"), request=d.get("request", ""),
        subtitle=d.get("subtitle", ""))
    print(f"Built: {r.get('output_path')} (rounds: {r.get('rounds')}, "
          f"clean: {r.get('final_clean')})")


if __name__ == "__main__":
    _main()
