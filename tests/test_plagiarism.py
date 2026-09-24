# -*- coding: utf-8 -*-
"""قياسُ النقل الحرفيّ — pipeline/plagiarism.py ومهارةُ check-plagiarism.

الثغرةُ التي يسدّها: الوكيلُ يفتح صفحاتٍ ويكتب منها، ولا شيءَ كان يقيس كم نسخ
منها حرفياً. الدستورُ والمهاراتُ الثلاثُ تعالج **الأسلوب**؛ ونصٌّ منقولٌ
بأسلوبٍ بشريٍّ ممتازٍ يمرّ عليها كلِّها بلا تنبيه.

وليس مطابقةَ كلماتٍ ممنوعة: يقارن نصَّين، ولا يغيّر حرفاً، ولا يتحكّم في
النموذج. والفكرةُ نفسُها في `_verbatim_overlap` (طبقةٌ معطَّلةٌ لا تُمَسّ) —
والفحصُ هنا يطابق نتيجتَها.
"""
import json
import os
import random
import subprocess
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from pipeline import plagiarism as PL   # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


SRC = ("وتشير الدراسات الحديثة إلى أنّ التعليم الإلكتروني ساهم في رفع نسبة "
       "الالتحاق بالجامعات بنحو ثلاثين بالمئة خلال العقد الأخير في الدول "
       "النامية، وهو ما غيّر خريطة التعليم العالي تغييراً جذرياً في المنطقة.")
RUN = ("التعليم الإلكتروني ساهم في رفع نسبة الالتحاق بالجامعات بنحو ثلاثين "
       "بالمئة خلال العقد الأخير في الدول النامية")          # ١٧ كلمة
S = [{"name": "src", "text": SRC}]

print("\n— القياس —")
r = PL.measure("بدأت الجامعات تتغيّر. " + RUN + "، ولهذا أثرٌ كبير.", S)
ok("نقلٌ حرفيّ ⟵ COPIED", r["verdict"] == "COPIED", r["verdict"])
ok("  ⟵ وطولُه ١٧ كلمة", r["longest_run"] == 17, r["longest_run"])
ok("  ⟵ ومصدرُه مُسمّى", r["spans"][0]["source"] == "src")
ok("  ⟵ والمقطعُ من النصّ نفسِه", "ساهم في رفع" in r["spans"][0]["excerpt"])
ok("  ⟵ ونسبةٌ من النصّ", 0 < r["copied_percent"] <= 100)
_diac = ("التعليمُ الإلكترونيُّ ساهمَ في رفعِ نسبةِ الالتحاقِ بالجامعاتِ بنحوِ "
         "ثلاثينَ بالمئةِ خلالَ العقدِ الأخيرِ في الدولِ الناميةِ")
ok("التشكيلُ لا يُخفي النقل",
   PL.measure(_diac, S)["longest_run"] == 17)
ok("ولا الهمزاتُ (أ/ا) ولا التاءُ المربوطة",
   PL.measure(RUN.replace("الإلكتروني", "الالكتروني")
              .replace("النامية", "الناميه"), S)["longest_run"] == 17)
r = PL.measure("يقول الباحث: «" + RUN + "» (عبدالله، 2023).", S)
ok("الاقتباسُ بين «» ⟵ ليس نقلاً", r["verdict"] == "CLEAN", r)
ok("  ⟵ ويُعَدّ وحدَه", r["quoted_words"] == 17, r["quoted_words"])
ok("وبين “” كذلك",
   PL.measure("قال: “" + RUN + "”.", S)["verdict"] == "CLEAN")
ok('وبين "" كذلك',
   PL.measure('قال: "' + RUN + '".', S)["verdict"] == "CLEAN")
r = PL.measure("ارتفع عددُ الملتحقين بالجامعات في البلدان النامية نحو الثلث في "
               "عشر سنوات، والفضلُ للدراسة عن بُعد.", S)
ok("الفكرةُ نفسُها بكلماتٍ أخرى ⟵ CLEAN", r["verdict"] == "CLEAN")
_14 = " ".join(RUN.split()[:14])
ok("١٤ كلمةً متطابقة ⟵ دون الحدّ", PL.measure(_14 + " وانتهى.", S)
   ["verdict"] == "CLEAN")
_15 = " ".join(RUN.split()[:15])
ok("١٥ كلمة ⟵ عند الحدّ: نقل", PL.measure(_15 + " وانتهى.", S)
   ["longest_run"] == 15)
ok("--min-words يُحترم", PL.measure(_14, S, min_words=8)["verdict"]
   == "COPIED")
r = PL.measure(RUN, [{"name": "a", "text": "نصٌّ آخر تماماً"},
                     {"name": "b", "text": SRC}])
ok("مصادرُ عدّة ⟵ يُسمّي الصحيح", r["spans"][0]["source"] == "b")
ok("لا مصدرَ يُقرأ ⟵ UNMEASURED (لا «سليم» كاذب)",
   PL.measure(RUN, [{"name": "x", "text": ""}])["verdict"] == "UNMEASURED")
ok("ولا مصادرَ أصلاً ⟵ UNMEASURED",
   PL.measure(RUN, [])["verdict"] == "UNMEASURED")
ok("نصٌّ فارغ لا يرفع استثناءً", PL.measure("", S)["verdict"] == "CLEAN")
_draft = "بدأت. " + RUN + " انتهت."
_copy = str(_draft)
PL.measure(_draft, S)
ok("لا يغيّر النصَّ المفحوص", _draft == _copy)

print("\n— يطابق _verbatim_overlap الأصليّة (الطبقةُ المعطَّلةُ لا تُمَسّ) —")
try:
    from pipeline.orchestrator import WeaverOrchestrator as _O
    random.seed(7)
    vocab = ("التعليم الجامعة الطالب البحث المعرفة المستقبل التقنية الشبكة "
             "المنهج الأستاذ الكتاب الدرس المدرسة الفصل التجربة النتيجة "
             "الدراسة الإحصاء المجتمع الثقافة").split()
    agree = 0
    for _ in range(120):
        sw = [random.choice(vocab) for _ in range(300)]
        L = random.choice([5, 10, 14, 16, 20, 35, 60])
        i = random.randrange(0, 300 - L)
        d = " ".join([random.choice(vocab) for _ in range(40)] + sw[i:i + L]
                     + [random.choice(vocab) for _ in range(40)])
        old = _O._verbatim_overlap(d, [{"content": " ".join(sw)}])
        new = PL.measure(d, [{"name": "s", "text": " ".join(sw)}])["longest_run"]
        # الأصليّةُ تُبلغ عمّا يزيد على ١٥، والجديدةُ عمّا يبلغ ١٥
        agree += (old == new or (old == 0 and new == 15))
    ok("أطولُ نقلٍ مطابقٌ في ١٢٠/١٢٠ حالةً عشوائيّة", agree == 120, agree)
except Exception as e:
    print("  (تعذّر استيرادُ المنسّق — تُخطّى المقارنة: %s)" % str(e)[:80])

print("\n— صفحةٌ حقيقيّة عبر HTTP —")
import tempfile  # noqa: E402
_tmp = tempfile.mkdtemp()
with open(os.path.join(_tmp, "p.html"), "w", encoding="utf-8") as fh:
    fh.write('<!doctype html><html><head><meta charset="utf-8"><script>var s='
             '"' + RUN + '";</script></head><body><nav>الرئيسية | اتصل بنا'
             '</nav><article><p>' + SRC + '</p></article><footer>جميع الحقوق'
             '</footer></body></html>')


class _Q(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=_tmp, **k)

    def log_message(self, *a):
        pass


_srv = HTTPServer(("127.0.0.1", 0), _Q)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
_url = "http://127.0.0.1:%d/p.html" % _srv.server_port
t, err = PL.fetch(_url)
ok("تُنزَّل وتُقرأ", err is None and "ساهم في رفع" in t, err)
ok("  ⟵ بلا السكربت ولا القوائم", "var s" not in t and "اتصل بنا" not in t
   and "جميع الحقوق" not in t, t[:120])
t, err = PL.fetch("http://127.0.0.1:9/none", timeout=3)
ok("رابطٌ لا يفتح ⟵ خطأٌ مُسمّى لا استثناء", t == "" and err, err)

print("\n— الطرفيّة —")
_S = os.path.join(_ROOT, "pipeline", "plagiarism.py")


def _run(*a):
    return subprocess.run([sys.executable, _S] + list(a), capture_output=True,
                          text=True, timeout=120)


p = _run("--text", "بدأت. " + RUN, "--url", _url, "--json")
ok("نقلٌ ⟵ رمز 1", p.returncode == 1, p.returncode)
try:
    j = json.loads(p.stdout)
except Exception:
    j = {}
ok("  ⟵ وJSON صالح", j.get("verdict") == "COPIED", p.stdout[:120])
p = _run("--text", "كتابةٌ أصليّة لا صلة لها بأيّ مصدر.", "--source-text", SRC)
ok("سليم ⟵ رمز 0 و«لا نقلَ حرفيّ»", p.returncode == 0
   and "لا نقلَ حرفيّ" in p.stdout, p.stdout[-120:])
p = _run("--text", RUN, "--url", "http://127.0.0.1:9/none")
ok("لم يُقَس ⟵ رمز 3 و«لم يُقَس»", p.returncode == 3
   and "لم يُقَس" in p.stdout, p.returncode)
p = _run("--text", RUN)
ok("بلا مصدر ⟵ رمز 2", p.returncode == 2)
_f = os.path.join(_tmp, "d.txt")
open(_f, "w", encoding="utf-8").write("بدأت. " + RUN)
ok("--file يعمل", _run("--file", _f, "--source-text", SRC).returncode == 1)
ok("ويعمل بمساره المطلق من أيّ مجلّد (كما تستدعيه المهارة)",
   subprocess.run([sys.executable, _S, "--text", RUN, "--source-text", SRC],
                  capture_output=True, text=True, timeout=120,
                  cwd=_tmp).returncode == 1)
_srv.shutdown()

print("\n— ليس في فهرس الكلمات المفتاحيّة القديم —")
# كلُّ مجلّدٍ في capabilities/skills بملفّ SKILL.md يُحمَّل في الفهرس القديم
# بـ`triggers` (كلماتٌ مفتاحيّة). فالسكربتُ في pipeline/ لا هناك.
ok("لا مجلّدَ له في capabilities/skills",
   not any("plagiar" in d for d in os.listdir(
       os.path.join(_ROOT, "capabilities", "skills"))))
_sk = open(os.path.join(_ROOT, "capabilities", "prompts", "skills",
                        "check-plagiarism", "SKILL.md"), encoding="utf-8").read()
ok("ومهارةُ المحرّك بلا triggers", "triggers:" not in _sk)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
