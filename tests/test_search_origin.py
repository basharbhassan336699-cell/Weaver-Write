# -*- coding: utf-8 -*-
"""مزوّدُ البحث: اختيارُ المستخدم يُحترَم، واختيارُ النظام له بدائل.

مبدأُ أوبن كلاو، مقروءٌ من كوده (dist/runtime-CFtRzJUE.mjs، runWebSearch):
    const allowFallback = !hasExplicitWebSearchSelection(...)
مُعيَّنٌ صراحةً ⟵ وحدَه بلا بديل؛ تلقائيٌّ ⟵ ينتقل إلى التالي عند الفشل.

العطبُ المقيس على هاتف المستخدم:
    المختار: duckduckgo · ✗ «DuckDuckGo returned a bot-detection challenge»
حلقتُنا كتبته بـconfig set فصار «صريحاً»، ولم يُبدَّل أبداً.
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from pipeline import weaver_core as W   # noqa: E402
# هذا الفحصُ يحاكي المحرّكَ باستبدال run/config_patch؛ فلا يُقرأ ملفُّ
# الإعداد الحقيقيُّ على الجهاز (القراءةُ السريعة — tests/test_cold_start.py).
W.CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__no_config__.json")

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


TMP = tempfile.mkdtemp()
_real = {n: getattr(W, n) for n in ("run", "probe_search", "WEB_SEARCH_AUTO",
                                    "WEB_SEARCH_STATUS")}
W.WEB_SEARCH_AUTO = os.path.join(TMP, "auto.json")
W.WEB_SEARCH_STATUS = os.path.join(TMP, "status.json")
CFG = {"provider": ""}
WORKS = set()           # المزوّدون الذين يعمل بحثُهم الآن
SETS = []


def _run(args, timeout=180, input_text=None, cwd=None):
    a = list(args)
    if a[:3] == ["config", "get", "tools.web.search.provider"]:
        return 0, json.dumps(CFG["provider"]), ""
    if a[:3] == ["config", "set", "tools.web.search.provider"]:
        CFG["provider"] = a[3]
        SETS.append(a[3])
        return 0, "", ""
    return 0, "", ""


def _probe(q="x"):
    p = CFG["provider"]
    good = p in WORKS
    return {"providers": ["duckduckgo", "parallel-free"], "configured": [p],
            "chosen": p, "usable": bool(p), "ok": good,
            "count": 3 if good else 0, "first": "",
            "error": "" if good else
            ("DuckDuckGo returned a bot-detection challenge."
             if p == "duckduckgo" else "failed: " + p)}


W.run, W.probe_search = _run, _probe


def reset(provider, works, record=None):
    CFG["provider"] = provider
    WORKS.clear()
    WORKS.update(works)
    SETS.clear()
    for f in (W.WEB_SEARCH_AUTO, W.WEB_SEARCH_STATUS):
        try:
            os.remove(f)
        except OSError:
            pass
    if record:
        W._json_write(W.WEB_SEARCH_AUTO, record)


try:
    print("\n— حالةُ الهاتف: duckduckgo محجوب، ولم يختره المستخدم —")
    reset("duckduckgo", {"parallel-free"})
    ok("بلا سجلّ: مزوّدٌ بلا مفتاح ⟵ النظامُ كتبه (المحرّكُ لا يختاره تلقائياً)",
       W.search_origin() == "system")
    r = W.ensure_web_search()
    ok("⟵ يُبدَّل إلى parallel-free الذي يعمل", r["ok"] and
       r["provider"] == "parallel-free" and CFG["provider"] == "parallel-free", r)
    ok("  ⟵ ويُذكر ما بُدِّل ولماذا", r["switched_from"] == "duckduckgo"
       and "bot-detection" in r["error"], r)
    ok("  ⟵ ويُسجَّل أنّ النظامَ اختاره (له بدائلُ لاحقاً)",
       W._json_read(W.WEB_SEARCH_AUTO) .get("by") == "system"
       and W.search_origin() == "system")
    ok("  ⟵ والحالةُ مكتوبةٌ للواجهة", W._json_read(W.WEB_SEARCH_STATUS)
       .get("switched_from") == "duckduckgo")

    print("\n— يعمل ⟵ لا يُلمَس شيء —")
    reset("parallel-free", {"parallel-free"},
          {"provider": "parallel-free", "by": "system"})
    r = W.ensure_web_search()
    ok("لا كتابة", r["ok"] and SETS == [], SETS)

    print("\n— تلقائيٌّ تعطّل لاحقاً ⟵ يعود البديلُ التالي —")
    reset("parallel-free", {"duckduckgo"},
          {"provider": "parallel-free", "by": "system"})
    r = W.ensure_web_search()
    ok("parallel-free فشل ⟵ duckduckgo", r["ok"]
       and CFG["provider"] == "duckduckgo", r)

    print("\n— اختيارُ المستخدم لا يُمَسّ (كالمحرّك) —")
    reset("brave", {"parallel-free"})
    ok("مزوّدٌ بمفتاح بلا سجلّ ⟵ اختيارُ المستخدم", W.search_origin() == "user")
    r = W.ensure_web_search()
    ok("يفشل ⟵ لا يُبدَّل، ويُقال السبب", not r["ok"] and SETS == []
       and r["origin"] == "user" and r["error"], r)
    reset("duckduckgo", {"parallel-free"},
          {"provider": "duckduckgo", "by": "user"})
    r = W.ensure_web_search()
    ok("اختار duckduckgo بنفسه (--web-search ddg) ⟵ لا يُبدَّل ولو فشل",
       not r["ok"] and SETS == [] and CFG["provider"] == "duckduckgo", r)
    reset("parallel-free", set(), {"provider": "duckduckgo", "by": "system"})
    ok("السجلُّ لغيره (غيّره بمعالج المحرّك) ⟵ اختيارُ المستخدم",
       W.search_origin() == "user")

    print("\n— لا بديلَ يعمل ⟵ يعود ما كان —")
    reset("duckduckgo", set())
    r = W.ensure_web_search()
    ok("لا يعمل شيء ⟵ ok=False، والمزوّدُ كما كان", not r["ok"]
       and CFG["provider"] == "duckduckgo", (r, CFG))

    print("\n— لا تعيينَ أصلاً ⟵ الأوّلُ الذي يعمل —")
    reset("", {"parallel-free"})
    r = W.ensure_web_search()
    ok("⟵ parallel-free", r["ok"] and CFG["provider"] == "parallel-free")

    print("\n— أوامرُ المستخدم تسجّله «user» —")
    reset("", set())
    W._set_search_provider("duckduckgo", auto=False)
    ok("--web-search ddg ⟵ by=user",
       W._json_read(W.WEB_SEARCH_AUTO) == {**W._json_read(W.WEB_SEARCH_AUTO),
                                           "provider": "duckduckgo",
                                           "by": "user"})
    src = open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
               encoding="utf-8").read()
    ok("--web-search choose ⟵ يسجّل ما اخترتَه by=user",
       '_mark_search_choice(chosen_provider(), "user")' in src)
    ok("والفحصُ قبل إقلاع البوّابة (تراه من أوّل نوبة)",
       src.index("ensure_web_search(say=_say)")
       < src.index('_args = [nb, ENTRY, "gateway", "run"]'))
finally:
    for n, f in _real.items():
        setattr(W, n, f)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
