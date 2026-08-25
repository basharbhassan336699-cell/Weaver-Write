"""
structures.py — academic research structures & planning (working script)
========================================================================
Builds a research outline/plan for a task, based on the structures we have
actually used before (recovered from prior work) plus standard academic
conventions for larger works.

Task tiers (auto-selected by size, overridable):
  assignment  — small: short intro + body + 3-4 refs
  medium      — report/medium project: intro + 3 مباحث (each 3 مطالب, 1.1.1
                sub-numbering) + conclusion + ~10 refs
  large       — graduation/master research (20-23 pages): intro (importance/
                problem/questions/objectives) + 5 مباحث (3 مطالب each +
                2.1.1 sub-divisions) + conclusion (results+recommendations)
                + ~12 refs
  thesis      — master/PhD: front matter + chapters (intro, lit review,
                methodology, results, discussion, conclusion) + refs +
                appendices

IMPORTANT override rule: if the task itself specifies a structure, or is a
set of questions to answer, or is a continuation/completion of earlier work,
DO NOT impose our structure — follow the task. `should_plan()` encodes this.

Bilingual: section names are provided in both ar and en.
"""
from __future__ import annotations


# ── section vocabularies (bilingual) ─────────────────────────
_SECTIONS = {
    "intro":       {"ar": "المقدمة", "en": "Introduction"},
    "problem":     {"ar": "إشكالية الدراسة", "en": "Research Problem"},
    "importance":  {"ar": "أهمية الدراسة", "en": "Significance of the Study"},
    "questions":   {"ar": "تساؤلات الدراسة", "en": "Research Questions"},
    "objectives":  {"ar": "أهداف الدراسة", "en": "Objectives"},
    "lit_review":  {"ar": "الإطار النظري والدراسات السابقة",
                    "en": "Literature Review"},
    "methodology": {"ar": "منهجية الدراسة", "en": "Methodology"},
    "results":     {"ar": "النتائج", "en": "Results"},
    "discussion":  {"ar": "المناقشة", "en": "Discussion"},
    "conclusion":  {"ar": "الخاتمة", "en": "Conclusion"},
    "results_recs":{"ar": "النتائج والتوصيات", "en": "Results and Recommendations"},
    "references":  {"ar": "المراجع", "en": "References"},
    "mabhath":     {"ar": "المبحث", "en": "Section"},
    "matlab":      {"ar": "المطلب", "en": "Subsection"},
}


def _name(key, lang):
    return _SECTIONS.get(key, {}).get(lang, key)


# ── tier detection ───────────────────────────────────────────
def detect_tier(task_card: dict) -> str:
    """Pick a structure tier from the task card (page/word count, type)."""
    ttype = (task_card.get("task_type") or "").lower()
    pages = task_card.get("page_count")
    n = 0
    if isinstance(pages, str):
        import re
        m = re.search(r"\d+", pages)
        n = int(m.group()) if m else 0
    elif isinstance(pages, (int, float)):
        n = int(pages)

    if ttype in ("thesis", "dissertation", "رسالة", "أطروحة"):
        return "thesis"
    if n >= 18 or ttype in ("graduation", "master", "تخرج", "ماجستير", "دكتوراه"):
        return "large"
    if ttype in ("assignment", "واجب") or (0 < n <= 4):
        return "assignment"
    return "medium"


# ── should we plan at all? ───────────────────────────────────
def should_plan(task_card: dict) -> bool:
    """
    Skip our structure if the task dictates one, is a Q&A, or continues
    earlier work. Otherwise plan.
    """
    if task_card.get("has_own_structure") or task_card.get("is_qa") \
            or task_card.get("continuation") or task_card.get("fragment"):
        return False
    return True


# ── builders per tier ────────────────────────────────────────
def _assignment(lang, topic):
    return {
        "tier": "assignment",
        "sections": [
            {"key": "intro", "title": _name("intro", lang), "level": 1},
            {"key": "body", "title": ("العرض" if lang == "ar" else "Body"),
             "level": 1},
            {"key": "conclusion", "title": _name("conclusion", lang), "level": 1},
            {"key": "references", "title": _name("references", lang), "level": 1},
        ],
        "reference_count": "3-4",
    }


def _medium(lang, topic):
    secs = [{"key": "intro", "title": _name("intro", lang), "level": 1}]
    for i in range(1, 4):  # 3 مباحث
        secs.append({"key": f"mabhath{i}",
                     "title": f"{_name('mabhath', lang)} {i}", "level": 1})
        for j in range(1, 4):  # 3 مطالب
            secs.append({"key": f"matlab{i}_{j}",
                         "title": f"{_name('matlab', lang)} {i}.{j}",
                         "level": 2, "numbering": f"{i}.{j}"})
    secs.append({"key": "conclusion", "title": _name("conclusion", lang), "level": 1})
    secs.append({"key": "references", "title": _name("references", lang), "level": 1})
    return {"tier": "medium", "sections": secs, "reference_count": "10",
            "sub_numbering": "1.1.1"}


def _large(lang, topic):
    # intro with 4 named parts
    secs = [{"key": "intro", "title": _name("intro", lang), "level": 1}]
    for part in ("importance", "problem", "questions", "objectives"):
        secs.append({"key": part, "title": _name(part, lang), "level": 2})
    # 5 مباحث, each 3 مطالب with 2.1.1 sub-divisions
    for i in range(1, 6):
        secs.append({"key": f"mabhath{i}",
                     "title": f"{_name('mabhath', lang)} {i}", "level": 1})
        for j in range(1, 4):
            secs.append({"key": f"matlab{i}_{j}",
                         "title": f"{_name('matlab', lang)} {i}.{j}",
                         "level": 2, "numbering": f"{i}.{j}",
                         "sub_divisions": [f"{i}.{j}.{k}" for k in range(1, 4)]})
    secs.append({"key": "results_recs",
                 "title": _name("results_recs", lang), "level": 1})
    secs.append({"key": "references", "title": _name("references", lang), "level": 1})
    return {"tier": "large", "sections": secs, "reference_count": "12",
            "sub_numbering": "2.1.1"}


def _thesis(lang, topic):
    chapters = ["intro", "lit_review", "methodology", "results",
                "discussion", "conclusion"]
    secs = [{"key": k, "title": _name(k, lang), "level": 1} for k in chapters]
    secs.append({"key": "references", "title": _name("references", lang), "level": 1})
    secs.append({"key": "appendices",
                 "title": ("الملاحق" if lang == "ar" else "Appendices"),
                 "level": 1})
    return {"tier": "thesis", "sections": secs, "reference_count": "25-40",
            "note": "front matter + chapters + refs + appendices"}


_BUILDERS = {"assignment": _assignment, "medium": _medium,
             "large": _large, "thesis": _thesis}


def build_structure(task_card: dict, lang="ar"):
    """
    Return a research structure/plan dict for the task, or None if the task
    dictates its own structure (Q&A, continuation, explicit outline).
    """
    if not should_plan(task_card):
        return None
    tier = task_card.get("tier") or detect_tier(task_card)
    topic = task_card.get("topic", "")
    builder = _BUILDERS.get(tier, _medium)
    plan = builder(lang, topic)
    plan["topic"] = topic
    plan["language"] = lang
    return plan


if __name__ == "__main__":
    import json
    for tier, card in [
        ("assignment", {"task_type": "assignment", "topic": "التسويق", "page_count": "2"}),
        ("medium", {"task_type": "report", "topic": "الاستدامة", "page_count": "8"}),
        ("large", {"task_type": "research", "topic": "التنمية", "page_count": "23"}),
        ("thesis", {"task_type": "thesis", "topic": "الذكاء الاصطناعي"}),
    ]:
        plan = build_structure(card, "ar")
        print(f"\n=== {tier} ({plan['tier']}) — {len(plan['sections'])} أقسام, "
              f"{plan['reference_count']} مراجع ===")
        for s in plan["sections"][:6]:
            print(f"  {'  '*(s['level']-1)}{s['title']}")
