# -*- coding: utf-8 -*-
"""الفاحصُ الحتميُّ للدستور.

`--soul` يُثبت أنّ الدستورَ مُركَّب، و`--bootstrap` أنّه يصل البرومبت. وهذا
يُثبت الثالثةَ: **أيُتَّبع؟** — وهو ما كان يُقاس بعين المستخدم وحدَها.

والقرارُ الحاكمُ في التصميم: القائمةُ **تُستخرَج من الدستور**، لا تُنسَخ.
نسخةٌ ثانيةٌ تنحرف عن أصلها بعد تعديلين فتقيس دستوراً لم يعد موجوداً — وهو
أسوأُ من لا فحص، لأنّه يطمئنك كذباً. وأكثرُ الفحوص هنا تحرس هذا.

والنصّان المرجعيّان ليسا مُختلَقَين: هما ما أخرجه النموذجُ على جهاز
المستخدم يومَي ٢٢ و٢٣ سبتمبر — الفاشلُ قبل إصلاح الثغرات، والناجحُ بعده.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from pipeline import soul_check as sc   # noqa: E402
from pipeline import weaver_core as wc  # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


# ما أخرجه النموذجُ فعلاً — قبل إصلاح الثغرات
BAD = """خاتمة

يتضح من خلال هذا البحث أن الزواج المبكر يحمل آثاراً متشعبة تمتد عبر الجوانب الاجتماعية والصحية.

في الختام، لا يمكن النظر إليه كظاهرة هامشية، بل أزمة تتطلب استجابة متكاملة. إن الحد منها يستدعي تشريعات واضحة.

الزواج المبكر ليس قدراً، وصحة الفتيات ومستقبل الأوطان رهنٌ بهذا التغيير."""

# وما أخرجه بعدها
GOOD = """خاتمة

الزواج المبكر ليس مسألةً فرديةً تخص عائلة هنا أو هناك. بل ظاهرةٌ تمتد آثارها عبر ثلاثة أجيال.

الدراسات التي رصدت هذه الآثار انتهت إلى نتائج متقاربة: التسرب المدرسي، والعنف الأسري. لكن الأرقام وحدها لا تفسر لماذا يستمر النمط رغم تكاليفه.

ما لفت الانتباه حقاً هو فجوة السياسات. دولٌ عدةٌ سنّت قوانين، لكن التطبيق يظل رهناً بسلطة القاضي المحلي.

يبقى سؤال لم تُحسم أبعاده: هل يكفي رفع السن قانونياً لكسر الحلقة؟ الإجابة مختلفة من قرية إلى أخرى، وهذا الاختلاف نفسه ما يجعل أي حلٍّ وحدويٍّ محلَّ شك."""

print("\n— الاستخراجُ من الدستور، لا نسخةٌ ثانية —")
en, ar = sc.banned_terms()
ok("يستخرج إنجليزيّاً", len(en) >= 15, len(en))
ok("ويستخرج عربيّاً", len(ar) >= 12, len(ar))
ok("ولا يقرأ من قائمةٍ مكتوبةٍ في الفاحص",
   "delve" not in open(sc.__file__, encoding="utf-8").read())
# الدستورُ ملفوفٌ على أسطر، والعبارةُ قد تنقسم بينها — فيُسطَّح للمقارنة.
# (وهذا الفحصُ نفسُه كشف أنّ الفاحصَ كان يفوته ما يكتبه النموذجُ على سطرين،
#  فصار يُسطّح النصَّ المفحوصَ كذلك.)
_soul = " ".join(open(sc.SOUL_SRC, encoding="utf-8").read().split())
ok("وكلُّ مصطلحٍ مُستخرَجٍ موجودٌ في الدستور فعلاً",
   all(w in _soul for w in en + ar),
   [w for w in en + ar if w not in _soul][:4])
ok("والفاحصُ يُسطّح النصَّ فلا تفلته عبارةٌ على سطرين",
   any("it is important to note that" == v["term"] for v in
       sc.check("This is important to test.\nIt is important to\nnote that x.")
       ["violations"]))
for w in ("delve", "in conclusion", "tapestry"):
    ok(f"  ⟵ {w}", w in en)
for w in ("في الختام", "يتضح من خلال", "يستدعي", "نخلص إلى"):
    ok(f"  ⟵ {w}", w in ar)
# وأنماطُ التحشيد مكتوبةٌ في الفاحص — فتُفحَص مطابقتُها للدستور كي لا تنحرف
ok("وأنماطُ التحشيد مذكورةٌ في الدستور",
   sum(1 for r in sc._RALLY if r in _soul) >= 3,
   [r for r in sc._RALLY if r in _soul])

print("\n— على نصَّي المستخدم الحقيقيَّين —")
rb = sc.check(BAD)
ok("الفاشلُ يُرفَض", rb["ok"] is False)
_terms = [v["term"] for v in rb["violations"]]
for w in ("في الختام", "يتضح من خلال", "يستدعي", "استجابة متكاملة"):
    ok(f"  ⟵ يمسك «{w}»", w in _terms, _terms)
ok("  ⟵ ويمسك خاتمةَ التحشيد",
   any("تحشيد" in v["rule"] for v in rb["violations"]), rb["violations"])
rg = sc.check(GOOD)
ok("والناجحُ يُقبَل", rg["ok"] is True,
   [v["term"] for v in rg["violations"]])
ok("  ⟵ بدرجةٍ كاملة", rg["score"] == 100, rg["score"])

print("\n— الحالاتُ الحدّيّة —")
ok("الفارغُ يُرفَض ولا يرفع", sc.check("")["ok"] is False)
ok("وNone كذلك", sc.check(None)["ok"] is False)
ok("والشرطةُ الملتصقةُ تُمسَك",
   any("ملتصقة" in v["rule"] for v in sc.check("الجواب—هنا واضح.")["violations"]))
ok("والمنفصلةُ بمسافتين لا تُمسَك",
   not any("ملتصقة" in v["rule"]
           for v in sc.check("الجواب — هنا — واضح.")["violations"]))
_same = "التعليم مهم جداً.\n\nالتعليم يحتاج جهداً."
ok("وفقرتان بنفس المطلع تُمسَكان",
   any("نفس المطلع" in v["rule"] for v in sc.check(_same)["violations"]))
ok("ونصٌّ نظيفٌ يمرّ", sc.check("القمر بعيد. والسماء صافية اليوم.")["ok"])

print("\n— الوصلُ بالطرفيّة —")
_src = open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
            encoding="utf-8").read()
for n in ("soul_check", "soul_test", "skills_invoke_test"):
    ok(n + " موجودة", callable(getattr(wc, n, None)))
ok("--soul check بلا نداءِ نموذج", '"check"' in _src)
ok("--soul test بنوبةٍ واحدة", 'sub == "test"' in _src)
ok("--skills invoke يقرأ مسارَ النوبة", 'sub == "invoke"' in _src)
ok("ويعتمد على trajectory لا على الجواب",
   "trajectory(sk)" in _src)
_r = wc.soul_check(BAD)
ok("soul_check عبر weaver_core تعمل", _r.get("ok") is False)

print("\n— النموذجُ لم يُجب ⟵ «لم يُقَس»، لا حكمٌ كاذب —")
# قيس على جهاز المستخدم: رصيدُ المزوّد نفد، فقال `--soul test` «مخالف 0/100»
# وقال `--skills invoke` «راجع وصفَ المهارة» — حكمان على نصٍّ لم يُكتب.
import io as _io
import contextlib as _cl
_NOTE = ("المحرّك لم يُجب [رمز 1]: 402 This request requires more credits. "
         "billing — السطرُ الكامل بلا قصّ " + "x" * 300)
_real = {n: getattr(wc, n) for n in ("ask", "trajectory")}
wc.ask = lambda *a, **k: {"answer": "", "engine": "python", "note": _NOTE}
wc.trajectory = lambda *a, **k: []
try:
    _t = wc.soul_test()
    ok("soul_test: measured=False", _t.get("measured") is False, str(_t)[:120])
    ok("  ⟵ بلا درجة (لا 0/100)", _t.get("score") is None)
    ok("  ⟵ وبلا مخالفاتٍ مُختلَقة", _t.get("violations") == [])
    ok("  ⟵ والسببُ كاملاً", _t.get("reason") == _NOTE)
    _s = wc.skills_invoke_test()
    ok("skills_invoke_test: measured=False", _s.get("measured") is False)
    ok("  ⟵ والسببُ كاملاً", _s.get("note") == _NOTE)

    def _run_cli(*args):
        _old = sys.argv
        sys.argv = ["weaver_core"] + list(args)
        buf, code = _io.StringIO(), 0
        try:
            with _cl.redirect_stdout(buf):
                wc._cli()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        finally:
            sys.argv = _old
        return code, buf.getvalue()
    for _args, _bad in ((("--soul", "test"), "0/100"),
                        (("--skills", "invoke"), "راجع وصفَ المهارة")):
        _c, _o = _run_cli(*_args)
        _n = " ".join(_args)
        ok(f"{_n}: «لم يُقَس»", "لم يُقَس" in _o, _o[:160])
        ok(f"  ⟵ رمزُ خروج 3 (لا 0 ولا 1)", _c == 3, str(_c))
        ok(f"  ⟵ لا حكمَ كاذب «{_bad}»", _bad not in _o)
        ok(f"  ⟵ السببُ بلا قصّ", _NOTE in _o)
        ok(f"  ⟵ ويدلّ على الرصيد", "openrouter.ai/credits" in _o)

    # والنجاحُ لم يتغيّر
    wc.ask = lambda *a, **k: {"answer": "القمر بعيد. والسماء صافية اليوم.",
                              "engine": "weaver-core", "note": ""}
    _t = wc.soul_test()
    ok("جوابٌ حقيقيٌّ ⟵ measured=True ويُحكَم عليه كما كان",
       _t.get("measured") is True and _t.get("ok") is True
       and _t.get("score") == 100, str(_t)[:120])
    wc.trajectory = lambda *a, **k: [{"name": "exec",
                                      "request": "python3 rewrite_ar.py"}]
    _s = wc.skills_invoke_test()
    ok("مسارٌ فيه rewrite_ar ⟵ humanize-ar كما كان",
       _s.get("measured") is True and _s.get("called") == ["humanize-ar"])
finally:
    for _n, _f in _real.items():
        setattr(wc, _n, _f)

print("\n— الأمرُ المجهولُ يصرخ، لا يصمت —")
# المستخدمُ شغّل `--soul test` بنسخةٍ لا تعرفه، فسقط إلى `show` وعرض الحالةَ
# وخرج بـ0 — بدا ناجحاً. الصمتُ أخفى أنّه لم يسحب الالتزامَ الذي أضافه.
import subprocess as _sp
for _flag in ("--soul", "--skills"):
    _p = _sp.run([sys.executable, "-m", "pipeline.weaver_core", _flag, "xyz"],
                 capture_output=True, text=True, timeout=90, cwd=_ROOT)
    ok(f"{_flag} xyz ⟶ رمزُ خروجٍ غيرُ صفريّ", _p.returncode == 2,
       _p.returncode)
    ok(f"  ⟵ ويقول إنّه غيرُ معروف", "غيرُ معروف" in (_p.stderr or ""))
    ok(f"  ⟵ ويقترح السحب", "git pull" in (_p.stderr or ""))
_p = _sp.run([sys.executable, "-m", "pipeline.weaver_core", "--soul", "show"],
             capture_output=True, text=True, timeout=90, cwd=_ROOT)
ok("و«show» الصريحُ ما زال يعمل", _p.returncode == 0
   and "المُركَّب" in (_p.stdout or ""))

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
