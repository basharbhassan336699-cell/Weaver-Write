# -*- coding: utf-8 -*-
"""دستورُ الكتابة — SOUL.md.

الفكرة: ما يمنع البصمةَ قبل أن تُولَد يُوضَع في ملفٍّ يُحقَن في كلِّ نوبة؛
وما يصلحها بعد ولادتها يبقى مهارةً تُستدعى. وهذا يفحص الأوّل.

وموضعُه مقيسٌ لا مظنون — `probe_bootstrap.mjs` يبني سياقَ التمهيد بدوالّ
المحرّك نفسِها ويقول أيُّ ملفٍّ دخل وبكم حرفاً:

    workspace-YW5Pl2cf.mjs:743  loadWorkspaceBootstrapFiles(dir)
    bootstrap-DYYMCrXY.mjs:236  buildBootstrapContextFiles(files, opts)

وأخطرُ ما في هذا التغيير أن يُدهَس ملفٌّ حرّره المستخدم. فأكثرُ الفحوص هنا
عن ذلك: نسخةٌ احتياطيّةٌ قبل أيِّ كتابة، ورفضُ الدهسِ بلا --force.
"""
import os
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


SRC = wc.SOUL_SRC
TXT = open(SRC, encoding="utf-8").read() if os.path.isfile(SRC) else ""
# النصُّ ملفوفٌ على أسطر، وعبارةٌ قد تنقسم بينها. فيُسطَّح للفحص: كسرُ فحصٍ
# لأنّ صياغةً التفّت على سطرين إنذارٌ كاذب، لا عطبٌ في الدستور.
FLAT = " ".join(TXT.split())

print("\n— الملفّ —")
ok("الدستورُ موجود", bool(TXT.strip()), SRC)
ok("حجمُه تحت الحدّ (٣٥٠٠ حرف)", len(TXT) <= 3500, len(TXT))
ok("وليس فارغاً من المضمون", len(TXT) > 1500, len(TXT))

print("\n— التغطية: مدموجةٌ من SYS-01 + HUMAN-04 + PIPE-02 —")
for w in ("delve", "tapestry", "groundbreaking", "robust", "pivotal",
          "leverage", "underscore", "comprehensive", "moreover",
          "in conclusion"):
    ok(f"إنجليزيّ: {w}", w in TXT)
for w in ("يُعدّ", "منظومة", "ركائز", "في إطار", "علاوة على ذلك",
          "وخلاصة القول", "تجدر الإشارة", "يستوجب", "يُعزّز"):
    ok(f"عربيّ: {w}", w in TXT)

print("\n— ما صُحّح بعد التجربة الأولى على الجهاز —")
# الاختبارُ الثالث («اكتب خاتمة») أخرج نوع A/B في DETECT-04:
#   «يتضح من خلال هذا البحث…» ثمّ «في الختام…» ثمّ خاتمةُ تحشيد.
# وسببُه ثغرةٌ في الدستور: مُنعت "in conclusion" ونُسيت مقابلاتُها
# العربيّة. وهذه الفحوصُ تمنع عودةَ الثغرة.
for w in ("في الختام", "وختاماً", "وفي الأخير", "يتضح من خلال",
          "نخلص إلى", "مما سبق يتبيّن"):
    ok(f"افتتاحُ تلخيصٍ ممنوع: {w}", w in TXT)
# و«قلّل» لم تعمل: استعمل «يستدعي» وهي في قائمة التقليل. فنُقلت للمنع.
ok("ونُقلت من «قلّل» إلى «امنع»", "ممنوعةٌ لا مُقلَّلة" in TXT)
for w in ("يستدعي", "يُكرّس", "يُمكّن", "تمكين"):
    ok(f"  ⟵ {w}", w in TXT)
# الشرطةُ الطويلة — دورتان:
#   الأولى: لا قاعدةَ إطلاقاً ⟶ استُعملت بكثرة
#   الثانية: قاعدةٌ في قسم «اللغة» اللّيّن ⟶ استُعملت مرّتين رغمها
# فنُقلت إلى المنع المطلق، لكن **مُضيَّقة**: البصمةُ الحقيقيّةُ هي الملتصقة
# «كلمة—كلمة»، أمّا «كلمة — كلمة» بمسافتين فاستطرادٌ بشريٌّ جيّد — وقد أخرجه
# النموذجُ نفسُه في التجربة («الجواب — جزئياً على الأقل — أنّ…»). منعُه مطلقاً
# يخسر أداةً تنفع، ويكسر الجملةَ إن مرّت على text_cleaner لاحقاً.
_ban = FLAT.split("## ٣)")[0].split("## ٢)")[-1] if "## ٢)" in FLAT else ""
ok("الملتصقةُ في المنع المطلق لا في القسم اللّيّن", "كلمة—كلمة" in _ban)
ok("  ⟵ وبديلُها القصيرةُ كما يفعل text_cleaner", "شرطةً قصيرة (-)" in FLAT)
ok("  ⟵ والاستطرادُ بمسافتين مسموحٌ بحدّ",
   "بمسافتين" in FLAT and "مرّةٌ واحدةٌ في القسم" in FLAT)
ok("ولم تبقَ نسخةٌ يتيمةٌ في قسم اللغة",
   FLAT.count("شرطةً قصيرة (-)") == 1, FLAT.count("شرطةً قصيرة (-)"))
# والخاتمةُ: كُتبت «لا تُلخّص» والمستخدمُ يطلب خاتمةً، والخاتمةُ تُلخّص.
ok("وقاعدةُ الخاتمة تُفرّق: لخّص ولا تُحشّد",
   "التلخيصُ وظيفتُها" in TXT and "تحشيد" in TXT)
ok("  ⟵ وفي غير الخاتمة لا تُلخّص", "لا تُلخّص ما قلتَه" in TXT)

print("\n— القواعدُ التي تمنع التكرار —")
ok("لا ثلاثُ جملٍ متقاربةُ الطول", "متقاربةُ الطول" in TXT)
ok("لا فقرتان بنفس المطلع", "بالتركيب نفسِه" in TXT)
ok("لا تبدأ كلَّ فقرةٍ بمضارع", "بفعلٍ مضارع" in TXT)

print("\n— والخاتمةُ والحماية —")
ok("لا خاتمةَ تلخيص+أهمّيّة", "بعبارةِ أهمّيّةٍ" in FLAT)
ok("الاستشهاداتُ لا تُمَسّ", "الاستشهاداتُ" in TXT)
ok("والآياتُ والأحاديث", "الأحاديثُ" in TXT)

print("\n— ما استُبعد عمداً (يُفسد المحادثة) —")
ok("لا «٢٠ سنة خبرة»", "20 years" not in TXT and "٢٠ سنة" not in TXT)
ok("لا «النصُّ فقط بلا تمهيد»", "لا تمهيد" not in TXT)
ok("لا كمّيّاتٍ للمستند (سؤالٌ لكلِّ قسم)",
   "لكلِّ قسمٍ رئيس" not in TXT and "per major section" not in TXT)
ok("ولا حقنَ صوتٍ شخصيٍّ (يتقاتل مع text_cleaner)",
   "لستُ مقتنعاً" not in TXT and "بصراحة، أجد" not in TXT)
ok("وفيه حدٌّ يحمي المحادثةَ القصيرة", "الحوارُ القصيرُ" in TXT)

print("\n— الدوالّ —")
for n in ("soul_path", "soul_on", "soul_state", "soul_apply",
          "soul_restore", "bootstrap_report"):
    ok(n + " موجودة", callable(getattr(wc, n, None)))
ok("probe_bootstrap.mjs موجود", os.path.isfile(wc.PROBE_BOOT))
ok("ويستعمل دوالَّ المحرّك لا تقليداً",
   "loadWorkspaceBootstrapFiles" in open(wc.PROBE_BOOT, encoding="utf-8").read())

print("\n— الأمان: لا يُدهَس شيء —")
_src = open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
            encoding="utf-8").read()
ok("نسخةٌ احتياطيّةٌ قبل الكتابة", "SOUL.md.openclaw" in _src)
ok("ولا تُدهَس بنسخةٍ أحدث", "not os.path.isfile(bak)" in _src)
ok("وتحريرُك يُرفَض بلا --force", '"custom"' in _src and "force" in _src)
ok("ويُميَّز دستورُنا المُضافُ إليه", "weaver-edited" in _src)
ok("والتركيبُ التلقائيُّ يُطفأ بالبيئة", "WEAVER_SOUL" in _src)
ok("وواجهةُ الطرفيّة: --soul و--bootstrap",
   '"--soul"' in _src and '"--bootstrap"' in _src)

print("\n— الحالةُ الحيّة —")
st = wc.soul_state()
ok("soul_state لا ترفع استثناءً", isinstance(st, dict))
ok("وتعرف المُركَّب", st.get("which") in
   ("weaver", "weaver-edited", "openclaw", "custom", "missing"),
   st.get("which"))
_old = os.environ.get("WEAVER_SOUL")
os.environ["WEAVER_SOUL"] = "off"
ok("WEAVER_SOUL=off تُطفئ التلقائيّ", wc.soul_on() is False)
if _old is None:
    os.environ.pop("WEAVER_SOUL", None)
else:
    os.environ["WEAVER_SOUL"] = _old
ok("وبلا البيئة: مُشتغل", wc.soul_on() is True)

_rep = wc.bootstrap_report()
if _rep.get("ok"):
    _names = [f.get("name") for f in _rep.get("files") or []]
    ok("SOUL.md يصل البرومبت", "SOUL.md" in _names, _names)
    _soul = next((f for f in _rep["files"] if f.get("name") == "SOUL.md"), {})
    ok("ويصل غيرَ مقصوص", not _soul.get("truncated"), _soul)
    ok("والمجموعُ دون ميزانيّة المحرّك (٦٠٬٠٠٠ حرف)",
       (_rep.get("totalChars") or 0) < 60000, _rep.get("totalChars"))
else:
    print("    ⓘ لا node صالحٌ هنا — تُخطّى قياساتُ البرومبت: "
          + str(_rep.get("error"))[:80])

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
