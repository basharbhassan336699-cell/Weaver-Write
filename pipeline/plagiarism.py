#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""قياسُ النقل الحرفيّ — كم نسخ النصُّ من مصادره كلمةً بكلمة.

ليس مطابقةَ كلماتٍ ممنوعة، ولا يتحكّم في النموذج: **يقارن نصَّين** — نصَّك
ونصَّ المصدر الذي قرأه النظام — ويبحث عن سلاسلَ متطابقةٍ حرفياً. لا يغيّر
حرفاً في نصّك، ولا ينادي نموذجاً (صفرُ نداءات)، ونتيجتُه واحدةٌ في كلّ مرّة.

الفكرةُ نفسُها في `Orchestrator._verbatim_overlap`
(pipeline/orchestrator.py) — داخلَ طبقةٍ معطَّلةٍ لا تُمَسّ. وحدُّها من منهجيّة
البحث نفسِها (capabilities/skills/web_research/scripts/web_research.py):

    MAX_QUOTE_WORDS = 15    # اقتباسٌ مباشرٌ واحدٌ لكلّ مصدر، دون ~١٥ كلمة

فالسلسلةُ المنقولةُ هنا **١٥ كلمةً متتاليةً فأكثر** خارجَ علامات الاقتباس.
والدالّةُ الأصليّةُ تعطي أطولَ سلسلةٍ وحدَها؛ وهذا يعطيها، ومعها كلُّ مقطعٍ
منقولٍ ومصدرُه، ونسبةُ المنقول من النصّ.

الاقتباسُ المشروعُ لا يُعدّ نقلاً: ما بين «» أو “” أو "" يُستثنى ويُعَدّ
وحدَه، فترى كم اقتبس النصُّ صراحةً.

حدودٌ صادقة:
  • يقارن بالمصادر التي تُعطيه وحدَها — لا بالإنترنت كلِّه.
  • يكشف النسخَ الحرفيّ؛ تغييرُ كلمةٍ كلَّ بضعِ كلماتٍ يفوته.
  • التطبيعُ خفيف: يزيل التشكيلَ والتطويل، ويوحّد (أ إ آ ⟵ ا، ى ⟵ ي، ة ⟵ ه)
    والأرقامَ الهنديّة، ويُصغّر اللاتينيّة — كي لا تُخفيَ حركةٌ نقلاً.

الاستعمال:
    python3 pipeline/plagiarism.py --file doc.txt --url https://… --url https://…
    python3 pipeline/plagiarism.py --text "…" --source-text "…" --json
    رموزُ الخروج: 0 لا نقل · 1 نقلٌ حرفيّ · 3 لم يُقَس (لا مصدرَ قُرئ) · 2 خطأ استعمال
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser

MIN_WORDS = 15            # = web_research.MAX_QUOTE_WORDS
MAX_BYTES = 5_000_000     # حدُّ تنزيل الصفحة الواحدة
_MARKS = "\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640"
_TOKEN = re.compile(r"[\w" + _MARKS + r"]+", re.U)
_STRIP = re.compile("[" + _MARKS + "]")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي",
                       "ة": "ه", "ؤ": "و", "ئ": "ي",
                       "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
                       "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9"})
_QUOTES = (("«", "»"), ("“", "”"), ("„", "“"), ('"', '"'))


# ── النصّ ⟵ كلمات ─────────────────────────────────────────────────────────
def _norm(w):
    return _STRIP.sub("", w).translate(_FOLD).lower()


def tokenize(text):
    """[(كلمةٌ مطبَّعة، بدايةٌ، نهاية)] — المواضعُ في النصّ الأصليّ للعرض."""
    out = []
    for m in _TOKEN.finditer(str(text or "")):
        n = _norm(m.group(0))
        if n and n.strip("_"):
            out.append((n, m.start(), m.end()))
    return out


def quoted_spans(text):
    """[(بداية، نهاية)] لما بين علامات الاقتباس — الاقتباسُ المشروع."""
    t = str(text or "")
    spans = []
    for op, cl in _QUOTES:
        i = 0
        while True:
            a = t.find(op, i)
            if a < 0:
                break
            b = t.find(cl, a + 1)
            if b < 0:
                break
            spans.append((a, b + 1))
            i = b + 1
    return spans


# ── المصدر ⟵ نصّ ──────────────────────────────────────────────────────────
class _Text(HTMLParser):
    """نصُّ الصفحة بلا سكربتٍ ولا قوائم — احتياطٌ حين لا يتوفّر Trafilatura."""
    SKIP = {"script", "style", "noscript", "nav", "header", "footer",
            "aside", "form", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html):
    """نصُّ المقال: Trafilatura إن وُجد (مدمجٌ في النظام)، وإلّا المكتبةُ
    القياسيّة. لا يرفع استثناءً."""
    try:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _uw = os.path.join(_root, "engines", "uniweb-core")
        if os.path.isdir(_uw) and _uw not in sys.path:
            sys.path.insert(0, _uw)
        import trafilatura  # noqa: WPS433 — اختياريّ
        t = trafilatura.extract(html, include_comments=False,
                                include_tables=True)
        if t and len(t.split()) >= MIN_WORDS:
            return t
    except Exception:
        pass
    try:
        p = _Text()
        p.feed(str(html or ""))
        return " ".join("".join(p.parts).split())
    except Exception:
        return ""


def fetch(url, timeout=20):
    """(نصّ، خطأ) — الصفحةُ كما يقرؤها النظام. لا يرفع استثناءً."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Weaver Write; plagiarism check)",
            "Accept": "text/html,text/plain,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(MAX_BYTES)
            ctype = (r.headers.get("Content-Type") or "").lower()
            cs = r.headers.get_content_charset() or "utf-8"
        if "pdf" in ctype or raw[:5] == b"%PDF-":
            return "", "PDF — لا يُقرأ هنا؛ مرّر نصَّه بـ--source-file"
        body = raw.decode(cs, errors="replace")
        if "html" in ctype or "<html" in body[:2000].lower():
            body = html_to_text(body)
        return body, None
    except Exception as e:
        return "", "%s: %s" % (type(e).__name__, str(e)[:160])


def read_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            t = fh.read()
        if path.lower().endswith((".html", ".htm")) or "<html" in t[:2000].lower():
            t = html_to_text(t)
        return t, None
    except Exception as e:
        return "", "%s: %s" % (type(e).__name__, str(e)[:160])


# ── القياس ────────────────────────────────────────────────────────────────
def measure(draft, sources, min_words=MIN_WORDS):
    """قارن النصَّ بمصادره. dict، ولا يرفع استثناءً.

    sources: [{"name": رابطٌ أو ملفّ، "text": نصُّه}]
    الطريقة: كلُّ سلسلةٍ من `min_words` كلمةً في المصدر تُحفَظ، ثمّ يُمرّ على
    النصّ: أيُّ سلسلةٍ منه بالطول نفسِه موجودةٌ في مصدرٍ ⟵ كلماتُها منقولة.
    والسلاسلُ المتّصلةُ تُضَمّ مقطعاً واحداً — فالمقطعُ هو أطولُ نقلٍ متّصل."""
    k = max(3, int(min_words or MIN_WORDS))
    toks = tokenize(draft)
    n = len(toks)
    qs = quoted_spans(draft)
    quoted = [any(a <= s < b for a, b in qs) for _w, s, _e in toks]
    grams, used = {}, []
    for i, src in enumerate(sources or []):
        sw = [w for w, _s, _e in tokenize(src.get("text") or "")]
        used.append({"name": src.get("name", "?"), "words": len(sw)})
        for j in range(len(sw) - k + 1):
            grams.setdefault(tuple(sw[j:j + k]), i)
    norm = [w for w, _s, _e in toks]
    covered, votes = [False] * n, [None] * n
    for p in range(n - k + 1):
        if any(quoted[p:p + k]):
            continue
        src_i = grams.get(tuple(norm[p:p + k]))
        if src_i is None:
            continue
        for q in range(p, p + k):
            covered[q] = True
            if votes[q] is None:
                votes[q] = src_i
    spans, p = [], 0
    while p < n:
        if not covered[p]:
            p += 1
            continue
        q = p
        while q < n and covered[q]:
            q += 1
        vs = [v for v in votes[p:q] if v is not None]
        src_i = max(set(vs), key=vs.count) if vs else None
        a, b = toks[p][1], toks[q - 1][2]
        excerpt = " ".join(str(draft)[a:b].split())
        spans.append({"words": q - p,
                      "source": used[src_i]["name"] if src_i is not None
                      else "?",
                      "excerpt": excerpt if len(excerpt) <= 240
                      else excerpt[:237] + "…"})
        p = q
    spans.sort(key=lambda s: -s["words"])
    n_quoted = sum(quoted)
    checked = n - n_quoted
    copied = sum(covered)
    measured = any(u["words"] >= k for u in used)
    return {
        "verdict": ("UNMEASURED" if not measured
                    else "COPIED" if spans else "CLEAN"),
        "min_words": k,
        "words": n,
        "quoted_words": n_quoted,
        "copied_words": copied,
        "copied_percent": round(100.0 * copied / checked, 1) if checked else 0.0,
        "longest_run": spans[0]["words"] if spans else 0,
        "spans": spans,
        "sources": used,
    }


# ── الطرفيّة ──────────────────────────────────────────────────────────────
def _report(r):
    L = []
    L.append("  الكلمات: %d · بين علامات اقتباس (مُستثناة): %d"
             % (r["words"], r["quoted_words"]))
    L.append("  المصادر:")
    for s in r["sources"]:
        L.append("    %s %s  (%d كلمة)%s" % (
            "✓" if s["words"] >= r["min_words"] else "✗", s["name"],
            s["words"], ("  ⟵ " + s["error"]) if s.get("error") else ""))
    L.append("")
    if r["verdict"] == "UNMEASURED":
        L.append("  ⚠ لم يُقَس — لم يُقرأ أيُّ مصدر، فلا حكمَ على شيء.")
        return "\n".join(L)
    L.append("  أطولُ نقلٍ حرفيّ : %d كلمة   (الحدّ: %d كلمةً متتالية)"
             % (r["longest_run"], r["min_words"]))
    L.append("  المنقولُ من النصّ : %d كلمة = %.1f٪"
             % (r["copied_words"], r["copied_percent"]))
    for s in r["spans"][:10]:
        L.append("\n  ⚠ %d كلمة من %s:\n    «%s»"
                 % (s["words"], s["source"], s["excerpt"]))
    L.append("")
    L.append("  ✓ لا نقلَ حرفيّ" if r["verdict"] == "CLEAN"
             else "  ✗ فيه نقلٌ حرفيّ — أعِد صياغةَ المقاطع أعلاه بكلماتك، "
                  "أو ضعها بين «» مع مصدرها")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="قياسُ النقل الحرفيّ من المصادر — لا يغيّر النصّ.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--text", help="النصُّ المفحوص")
    g.add_argument("--file", help="ملفُّ النصّ المفحوص (- للإدخال القياسيّ)")
    ap.add_argument("--url", action="append", default=[],
                    help="رابطُ مصدر (يُكرَّر)")
    ap.add_argument("--source-file", action="append", default=[],
                    help="ملفُّ مصدر: نصٌّ أو HTML (يُكرَّر)")
    ap.add_argument("--source-text", action="append", default=[],
                    help="نصُّ مصدرٍ مباشرةً (يُكرَّر)")
    ap.add_argument("--min-words", type=int, default=MIN_WORDS,
                    help="أقصرُ سلسلةٍ تُعَدّ نقلاً (الافتراضيّ 15)")
    ap.add_argument("--json", action="store_true", help="خرجٌ بصيغة JSON")
    a = ap.parse_args(argv)

    if a.text is not None:
        draft = a.text
    elif a.file == "-":
        draft = sys.stdin.read()
    else:
        draft, err = read_file(a.file)
        if err:
            print("✗ تعذّرت قراءةُ النصّ: " + err, file=sys.stderr)
            return 2
    if not (a.url or a.source_file or a.source_text):
        print("✗ لا مصدر — أعطِ --url أو --source-file أو --source-text",
              file=sys.stderr)
        return 2

    sources, errors = [], {}
    for u in a.url:
        t, err = fetch(u)
        sources.append({"name": u, "text": t})
        if err:
            errors[u] = err
    for f in a.source_file:
        t, err = read_file(f)
        sources.append({"name": f, "text": t})
        if err:
            errors[f] = err
    for i, t in enumerate(a.source_text, 1):
        sources.append({"name": "نصُّ المصدر %d" % i, "text": t})

    r = measure(draft, sources, a.min_words)
    for s in r["sources"]:
        if s["name"] in errors:
            s["error"] = errors[s["name"]]
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(_report(r))
    return {"CLEAN": 0, "COPIED": 1}.get(r["verdict"], 3)


if __name__ == "__main__":
    sys.exit(main())
