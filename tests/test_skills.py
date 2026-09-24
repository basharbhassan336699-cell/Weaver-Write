# -*- coding: utf-8 -*-
"""المهاراتُ الثلاثُ الآمنة — ما بعد التوليد.

القسمةُ التي بنينا عليها: ما يمنع البصمةَ قبل ولادتها في `SOUL.md` (دستورٌ
يُحقَن في كلِّ نوبة)؛ وما يصلحها بعدها مهارةٌ **يستدعيها النموذجُ حين يقرّر**.

والمُركَّبُ هنا الآمنُ وحدَه:
  detect-ai       قياسٌ فقط، لا يُعيد صياغةَ شيء
  fix-conclusion  فقرةٌ واحدةٌ لا النصُّ كلُّه
  humanize-ar     سكربتٌ محلّيٌّ مُختبَرٌ بحارسِ استشهادات، صفرُ نداءات

و`rewrite-from-ideas` مؤجَّلةٌ عمداً: «انسَ الصياغةَ الأصليّة» يُزحزح
الاستشهادَ عن جملته، والعدُّ يقول «سليم» والمعنى مزوَّر.

وأخطرُ ما في المهارة **وصفُها**: وصفٌ غامضٌ يجعلها ميّتةً بلا رسالةِ خطأ،
ووصفٌ فضفاضٌ يجعلها تعمل على «مرحباً». فأكثرُ الفحوص هنا عن الوصف والحدود.
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from pipeline import weaver_core as wc   # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


WANT = ("detect-ai", "fix-conclusion", "humanize-ar", "check-plagiarism")
BODY = {}
for n in WANT:
    p = os.path.join(wc.SKILLS_SRC, n, "SKILL.md")
    BODY[n] = open(p, encoding="utf-8").read() if os.path.isfile(p) else ""


def front(t, key):
    m = re.search(rf"^{key}:\s*(.+)$", t, re.M)
    return m.group(1).strip() if m else ""


print("\n— الملفّات —")
for n in WANT:
    ok(f"{n} موجودة", bool(BODY[n].strip()))
ok("ولا غيرَها (الخطرةُ مؤجّلة)",
   set(wc._skill_names()) == set(WANT), wc._skill_names())
ok("ولا rewrite-from-ideas", "rewrite-from-ideas" not in wc._skill_names())

print("\n— الواجهة: الاسمُ والوصفُ هما ما يدخل البرومبت —")
for n in WANT:
    t = BODY[n]
    ok(f"{n}: الاسمُ يطابق المجلّد", front(t, "name") == n, front(t, "name"))
    d = front(t, "description")
    ok(f"  ⟵ وصفٌ ذو طول ({len(d)} حرفاً)", 80 <= len(d) <= 320, len(d))
    ok("  ⟵ وبالعربيّة والإنجليزيّة معاً",
       any("؀" <= c <= "ۿ" for c in d)
       and any("a" <= c.lower() <= "z" for c in d))

print("\n— الحدود: كلُّ مهارةٍ تقول متى لا تُستدعى —")
ok("detect-ai: قياسٌ لا إعادةُ صياغة", "لا تُعد صياغةَ شيء" in BODY["detect-ai"])
ok("  ⟵ وللنصِّ الخارجيِّ وحدَه", "من خارج النظام" in BODY["detect-ai"])
ok("  ⟵ ولا على ما كتبتَه في هذه النوبة",
   "كتبتَه أنت في هذه النوبة" in BODY["detect-ai"])
ok("  ⟵ ويقول إنّ النسبةَ تقديرٌ لا قياس",
   "تقديرٌ لا قياس" in BODY["detect-ai"])
ok("fix-conclusion: الفقرةُ الأخيرةُ وحدَها",
   "لا تمسَّ النصَّ إلّا فقرتَه الأخيرة" in BODY["fix-conclusion"])
ok("  ⟵ ويترك D/E/F ولا يُصلح السليم",
   "لا تُصلح ما ليس معطوباً" in BODY["fix-conclusion"])
ok("  ⟵ ولا يُضيف معلومةً ليست في النصّ",
   "لا تُضف معلومةً ليست في النصّ" in BODY["fix-conclusion"])
ok("humanize-ar: لا على نصٍّ كتبتَه أنت",
   "لا تستدعِها على نصٍّ كتبتَه أنت" in BODY["humanize-ar"])
ok("  ⟵ و--general 0 إلزاميّ (القاموسُ العامُّ يُخرّب)",
   "--general 0" in BODY["humanize-ar"]
   and "إلزاميّ" in BODY["humanize-ar"])
ok("  ⟵ ويُصلح ما كسره الاستبدالُ من إعراب",
   "كُسر الإعرابُ" in BODY["humanize-ar"])
ok("  ⟵ ويرفض التسليمَ عند intact: False",
   "لا تُسلّم الناتج" in BODY["humanize-ar"])
ok("  ⟵ وعند فقدِ أكثرَ من الثلث",
   "أقصرَ بأكثر من الثلث" in BODY["humanize-ar"])

ok("check-plagiarism: قياسٌ لا يغيّر حرفاً",
   "لا تغيّر حرفاً في النصّ" in BODY["check-plagiarism"])
ok("  ⟵ ولا على نصٍّ بلا مصادر",
   "نصٌّ بلا مصادر" in BODY["check-plagiarism"])
ok("  ⟵ ولا يدّعي «خالٍ من السرقة» مطلقاً",
   "لا تقل «خالٍ من السرقة»" in BODY["check-plagiarism"])
ok("  ⟵ ولم يُقَس ⟵ يُبلغ ولا يدّعي السلامة",
   "UNMEASURED" in BODY["check-plagiarism"]
   and "لا تدّعِ أنّ النصَّ سليم" in BODY["check-plagiarism"])
ok("  ⟵ ولا يمسّ الاستشهادات لينجح",
   "لا تُعدّل الاستشهاداتِ" in BODY["check-plagiarism"])
_pb = wc._skill_body("check-plagiarism")
ok("  ⟵ ومسارُ السكربت يُحَلّ إلى ملفٍّ موجود",
   any(os.path.isfile(x) for x in re.findall(r"(/\S+plagiarism\.py)", _pb)))

print("\n— السلسلة: detect-ai تُشغّل البقيّة، لا سكربت —")
ok("تُخرج next_skills", "next_skills" in BODY["detect-ai"])
ok("  ⟵ وتسمّي fix-conclusion", "fix-conclusion" in BODY["detect-ai"])
ok("  ⟵ وhumanize-ar", "humanize-ar" in BODY["detect-ai"])

print("\n— المسار: {{WEAVER}} يُحَلّ عند التركيب —")
ok("المصدرُ فيه العلامة", wc._SKILLS_MARK in BODY["humanize-ar"])
_b = wc._skill_body("humanize-ar")
ok("والمُركَّبُ بلا علامة", wc._SKILLS_MARK not in _b)
ok("  ⟵ وبمسارٍ مطلقٍ موجود",
   any(os.path.isfile(x) for x in re.findall(r"(/\S+rewrite_ar\.py)", _b)),
   re.findall(r"(/\S+rewrite_ar\.py)", _b))

print("\n— الدوالّ والأمان —")
for n in ("skills_dir", "skills_on", "skills_state", "skills_apply",
          "skills_remove", "skills_seen"):
    ok(n + " موجودة", callable(getattr(wc, n, None)))
_src = open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
            encoding="utf-8").read()
ok("تحريرُك يُرفَض بلا --force", '"edited"' in _src and "لن تُدهَس" in _src)
ok("والحذفُ لا يمسُّ ما ليس لنا",
   'if row["state"] in ("ours", "old", "edited")' in _src)
ok("والتلقائيُّ يُطفأ بالبيئة", "WEAVER_SKILLS" in _src)
ok("وواجهةُ الطرفيّة --skills", '"--skills"' in _src)
ok("وتُركَّب بعد البذر مع الدستور", "skills_apply()" in _src)

print("\n— الترقية: نسخُنا السابقةُ تُرقّى، وتحريرُك محميّ —")
import hashlib as _hl
for n in WANT:
    _h = _hl.sha256(BODY[n].strip().encode("utf-8")).hexdigest()[:16]
    # عدّلتَ SKILL.md؟ أضف بصمتَه إلى _SKILLS_PAST — وإلّا بدت نسختُه
    # المُركَّبةُ بعد التعديل التالي «مُحرَّرةً بيدك».
    ok(f"{n}: نسختُه الحاليّةُ في _SKILLS_PAST", _h in wc._SKILLS_PAST.get(n, ()),
       _h)
import tempfile as _tf
_real_sd, _real_body = wc.skills_dir, wc._skill_body
try:
    _d = _tf.mkdtemp()
    wc.skills_dir = lambda: _d
    _n = "humanize-ar"
    _prev = _real_body(_n)                         # ما رُكِّب سابقاً (بمساره المحلول)
    os.makedirs(os.path.join(_d, _n))
    open(os.path.join(_d, _n, "SKILL.md"), "w", encoding="utf-8").write(_prev)
    wc._skill_body = lambda n: _real_body(n) + ("\nسطرٌ جديدٌ في المصدر.\n"
                                                if n == _n else "")
    _row = [r for r in wc.skills_state()["skills"] if r["name"] == _n][0]
    ok("المُركَّبُ نسخةٌ سابقة (والمصدرُ تغيّر) ⟵ old", _row["state"] == "old",
       _row["state"])
    _ok, _rows = wc.skills_apply()
    ok("  ⟵ تُرقّى بلا --force",
       "سطرٌ جديدٌ في المصدر" in open(os.path.join(_d, _n, "SKILL.md"),
                                      encoding="utf-8").read(), _rows)
    open(os.path.join(_d, _n, "SKILL.md"), "w", encoding="utf-8").write(
        _prev + "\nقاعدتي أنا.\n")
    _row = [r for r in wc.skills_state()["skills"] if r["name"] == _n][0]
    ok("نسخةٌ سابقة + سطرٌ منك ⟵ edited", _row["state"] == "edited")
    wc.skills_apply()
    ok("  ⟵ لا تُدهَس بلا --force", "قاعدتي أنا" in open(
        os.path.join(_d, _n, "SKILL.md"), encoding="utf-8").read())
finally:
    wc.skills_dir, wc._skill_body = _real_sd, _real_body

print("\n— الحالةُ الحيّة —")
st = wc.skills_state()
ok("skills_state لا ترفع استثناءً", isinstance(st, dict))
ok("وتعرفها كلَّها", len(st.get("skills") or []) == len(WANT))
_old = os.environ.get("WEAVER_SKILLS")
os.environ["WEAVER_SKILLS"] = "off"
ok("WEAVER_SKILLS=off تُطفئ التلقائيّ", wc.skills_on() is False)
if _old is None:
    os.environ.pop("WEAVER_SKILLS", None)
else:
    os.environ["WEAVER_SKILLS"] = _old
ok("وبلا البيئة: مُشتغل", wc.skills_on() is True)

print("\n— القاموسُ: أيعمل بأداةِ exec الحقيقيّة؟ —")
# «يعمل عندي» لا تكفي: المهارةُ تُملي أمراً والنموذجُ ينفّذه بـ`exec`، وبين
# الاثنين أسئلةٌ لا تُجاب بالظنّ — أمسموحٌ مسارٌ خارج مساحة العمل؟ أيوجد
# python3 في بيئة المحرّك؟ فيُنفَّذ الأمرُ نفسُه ويُقرأ جوابُه.
ok("probe_exec.mjs موجود", os.path.isfile(wc.PROBE_EXEC))
ok("ويبني الأداةَ من المحرّك لا يحاكيها",
   "createOpenClawCodingTools" in open(wc.PROBE_EXEC, encoding="utf-8").read())
ok("skills_test موجودة", callable(getattr(wc, "skills_test", None)))
_t = wc.skills_test()
if _t.get("error"):
    print("    ⓘ يُتخطّى القياس: " + str(_t["error"])[:90])
else:
    ok("أداةُ exec متاحةٌ للنموذج", _t.get("found"))
    ok("والأمرُ خرج بـ0", _t.get("exitCode") == 0, _t.get("exitCode"))
    ok("ومسارٌ خارج مساحة العمل مسموح", _t.get("ok"), _t.get("text", "")[:80])
    ok("والاستشهادُ سليمٌ بعد التنظيف", _t.get("intact") is True)
    ok("والعباراتُ الموسومةُ بُدّلت فعلاً", _t.get("changed"),
       _t.get("text", "")[:120])

print("\n— القياسُ الحاسم: أرآها المحرّك؟ (بأمرِه skills --json) —")
seen = wc.skills_seen()
if seen:
    for r in seen:
        ok(f"{r['name']}: يراها النموذج",
           r["eligible"] and r["modelVisible"], r)
    ok("والمصدرُ مساحةُ العمل (الأولويّةُ الأولى)",
       all("workspace" in (r["source"] or "") for r in seen),
       [r["source"] for r in seen])
    # ما رُكِّب يراه النموذجُ كلَّه. والجديدةُ تُركَّب بـ`--skills apply`.
    _inst = [r["name"] for r in wc.skills_state()["skills"]
             if r["state"] != "missing"]
    ok("وكلُّ مُركَّبةٍ يراها", len(seen) >= len(_inst), (len(seen), _inst))
else:
    print("    ⓘ لا محرّكَ صالحٌ هنا أو غيرُ مُركَّبة — يُتخطّى القياس")

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
