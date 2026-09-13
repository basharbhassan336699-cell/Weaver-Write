# -*- coding: utf-8 -*-
"""من يقرّر؟ المستخدم، ثم النموذج، ثم الكاشف اللفظيّ — بهذا الترتيب."""
import sys, os, inspect
sys.path.insert(0, "/home/user/Weaver-Write")
for k in list(os.environ):
    if k.startswith("WEAVER_"): os.environ.pop(k)
from pipeline.orchestrator import WeaverOrchestrator as W
ok = True

print("═"*66); print(" ١) الأسبقية الثلاثية"); print("═"*66)
cases = [
 ("المستخدم صرّح ⟶ يفوز على الاثنين", "MLA", "APA", "Chicago", "MLA", "user"),
 ("النموذج حكم ⟶ يفوز على الكاشف",     None,  "APA", "Chicago", "APA", "model"),
 ("لا نموذج ⟶ الكاشف احتياطاً",         None,  None,  "Chicago", "Chicago", "fallback"),
 ("لا أحد ⟶ لا قرار",                   None,  None,  None,      None, None),
]
for name, ex, mv, dv, want, by in cases:
    card = {}
    got = W._settle(card, "k", mv, dv, "اختبار", explicit=ex)
    d = (card.get("decisions") or {}).get("k") or {}
    g = (got == want) and (d.get("by") == by if by else not d)
    ok &= g
    print(f"   {name:34s} ⟶ {str(got):9s} ← {d.get('by','—'):9s} {'✅' if g else '❌'}")

print("\n" + "═"*66); print(" ٢) «لا» صارت قابلةً للقول"); print("═"*66)
for name, mv, dv, want in [
  ("النموذج يقول: لا جداول", False, True,  False),
  ("النموذج يقول: نعم",      True,  None,  True),
  ("النموذج صامت ⟶ الكاشف",  None,  True,  True),
  ("الجميع صامت",            None,  None,  None)]:
    card = {}
    got = W._settle(card, "want_table", mv, dv, "")
    ok &= (got is want)
    print(f"   {name:26s} ⟶ {str(got):5s} {'✅' if got is want else '❌'}")
print("   ⟵ False قرارٌ يُحترم، وNone صمتٌ يُتجاوز ✅")

print("\n" + "═"*66); print(" ٣) «لا جداول» تُنفَّذ لا تُسجَّل فقط"); print("═"*66)
src = inspect.getsource(W._layer_6) if hasattr(W, "_layer_6") else ""
a = inspect.getsource(W)
g = ('card.get("tables_forbidden")' in a and '_tbl_budget, _tbl_used = 0, 0' in a)
ok &= g
print(f"   ميزانية الجداول = صفر عند المنع: {'✅' if g else '❌'}")
g2 = ('tables_forbidden"] = True' in a)
ok &= g2
print(f"   الراية تُرفع حين يقول النموذج/المستخدم لا: {'✅' if g2 else '❌'}")

print("\n" + "═"*66); print(" ٤) مخطّط الفهم يسأل عن الثلاثة الناقصة"); print("═"*66)
u = inspect.getsource(sys.modules["pipeline.orchestrator"].understand_request)
for fld in ('"sourcing"', '"citation_style"', '"recency"',
            '"wants_table":true|false|null'):
    g3 = fld in u
    ok &= g3
    print(f"   {fld:34s} {'✅' if g3 else '❌'}")
ok &= ("max_tokens=1200" in u)
print(f"   الميزانية رُفعت للمخطّط الأوسع: {'✅' if 'max_tokens=1200' in u else '❌'}")

print("\n" + "═"*66); print(" ٥) الكاشف اللفظيّ لم يعد يدوس على النموذج"); print("═"*66)
# القرارات الأربعة انتقلت إلى موضعٍ واحد بعد دمج خطة النموذج — حيث تكون
# البطاقة قد امتلأت فعلاً. فالمقياس هو أن تمرّ بالأسبقية، لا أن تُكتب بهجاءٍ
# بعينه. وأهمّ من ذلك: أن الكاشف يقرأ الطلب الحاليّ وحده.
for nm, pat in [("sourcing_mode", '_settle(c, "sourcing_mode"'),
                ("action",        '_settle(c, "action"'),
                ("citation_style",'_settle(c, "citation_style"'),
                ("recency",       '_settle(c, "recency_intent"')]:
    g4 = pat in a
    ok &= g4
    print(f"   {nm:16s} يمرّ بالأسبقية: {'✅' if g4 else '❌'}")
# لا يقرأ كاشفٌ تاريخَ المحادثة فيَنسب إلى المستخدم ما قاله في طلبٍ سابق
_old = ['_sourcing_mode(task.description)',
        '_requested_citation_style(task.description)']
_leak = [x for x in _old if x in a]
ok &= not _leak
print(f"   لا كاشفَ يقرأ كلّ المحادثة: {'✅' if not _leak else '❌ ' + str(_leak)}")
# والثلاثية محفوظة في مُحلِّل الخطة: null ليست False
_u = inspect.getsource(sys.modules["pipeline.orchestrator"])
g5 = 'out["wants_table"] = _tri("wants_table")' in _u
ok &= g5
print(f"   null ≠ False في مُحلِّل الخطة: {'✅' if g5 else '❌'}")

print("\n" + "═"*66); print(" ٦) التمهيد يتبع المستند لا رقماً ثابتاً"); print("═"*66)
for tw, np_, lo, hi in [(0, 0, 120, 120), (3000, 3, 200, 200),
                        (20000, 8, 300, 300), (800, 4, 60, 60)]:
    c = {"target_words": tw, "mabhath_count": np_} if tw else {}
    v = W._bridge_policy(c, "")["max_words"]
    ok &= (lo <= v <= hi)
    print(f"   {tw or 'بلا طول':>8} كلمة · {np_ or '-'} مباحث ⟶ {v} كلمة  "
          f"{'✅' if lo <= v <= hi else '❌'}")
os.environ["WEAVER_BRIDGE_MAXWORDS"] = "90"
v = W._bridge_policy({"target_words": 20000, "mabhath_count": 8}, "")["max_words"]
os.environ.pop("WEAVER_BRIDGE_MAXWORDS")
ok &= (v == 90)
print(f"   المفتاح يعلو على الحساب: {v} {'✅' if v == 90 else '❌'}")

print("\n" + "═"*66); print(" ٧) الطبقتان ٢ و٧"); print("═"*66)
import subprocess
d = subprocess.run(["git","diff","-U0"],capture_output=True,text=True).stdout
bad = [l for l in d.splitlines() if l[:1] in "+-" and not l.startswith(("+++","---"))
       and any(w in l for w in ("enforce_strict_rag","conduct_guard"))]
ok &= not bad
print(f"   {'✅ لا مساس' if not bad else '❌'}")

print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
sys.exit(0 if ok else 1)
