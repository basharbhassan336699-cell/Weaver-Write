# -*- coding: utf-8 -*-
"""فحصُ نصٍّ على دستور الكتابة — حتميٌّ، بلا نداءِ نموذج.

المشكلةُ التي يحلّها: `--soul` يُثبت أنّ الدستورَ مُركَّب، و`--bootstrap`
يُثبت أنّه يصل البرومبت. **ولا شيءَ كان يُثبت أنّه يُتَّبع.** والدليلُ الوحيد
كان عينَ المستخدم — وهي التي كشفت فشلَ الخاتمة ثمّ فشلَ الشرطة، بالقراءة
لا بأمر. فصار ما تفعله العينُ أمراً يُعاد بعد كلِّ تعديل.

والقرارُ التصميميُّ الحاكم: **القائمةُ تُستخرَج من الدستور نفسِه، لا تُنسَخ.**
نسخةٌ ثانيةٌ تنحرف عن أصلها بعد تعديلين، فيصير الفاحصُ يقيس دستوراً لم يعد
موجوداً — وهو أسوأُ من لا فحص، لأنّه يطمئنك كذباً.

والفحصُ لا يحكم على المعنى — يقيس ما يُقاس:
    · كلمةٌ من قائمة المنع موجودة؟        عدٌّ ومطابقة
    · فقرتان متتاليّتان بنفس التركيب؟     مقارنةُ المطلع
    · شرطةٌ طويلةٌ ملتصقة؟                regex
    · خاتمةٌ تنتهي بتحشيد؟                قائمةُ أنماط

وما لا يُقاس (أهو نصٌّ جيّد؟) لا يُدّعى قياسُه.
"""
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUL_SRC = os.path.join(_ROOT, "capabilities", "prompts", "soul",
                        "SOUL.weaver.md")

# أنماطُ التحشيد في الخاتمة — القاعدةُ ٦ تمنعها بالاسم، وهي مذكورةٌ فيها
# كأمثلةٍ لا كقائمةٍ مُستخرَجة، فتُكتب هنا وتُفحَص مطابقتُها للدستور في
# tests/test_soul_check.py كي لا تنحرف.
_RALLY = ("رهنٌ بهذا التغيير", "رهن بهذا التغيير", "تضافر الجهود",
          "تضافرَ الجهود", "أملٌ في مستقبل", "أمل في مستقبل",
          "تكمن أهمية", "تكمن أهمّيّة", "لا غنى عنه", "لا بدّ من",
          "يجب على الجميع", "مسؤوليّة الجميع", "مسؤولية الجميع",
          "نحو مستقبل أفضل", "خيارٌ بل ضرورة", "خيار بل ضرورة")


def _section(text, num):
    """نصُّ قسمٍ من الدستور بعنوانه الرقميّ، أو ""."""
    m = re.search(r"^## " + num + r"\).*?$(.*?)(?=^## |\Z)", text,
                  re.M | re.S)
    return m.group(1) if m else ""


def _terms(block):
    """مصطلحاتُ كتلةٍ مفصولةٍ بـ« · » — مع احترام الاقتباسات."""
    out = []
    for raw in block.replace("\n", " ").split("·"):
        t = raw.strip().strip("،.").strip()
        if not t or t.startswith("و") and len(t) < 3:
            continue
        # «"in conclusion"» ⟶ in conclusion
        q = re.match(r'^"(.+)"$', t)
        if q:
            t = q.group(1)
        out.append(t)
    return [t for t in out if 2 <= len(t) <= 60]


def banned_terms(soul_text=None):
    """قائمةُ المنع المطلق — مُستخرَجةٌ من القسم ٢ ومن كتلة «ممنوعةٌ لا مُقلَّلة».

    تعيد (إنجليزيّ، عربيّ)."""
    t = soul_text
    if t is None:
        try:
            with open(SOUL_SRC, encoding="utf-8") as fh:
                t = fh.read()
        except Exception:
            return [], []
    sec2 = _section(t, "٢")
    # القسمُ ٢ ثلاثُ كتل: إنجليزيّة، ثمّ «وبالعربيّة —»، ثمّ فقرةُ الشرطة.
    parts = sec2.split("وبالعربيّة")
    en = _terms(parts[0])
    ar = []
    if len(parts) > 1:
        # حتى فقرة الشرطة
        ar_block = parts[1].split("والشرطةُ")[0]
        ar_block = ar_block.split(":", 1)[-1]
        ar = _terms(ar_block)
    # وكتلةُ «ممنوعةٌ لا مُقلَّلة» في القسم ٤
    m = re.search(r"ممنوعةٌ لا مُقلَّلة\*\*[^\n]*\n(.+?)(?=\n\n|\Z)", t, re.S)
    if m:
        ar += _terms(m.group(1))
    _en = [x for x in en if re.search(r"[A-Za-z]", x)]
    _ar = [x for x in ar if re.search(r"[؀-ۿ]", x)]
    return sorted(set(_en)), sorted(set(_ar))


def _paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", str(text or ""))
            if p.strip() and not p.strip().startswith(("#", "|", "```"))]


def _opening(par):
    """بصمةُ مطلعِ الفقرة: أوّلُ كلمةٍ + أهي فعلٌ مضارع؟"""
    w = re.sub(r"^[^\w؀-ۿ]+", "", par).split()
    first = w[0] if w else ""
    pres = bool(re.match(r"^[يتن]ُ?[؀-ۿ]{2,}$", first))
    return first, pres


def check(text, soul_text=None):
    """افحص نصّاً. يعيد dict ولا يرفع استثناءً.

    {ok, score, violations:[{rule,term,where}], warnings:[…], stats:{…}}
    """
    out = {"ok": False, "score": 0, "violations": [], "warnings": [],
           "stats": {}}
    try:
        t = str(text or "")
        if not t.strip():
            out["violations"].append({"rule": "فارغ", "term": "", "where": ""})
            return out
        en, ar = banned_terms(soul_text)
        # عبارةٌ من عدّة كلماتٍ قد يكتبها النموذجُ على سطرين، فيفلت المطابقةَ
        # الحرفيّة. (كشفه الفحصُ نفسُه: «it is important to note that» مكتوبةٌ
        # في الدستور على سطرين، فلم تُطابق نصَّه.) فتُسطَّح المسافاتُ قبل
        # البحث — والمواضعُ تُحسب على المُسطَّح، وهو ما نبحث فيه.
        flat = " ".join(t.split())
        low = flat.lower()

        # ① المنعُ المطلق
        for w in en:
            if re.search(r"\b" + re.escape(w.lower()) + r"\b", low):
                out["violations"].append(
                    {"rule": "ممنوعٌ مطلقاً (إنجليزيّ)", "term": w,
                     "where": ""})
        for w in ar:
            if w in flat:
                out["violations"].append(
                    {"rule": "ممنوعٌ مطلقاً (عربيّ)", "term": w, "where": ""})

        # ② الشرطةُ الملتصقة — البصمةُ الحقيقيّة
        n_glued = len(re.findall(r"\S—\S", t))
        if n_glued:
            out["violations"].append(
                {"rule": "شرطةٌ طويلةٌ ملتصقة", "term": "كلمة—كلمة",
                 "where": "%d موضعاً" % n_glued})

        # ③ مطالعُ الفقرات
        pars = _paragraphs(t)
        opens = [_opening(p) for p in pars]
        for i in range(1, len(opens)):
            if opens[i][0] and opens[i][0] == opens[i - 1][0]:
                out["violations"].append(
                    {"rule": "فقرتان متتاليّتان بنفس المطلع",
                     "term": opens[i][0], "where": "الفقرة %d" % (i + 1)})
            elif opens[i][1] and opens[i - 1][1]:
                out["warnings"].append(
                    {"rule": "فقرتان متتاليّتان تبدآن بمضارع",
                     "term": "%s / %s" % (opens[i - 1][0], opens[i][0]),
                     "where": "الفقرة %d" % (i + 1)})

        # ④ الخاتمة — آخرُ فقرةٍ فيها تحشيد؟
        if pars:
            last = pars[-1]
            for r in _RALLY:
                if r in last:
                    out["violations"].append(
                        {"rule": "خاتمةٌ بتحشيدٍ أو عبارةِ أهمّيّة",
                         "term": r, "where": "الفقرة الأخيرة"})
                    break

        # ⑤ تنويعُ الأطوال — تحذيرٌ لا مخالفة (القياسُ تقريبيّ)
        sents = [s for s in re.split(r"[.؟!]\s+", t) if len(s.split()) >= 3]
        lens = [len(s.split()) for s in sents]
        if len(lens) >= 4:
            run = 1
            for i in range(1, len(lens)):
                if abs(lens[i] - lens[i - 1]) <= 3:
                    run += 1
                    if run >= 3:
                        out["warnings"].append(
                            {"rule": "ثلاثُ جملٍ متتاليةٍ متقاربةُ الطول",
                             "term": str(lens[i - 2:i + 1]), "where": ""})
                        break
                else:
                    run = 1
        out["stats"] = {"words": len(t.split()), "paragraphs": len(pars),
                        "sentences": len(sents),
                        "banned_checked": len(en) + len(ar)}
        n = len(out["violations"])
        out["ok"] = n == 0
        out["score"] = max(0, 100 - n * 10)
    except Exception as e:
        out["violations"].append(
            {"rule": "عطبٌ في الفحص", "term": type(e).__name__,
             "where": str(e)[:120]})
    return out
