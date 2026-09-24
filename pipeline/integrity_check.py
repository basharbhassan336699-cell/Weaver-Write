#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""حارسُ إعادة الصياغة — أبقيَ ما لا يُمَسّ كما هو؟

لا يغيّر شيئاً ولا ينادي نموذجاً: يقارن النصَّ قبل إعادة الصياغة وبعدها،
ويقول بالتحديد ما تغيّر ممّا يمنعه الدستور (SOUL.md § ٧):

  • الاستشهادات   — نفسُها حرفاً، وبترتيبها نفسِه. العدُّ وحده لا يكفي:
                    استشهادٌ ينتقل إلى موضعٍ آخر يُبقي العددَ صحيحاً ويزوّر
                    المعنى — فالترتيبُ يُفحص أيضاً.
  • الأرقامُ والنسب — خارج الاستشهادات، كما هي (والهنديّةُ تُطابَق بالعربيّة).
  • الاقتباساتُ   — ما بين «» و“” و"" حرفاً.
  • الطول         — لم يَقصُر بأكثر من الثلث (حذفٌ لا صياغة).

تستعمله مهارتا academic-humanize وvoice-inject بعد كلِّ إعادة صياغة: فإن
قال intact: false سُلِّم الأصلُ وأُبلغ المستخدم.

    python3 pipeline/integrity_check.py --original a.txt --rewritten b.txt
    رموزُ الخروج: 0 سليم · 1 تغيّر ما لا يُمَسّ · 2 خطأ استعمال
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
# (المؤلّف، 2020، ص. 45) · (Smith et al., 2019, p. 12) · (الفهري، د.ت)
_CIT_PAREN = re.compile(
    r"\((?=[^()]{0,160}?(?:1[5-9]\d\d|20\d\d|[١][٥-٩][٠-٩]{2}|[٢][٠][٠-٩]{2}"
    r"|n\.d\.|د\.\s?ت))[^()]{1,200}\)")
# [12] · [3, 4] · [5–7]
_CIT_BRACK = re.compile(r"\[\d+(?:\s*[,،\-–]\s*\d+)*\]")
_NUM = re.compile(r"(?<![\w.])\d+(?:[.,٫]\d+)*\s*[%٪]?")
_QUOTES = (("«", "»"), ("“", "”"), ('"', '"'))


def _flat(s):
    return " ".join(str(s or "").split())


def citations(text):
    """الاستشهاداتُ بترتيب ظهورها، مسطّحةَ الفراغات."""
    t = str(text or "")
    found = [(m.start(), _flat(m.group(0))) for m in _CIT_PAREN.finditer(t)]
    found += [(m.start(), _flat(m.group(0))) for m in _CIT_BRACK.finditer(t)]
    return [c for _p, c in sorted(found)]


def numbers(text):
    """الأرقامُ خارج الاستشهادات — كمجموعةٍ بتكرارها."""
    t = str(text or "")
    t = _CIT_PAREN.sub(" ", t)
    t = _CIT_BRACK.sub(" ", t)
    return Counter(re.sub(r"\s+", "", m.group(0)).translate(_DIGITS)
                   .replace("٫", ".").replace("٪", "%")
                   for m in _NUM.finditer(t.translate(_DIGITS)))


def quotes(text):
    t = str(text or "")
    out = []
    for op, cl in _QUOTES:
        i = 0
        while True:
            a = t.find(op, i)
            if a < 0:
                break
            b = t.find(cl, a + 1)
            if b < 0:
                break
            out.append(_flat(t[a + 1:b]))
            i = b + 1
    return Counter(q for q in out if q)


def check(original, rewritten):
    """dict: intact، problems، والأعدادُ قبلُ وبعد. لا يرفع استثناءً."""
    problems = []
    try:
        c0, c1 = citations(original), citations(rewritten)
        if Counter(c0) != Counter(c1):
            lost = list((Counter(c0) - Counter(c1)).elements())
            added = list((Counter(c1) - Counter(c0)).elements())
            if lost:
                problems.append("استشهادٌ فُقد أو تغيّر: " + " · ".join(lost[:5]))
            if added:
                problems.append("استشهادٌ جديدٌ لم يكن في الأصل: "
                                + " · ".join(added[:5]))
        elif c0 != c1:
            problems.append("الاستشهاداتُ نفسُها لكن تغيّر ترتيبُها — "
                            "استشهادٌ انتقل إلى موضعٍ آخر")
        n0, n1 = numbers(original), numbers(rewritten)
        if n0 != n1:
            lost = list((n0 - n1).elements())
            added = list((n1 - n0).elements())
            problems.append("الأرقامُ تغيّرت: فُقد [%s] وأُضيف [%s]"
                            % (" ".join(lost[:8]), " ".join(added[:8])))
        q0, q1 = quotes(original), quotes(rewritten)
        lostq = list((q0 - q1).elements())
        if lostq:
            problems.append("اقتباسٌ مباشرٌ تغيّر: «%s»" % lostq[0][:80])
        w0 = len(_flat(original).split())
        w1 = len(_flat(rewritten).split())
        if w0 >= 30 and w1 < w0 * 2 / 3:
            problems.append("النصُّ قصُر بأكثر من الثلث (%d ⟵ %d كلمة) — "
                            "حذفٌ لا صياغة" % (w0, w1))
        return {"intact": not problems, "problems": problems,
                "citations": [len(c0), len(c1)],
                "numbers": [sum(n0.values()), sum(n1.values())],
                "quotes": [sum(q0.values()), sum(q1.values())],
                "words": [w0, w1]}
    except Exception as e:
        return {"intact": False, "problems": ["تعذّر الفحص: %s" % e],
                "citations": [0, 0], "numbers": [0, 0], "quotes": [0, 0],
                "words": [0, 0]}


def _read(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description="حارسُ إعادة الصياغة — لا يغيّر شيئاً.")
    ap.add_argument("--original", required=True, help="ملفُّ الأصل")
    ap.add_argument("--rewritten", required=True, help="ملفُّ الصياغة الجديدة")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = check(_read(a.original), _read(a.rewritten))
    except OSError as e:
        print("✗ تعذّرت القراءة: %s" % e, file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("  الاستشهادات: %d ⟵ %d · الأرقام: %d ⟵ %d · الاقتباسات: %d ⟵ %d"
              " · الكلمات: %d ⟵ %d" % (tuple(r["citations"]) + tuple(r["numbers"])
                                      + tuple(r["quotes"]) + tuple(r["words"])))
        for p in r["problems"]:
            print("  ✗ " + p)
        print("  intact: %s" % r["intact"])
    return 0 if r["intact"] else 1


if __name__ == "__main__":
    sys.exit(main())
