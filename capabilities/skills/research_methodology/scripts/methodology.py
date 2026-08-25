"""
methodology.py — scientific research methodology helper (working script)
========================================================================
Provides the methodology scaffolding a research paper needs when it lacks
one: research approach, design, population/sample, instruments, data
collection, and analysis — with correct academic terminology in Arabic and
English.

It does NOT invent findings; it lays out the methodological structure and
prompts so the writing layer (with an LLM) fills it accurately for the topic.
"""
from __future__ import annotations

# bilingual methodology vocabulary
_APPROACHES = {
    "quantitative": {"ar": "المنهج الكمّي", "en": "Quantitative approach"},
    "qualitative": {"ar": "المنهج الكيفي", "en": "Qualitative approach"},
    "mixed": {"ar": "المنهج المختلط", "en": "Mixed-methods approach"},
    "descriptive": {"ar": "المنهج الوصفي", "en": "Descriptive approach"},
    "analytical": {"ar": "المنهج التحليلي", "en": "Analytical approach"},
    "experimental": {"ar": "المنهج التجريبي", "en": "Experimental approach"},
    "case_study": {"ar": "دراسة الحالة", "en": "Case study"},
    "historical": {"ar": "المنهج التاريخي", "en": "Historical approach"},
}

_COMPONENTS = {
    "approach": {"ar": "منهج الدراسة", "en": "Research Approach"},
    "design": {"ar": "تصميم الدراسة", "en": "Research Design"},
    "population": {"ar": "مجتمع الدراسة", "en": "Study Population"},
    "sample": {"ar": "عيّنة الدراسة", "en": "Study Sample"},
    "instruments": {"ar": "أدوات الدراسة", "en": "Research Instruments"},
    "data_collection": {"ar": "إجراءات جمع البيانات",
                        "en": "Data Collection Procedures"},
    "validity": {"ar": "صدق الأداة وثباتها", "en": "Validity and Reliability"},
    "analysis": {"ar": "أساليب تحليل البيانات",
                 "en": "Data Analysis Methods"},
    "ethics": {"ar": "الاعتبارات الأخلاقية", "en": "Ethical Considerations"},
    "limitations": {"ar": "حدود الدراسة", "en": "Study Limitations"},
}

# suggested approach by field/topic hints
_FIELD_HINTS = {
    "quantitative": ["إحصاء", "استبيان", "قياس", "survey", "statistic",
                     "measure", "correlation", "experiment"],
    "qualitative": ["مقابلة", "ملاحظة", "تحليل مضمون", "interview",
                    "observation", "content analysis", "ethnograph"],
    "descriptive": ["وصف", "واقع", "describe", "current state", "status"],
    "analytical": ["تحليل", "نقد", "analyze", "critique", "examine"],
}


def _name(d, key, lang):
    return d.get(key, {}).get(lang, key)


def suggest_approach(topic: str, field: str = "") -> str:
    """Guess a suitable research approach from topic keywords."""
    text = (topic + " " + field).lower()
    for approach, hints in _FIELD_HINTS.items():
        if any(h.lower() in text for h in hints):
            return approach
    return "descriptive"  # safe academic default


def build_methodology(task_card: dict, lang="ar"):
    """
    Return a methodology outline (components + suggested approach) for the
    topic. The writing layer fills each component with topic-specific text.
    """
    topic = task_card.get("topic", "")
    field = task_card.get("academic_field", "")
    approach = task_card.get("approach") or suggest_approach(topic, field)

    components = ["approach", "design", "population", "sample", "instruments",
                  "data_collection", "validity", "analysis", "ethics",
                  "limitations"]
    # small tasks need only the essentials
    tier = task_card.get("tier", "medium")
    if tier in ("assignment", "medium"):
        components = ["approach", "population", "sample", "instruments",
                      "data_collection", "analysis"]

    return {
        "language": lang,
        "suggested_approach": {
            "key": approach,
            "name": _name(_APPROACHES, approach, lang),
        },
        "components": [
            {"key": c, "title": _name(_COMPONENTS, c, lang)} for c in components
        ],
        "note": ("املأ كل مكوّن بمحتوى يخص الموضوع دون اختلاق بيانات"
                 if lang == "ar" else
                 "Fill each component with topic-specific content; invent no data"),
    }


def has_methodology(task_card: dict) -> bool:
    """Whether the task already includes/《needs》a methodology section."""
    secs = task_card.get("sections", [])
    keys = {s.get("key", "") for s in secs} if secs else set()
    return "methodology" in keys


if __name__ == "__main__":
    import json
    for topic in ["أثر الاستبيان على قياس الرضا", "تحليل نقدي لنظرية التنمية",
                  "impact of interviews on learning"]:
        card = {"topic": topic, "tier": "large"}
        m = build_methodology(card, "ar" if any('\u0600' <= c <= '\u06FF' for c in topic) else "en")
        print(f"\nالموضوع: {topic}")
        print(f"  المنهج المقترح: {m['suggested_approach']['name']}")
        print(f"  المكوّنات ({len(m['components'])}): "
              + "، ".join(c["title"] for c in m["components"][:4]) + " ...")
