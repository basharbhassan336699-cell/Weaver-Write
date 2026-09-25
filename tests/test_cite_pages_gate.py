# -*- coding: utf-8 -*-
"""cite-pages بطلبٍ فقط — واختبارُ الاتّجاهين (محاكاة، بلا نموذج).

`--skills invoke cite-pages`        طلبُ صفحة  ⟵ النجاحُ أن يفتحها
`--skills invoke cite-pages --not`  تلخيصٌ فقط ⟵ النجاحُ ألّا يفتحها
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from pipeline import weaver_core as W   # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


_real = {n: getattr(W, n) for n in ("ask", "trajectory", "_probe_setup")}
_seen = {}


def fake(answer, opened):
    def _ask(prompt, timeout=None, fallback=False, session=None):
        _seen["prompt"] = prompt
        return {"answer": answer}

    def _traj(sk):
        return ([{"name": "read", "request": W.skills_dir()
                  + "/cite-pages/SKILL.md"}] if opened else
                [{"name": "read", "request": "/x/uploads-test/pages.pdf"}])
    W.ask, W.trajectory = _ask, _traj


try:
    W._probe_setup = lambda target: ("/x/uploads-test", None)

    print("\n— طلبُ الصفحة ⟵ يجب أن يفتحها —")
    fake("وردت كلمة bravo في (ص. 2) من الملفّ.", opened=True)
    r = W.skills_invoke_test(target="cite-pages")
    ok("فتحها ⟵ نجح", r["ok"] and not r["negative"])
    ok("  ⟵ والطلبُ يسأل عن الصفحة", "برقم الصفحة" in _seen["prompt"]
       and "/x/uploads-test/pages.pdf" in _seen["prompt"])
    ok("  ⟵ والصفحةُ الصحيحةُ (٢) تُفحص", r["extra"].get(
        "الصفحةُ الصحيحة (٢)") is True, r["extra"])
    fake("وردت في ص. ٣", opened=True)
    r = W.skills_invoke_test(target="cite-pages")
    ok("  ⟵ وصفحةٌ خاطئة تُكشف (٣ لا ٢)",
       r["extra"].get("الصفحةُ الصحيحة (٢)") is False)
    fake("لا أعرف", opened=False)
    ok("لم يفتحها ⟵ فشل", not W.skills_invoke_test(target="cite-pages")["ok"])

    print("\n— تلخيصٌ بلا طلب صفحة ⟵ يجب ألّا يفتحها —")
    fake("البحثُ من ثلاث صفحات: alpha ثمّ bravo ثمّ charlie.", opened=False)
    r = W.skills_invoke_test(target="cite-pages", negative=True)
    ok("لم يفتحها ⟵ نجح", r["ok"] and r["negative"], r)
    ok("  ⟵ والطلبُ تلخيصٌ لا يذكر الصفحة", "لخّصه" in _seen["prompt"]
       and "صفحة" not in _seen["prompt"].replace("pages.pdf", ""))
    ok("  ⟵ ولا رقمَ صفحةٍ في الجواب", r["extra"].get(
        "رقمُ صفحةٍ في الجواب (لم يُطلب)") is False, r["extra"])
    fake("ملخّص (ص. 1) و(ص. 2)", opened=True)
    r = W.skills_invoke_test(target="cite-pages", negative=True)
    ok("فتحها ولم يُطلب منه ⟵ فشل (وصفُها واسع)", not r["ok"])
    ok("  ⟵ وأرقامُ صفحاتٍ لم تُطلب تُكشف",
       r["extra"].get("رقمُ صفحةٍ في الجواب (لم يُطلب)") is True)
    fake("", opened=False)
    W.trajectory = lambda sk: []
    r = W.skills_invoke_test(target="cite-pages", negative=True)
    ok("النموذجُ لم يعمل ⟵ لا يُحسب نجاحاً", not r["ok"]
       and r["measured"] is False)

    print("\n— المهاراتُ الأخرى كما كانت —")
    fake("x", opened=False)
    W.trajectory = lambda sk: [{"name": "exec", "request":
                                "python3 plagiarism.py --file a"}]
    r = W.skills_invoke_test(target="check-plagiarism")
    ok("check-plagiarism بلا negative ⟵ حكمُه كما كان", r["ok"]
       and not r["negative"])
finally:
    for n, f in _real.items():
        setattr(W, n, f)

src = open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
           encoding="utf-8").read()
ok("الواجهة: --skills invoke <مهارة> --not", '"--not" in argv' in src)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
