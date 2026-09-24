# -*- coding: utf-8 -*-
"""حارسُ إعادة الصياغة (pipeline/integrity_check.py) — لمهارتي academic-humanize
وvoice-inject. يقارن الأصلَ بالصياغة: الاستشهاداتُ حرفاً وبترتيبها، والأرقامُ،
والاقتباساتُ، والطول. العدُّ وحده لا يكفي: استشهادٌ ينتقل يُبقي العدد."""
import os
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from pipeline.integrity_check import check, citations   # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


A = ("يُعدّ التعليم ركيزةً أساسية (الفهري، 2020، ص. 45)، وقد ارتفعت نسبة "
     "الالتحاق 30% (Smith et al., 2019, p. 12). ويقول الباحث: «التعليم حقٌّ "
     "للجميع» [3].")
print("\n— التقاطُ الاستشهادات —")
ok("ثلاثةُ أنماط: عربيّ، إنجليزيّ، مرقَّم", citations(A) == [
    "(الفهري، 2020، ص. 45)", "(Smith et al., 2019, p. 12)", "[3]"],
   citations(A))
ok("(الفهري، د.ت) بلا سنة", citations("قال (الفهري، د.ت).") == ["(الفهري، د.ت)"])
ok("قوسٌ عاديٌّ بلا سنة ليس استشهاداً", citations("المنصّات (وهي كثيرة) تتغيّر") == [])

print("\n— الأحكام —")
R = {
    "صياغةٌ جديدةٌ سليمة": ("التعليم أساسٌ في التنمية (الفهري، 2020، ص. 45)، "
        "وارتفعت نسبة الالتحاق 30% (Smith et al., 2019, p. 12). ويقول الباحث: "
        "«التعليم حقٌّ للجميع» [3].", True),
    "استشهادٌ انتقل إلى موضعٍ آخر": ("ارتفعت نسبة الالتحاق 30% (Smith et al., "
        "2019, p. 12). والتعليم أساسٌ (الفهري، 2020، ص. 45). ويقول الباحث: "
        "«التعليم حقٌّ للجميع» [3].", False),
    "رقمُ صفحةٍ تغيّر": ("التعليم أساسٌ (الفهري، 2020، ص. 46)، وارتفعت النسبة "
        "30% (Smith et al., 2019, p. 12). ويقول الباحث: «التعليم حقٌّ للجميع» "
        "[3].", False),
    "نسبةٌ تغيّرت": ("التعليم أساسٌ (الفهري، 2020، ص. 45)، وارتفعت النسبة 35% "
        "(Smith et al., 2019, p. 12). ويقول الباحث: «التعليم حقٌّ للجميع» [3].",
        False),
    "اقتباسٌ تغيّر": ("التعليم أساسٌ (الفهري، 2020، ص. 45)، وارتفعت النسبة 30% "
        "(Smith et al., 2019, p. 12). ويقول الباحث: «التعليم حقٌّ لكلّ الناس» "
        "[3].", False),
    "استشهادٌ حُذف": ("التعليم أساسٌ في التنمية، وارتفعت نسبة الالتحاق 30% "
        "(Smith et al., 2019, p. 12). ويقول الباحث: «التعليم حقٌّ للجميع» [3].",
        False),
    "استشهادٌ مُختلَقٌ أُضيف": ("التعليم أساسٌ (الفهري، 2020، ص. 45) (عمر، 2021)، "
        "وارتفعت النسبة 30% (Smith et al., 2019, p. 12). ويقول الباحث: «التعليم "
        "حقٌّ للجميع» [3].", False),
    "أرقامٌ هنديّة = عربيّة": ("التعليم أساسٌ (الفهري، 2020، ص. 45)، وارتفعت النسبة "
        "٣٠٪ (Smith et al., 2019, p. 12). ويقول الباحث: «التعليم حقٌّ للجميع» [3].",
        True),
}
for name, (txt, want) in R.items():
    r = check(A, txt)
    ok("%s ⟵ intact=%s" % (name, want), r["intact"] is want, r["problems"])
_long = " ".join(["كلمة"] * 60)
ok("قصُر بأكثر من الثلث ⟵ حذفٌ لا صياغة",
   check(_long, " ".join(["كلمة"] * 30))["intact"] is False)
ok("مدخلٌ فارغ لا يرفع استثناءً", check("", "")["intact"] is True)

print("\n— الطرفيّة —")
_d = tempfile.mkdtemp()
_a, _b = os.path.join(_d, "a.txt"), os.path.join(_d, "b.txt")
open(_a, "w", encoding="utf-8").write(A)
open(_b, "w", encoding="utf-8").write(R["صياغةٌ جديدةٌ سليمة"][0])
_s = os.path.join(_ROOT, "pipeline", "integrity_check.py")
p = subprocess.run([sys.executable, _s, "--original", _a, "--rewritten", _b,
                    "--json"], capture_output=True, text=True, timeout=60)
ok("سليم ⟵ رمز 0 وJSON", p.returncode == 0 and '"intact": true' in p.stdout,
   p.stdout[-120:])
open(_b, "w", encoding="utf-8").write(R["رقمُ صفحةٍ تغيّر"][0])
p = subprocess.run([sys.executable, _s, "--original", _a, "--rewritten", _b],
                   capture_output=True, text=True, timeout=60)
ok("تغيّر ⟵ رمز 1 والسببُ مكتوب", p.returncode == 1 and "استشهادٌ" in p.stdout)
ok("ويعمل بمساره المطلق من أيّ مجلّد", subprocess.run(
    [sys.executable, _s, "--original", _a, "--rewritten", _a], cwd=_d,
    capture_output=True, text=True, timeout=60).returncode == 0)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
