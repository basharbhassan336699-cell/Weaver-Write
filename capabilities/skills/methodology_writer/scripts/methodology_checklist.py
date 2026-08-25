"""
methodology_checklist.py — verify methodology completeness (working script)
===========================================================================
Pure-logic checker (bilingual). Scans a methodology text for the five
required elements and reports what is present/missing.

Usage:
    python methodology_checklist.py --file methodology.txt --lang ar
"""
from __future__ import annotations
import argparse

# keyword markers per element, per language
ELEMENTS = {
    "research_type": {
        "ar": ["نوع البحث", "منهج", "وصفي", "تجريبي", "نوعي", "كمي", "مختلط"],
        "en": ["research type", "descriptive", "experimental", "qualitative",
               "quantitative", "mixed method"],
    },
    "population": {
        "ar": ["مجتمع الدراسة", "مجتمع البحث", "المجتمع"],
        "en": ["population", "target group"],
    },
    "sample": {
        "ar": ["العينة", "عينة", "حجم العينة", "اختيار العينة"],
        "en": ["sample", "sampling", "sample size"],
    },
    "instruments": {
        "ar": ["أداة", "أدوات", "استبيان", "مقابلة", "ملاحظة", "اختبار"],
        "en": ["instrument", "questionnaire", "interview", "observation", "survey"],
    },
    "analysis": {
        "ar": ["تحليل", "إحصائي", "تحليل البيانات", "معالجة"],
        "en": ["analysis", "statistical", "data analysis", "processing"],
    },
}

LABELS = {
    "research_type": ("نوع البحث/المنهج", "Research type/method"),
    "population":    ("مجتمع الدراسة", "Study population"),
    "sample":        ("العينة", "Sample"),
    "instruments":   ("أدوات جمع البيانات", "Data-collection instruments"),
    "analysis":      ("أساليب التحليل", "Analysis methods"),
}


def check_methodology(text: str, lang: str = "ar") -> dict:
    """Return which elements are present/missing."""
    low = text.lower()
    present, missing = [], []
    for elem, kws in ELEMENTS.items():
        found = any(k.lower() in low for k in kws.get(lang, []) + kws.get("en", []))
        label = LABELS[elem][0 if lang == "ar" else 1]
        (present if found else missing).append(label)
    score = int(len(present) / len(ELEMENTS) * 100)
    return {
        "present": present, "missing": missing,
        "score": score, "complete": len(missing) == 0,
    }


def _main():
    p = argparse.ArgumentParser(description="Check methodology completeness")
    p.add_argument("--file", required=True)
    p.add_argument("--lang", default="ar", choices=["ar", "en"])
    args = p.parse_args()
    with open(args.file, encoding="utf-8") as f:
        text = f.read()
    r = check_methodology(text, args.lang)
    print(f"Completeness: {r['score']}% ({'complete' if r['complete'] else 'incomplete'})")
    if r["present"]:
        print("Present:", "، ".join(r["present"]))
    if r["missing"]:
        print("Missing:", "، ".join(r["missing"]))


if __name__ == "__main__":
    _main()
