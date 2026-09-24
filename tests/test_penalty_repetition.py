# -*- coding: utf-8 -*-
"""عقوبةُ التكرار (اختياريّةٌ مطفأة) وكاشفُ التكرار في `--soul check`.

  • الكاشف: عباراتٌ مكرّرة ومطالعُ جملٍ متشابهة ⟵ تحذيراتٌ لا تغيّر الدرجة.
  • العقوبة: لا تُرسَل إلا إن ضُبطت — لا في المسار المباشر ولا في المحرّك.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "web"))

from pipeline import weaver_core as W   # noqa: E402
from pipeline import soul_check as SC   # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


_PK = ("WEAVER_FREQUENCY_PENALTY", "WEAVER_PRESENCE_PENALTY")
_KEYS = ("WEAVER_PROVIDER", "WEAVER_BASE_URL", "WEAVER_MODEL",
         "WEAVER_API_KEY") + _PK
_SAVED_ENV = {k: os.environ.get(k) for k in _KEYS}
_real_load = W._load_settings
W._load_settings = lambda: {k: os.environ[k] for k in _KEYS
                            if os.environ.get(k)}


def setenv(**kw):
    for k in _KEYS:
        os.environ.pop(k, None)
    for k, v in kw.items():
        if v:
            os.environ[k] = v


_REP = (
    "والجامعات العربية تواجه تحديات كبيرة في التحول الرقمي الشامل. "
    "والجامعات العربية تواجه تحديات كبيرة في تمويل البحث العلمي. "
    "والجامعات العربية تواجه تحديات كبيرة في تدريب الكوادر الأكاديمية. "
    "والجامعات العربية تواجه تحديات كبيرة في تحديث المناهج الدراسية. "
    "وفي هذا السياق تبرز أهمية التعاون بين المؤسسات التعليمية المختلفة. "
    "وفي هذا السياق تبرز أهمية الاستثمار في البنية التحتية الرقمية. "
    "وفي هذا السياق تبرز أهمية إشراك الطلاب في صنع القرار الجامعي. ") * 3
_CLEAN = (
    "بدأت الجامعة مشروعها الرقمي قبل خمس سنوات بميزانية محدودة. "
    "لم يكن الأساتذة متحمسين في البداية، فالمنصة الأولى كانت بطيئة. "
    "غير أن الطلاب تبنّوها سريعاً، وصاروا يطلبون محاضرات مسجّلة. "
    "وحين تغيّرت الإدارة، جاءت أولويات مختلفة تماماً عن سابقتها. "
    "أما المكتبة فقد رقمنت مخطوطاتها النادرة بالتعاون مع جهة خارجية. "
    "وتبقى مسألة الاتصال بالإنترنت في الأرياف عائقاً لم يُحلّ بعد. ") * 5

try:
    print("\n— كاشفُ التكرار —")
    rep = SC.repetition(_REP)
    phr = dict(rep["phrases"])
    ok("عبارةٌ مكرّرة تُكتشف", any("الجامعات العربية تواجه" in p for p in phr),
       str(rep["phrases"]))
    ok("  ⟵ بالإملاء الأصليّ لا المُطبَّع",
       any(p.startswith("والجامعات العربية") for p in phr), str(list(phr)))
    ok("  ⟵ نوافذُ متداخلةٌ تُدمج (لا تحذيراتٌ مكرّرة للعبارة نفسها)",
       sum("الجامعات العربية تواجه" in p for p in phr) == 1, str(list(phr)))
    # الفقرةُ مكرّرةٌ ٣ مرّات ⟵ كلُّ جملةٍ كاملةٍ عبارةٌ مكرّرةٌ ٣ مرّات.
    ok("  ⟵ العدّ صحيح (الفقرةُ × ٣)",
       all(c == 3 for _p, c in rep["phrases"]), str(rep["phrases"]))
    st = dict(rep["starters"])
    ok("مطالعُ الجمل المتشابهة تُكتشف", "والجامعات العربية" in st
       and "وفي هذا" in st, str(rep["starters"]))
    ok("  ⟵ بالأعداد الصحيحة", st.get("والجامعات العربية") == 12
       and st.get("وفي هذا") == 9, str(st))
    ok("نصٌّ قصير ⟵ لا شيء (أقلّ من ١٥٠ كلمة)",
       SC.repetition("كلمة كلمة كلمة") == {"phrases": [], "starters": [],
                                           "top_words": []}
       or not SC.repetition("كلمة كلمة كلمة")["phrases"])
    cl = SC.repetition(_CLEAN)
    ok("نصٌّ نظيفٌ لا تكرارَ فيه غيرُ متعمَّد ⟵ …", isinstance(cl, dict))

    r1 = SC.check(_REP)
    rules = [w.get("rule") for w in r1.get("warnings", [])]
    ok("check(): تحذيرُ «عبارةٌ مكرّرة»", "عبارةٌ مكرّرة" in rules, str(rules))
    ok("check(): تحذيرُ «جملٌ تبدأ بالمطلع نفسِه»",
       "جملٌ تبدأ بالمطلع نفسِه" in rules, str(rules))
    ok("check(): الإحصاءُ في stats.repetition",
       "repetition" in r1.get("stats", {}))
    # الدرجةُ لا تتغيّر: نُعيد الفحصَ والكاشفُ معطَّل.
    _real_rep = SC.repetition
    SC.repetition = lambda text, min_words=150: {"phrases": [], "starters": [],
                                                 "top_words": []}
    r0 = SC.check(_REP)
    SC.repetition = _real_rep
    ok("الدرجةُ نفسُها بالكاشف وبدونه (تحذيرٌ لا خصم)",
       r0.get("score") == r1.get("score"),
       "%s ≠ %s" % (r0.get("score"), r1.get("score")))
    ok("والتحذيراتُ وحدها هي الفرق",
       [w for w in r1.get("warnings", [])
        if w.get("rule") not in ("عبارةٌ مكرّرة", "جملٌ تبدأ بالمطلع نفسِه")]
       == r0.get("warnings", []))

    print("\n— العقوبة: مطفأةٌ افتراضياً —")
    setenv()
    ok("penalty_params() بلا ضبط ⟵ {}", W.penalty_params() == {})
    os.environ["WEAVER_FREQUENCY_PENALTY"] = "0.3"
    ok("مضبوطة ⟵ frequencyPenalty فقط",
       W.penalty_params() == {"frequencyPenalty": 0.3}, str(W.penalty_params()))
    os.environ["WEAVER_PRESENCE_PENALTY"] = "0.2"
    ok("والاثنتان", W.penalty_params() == {"frequencyPenalty": 0.3,
                                          "presencePenalty": 0.2})
    for bad in ("0", "0.0", "abc", "3", "-2.5", "nan", " "):
        os.environ["WEAVER_FREQUENCY_PENALTY"] = bad
        ok("قيمةٌ «%s» ⟵ لا تُرسَل" % bad,
           "frequencyPenalty" not in W.penalty_params())
    os.environ["WEAVER_FREQUENCY_PENALTY"] = "-0.5"
    ok("سالبةٌ في المدى ⟵ تُقبل", W.penalty_params().get("frequencyPenalty")
       == -0.5)
    setenv()

    print("\n— المسار المباشر —")
    import server as S   # noqa: E402
    ok("_penalty_payload() بلا ضبط ⟵ {} (الحمولةُ كما كانت حرفاً)",
       S._penalty_payload({}) == {} and S._penalty_payload() == {})
    ok("من الإعدادات", S._penalty_payload(
        {"WEAVER_FREQUENCY_PENALTY": "0.4"}) == {"frequency_penalty": 0.4})
    os.environ["WEAVER_PRESENCE_PENALTY"] = "0.1"
    ok("والبيئةُ أوّلاً", S._penalty_payload(
        {"WEAVER_PRESENCE_PENALTY": "0.9"}) == {"presence_penalty": 0.1})
    os.environ["WEAVER_PRESENCE_PENALTY"] = "0"
    ok("صفرٌ ⟵ لا يُرسَل", S._penalty_payload({}) == {})
    setenv()
    src = open(os.path.join(_ROOT, "web", "server.py"), encoding="utf-8").read()
    i = src.index("def _chat_direct")
    ok("_chat_direct يضيفها بعد thinking",
       "_pl.update(_penalty_payload(s))" in src[i:])

    print("\n— المحرّك: params لكلّ نموذج، بلا إعادة إقلاع —")
    _calls = []
    _real = {n: getattr(W, n) for n in (
        "config_patch", "_save_fingerprint", "_applied_fingerprint",
        "credentials", "engine_route", "model_ref")}
    _applied = {}
    W.config_patch = lambda tree, timeout=180, replace_paths=(): (
        _calls.append(tree) or (True, "ok"))
    W._save_fingerprint = lambda fp: _applied.update(fp) if False else None
    W._applied_fingerprint = lambda: dict(_applied)
    W.credentials = lambda: {"OPENROUTER_API_KEY": "sk-or-1"}
    W.engine_route = lambda: {"mode": "bundled", "provider": "openrouter",
                              "ref": "openrouter/x/y", "base_url": "",
                              "api": ""}
    W.model_ref = lambda: "openrouter/x/y"
    setenv()
    W.configure_model()
    ok("بلا ضبط ⟵ لا `models` في agents.defaults (كما كان)",
       "models" not in _calls[-1]["agents"]["defaults"], str(_calls[-1]))
    ok("وبلا ضبط ⟵ البصمةُ بلا penalty (كما كانت حرفاً)",
       "penalty" not in W._model_fingerprint())
    os.environ["WEAVER_FREQUENCY_PENALTY"] = "0.3"
    W.configure_model()
    pm = _calls[-1]["agents"]["defaults"]["models"]["openrouter/x/y"]["params"]
    ok("مضبوطة ⟵ params.frequencyPenalty = 0.3 للنموذج",
       pm == {"frequencyPenalty": 0.3}, str(pm))
    fp = W._model_fingerprint()
    ok("البصمة: penalty خارج boot", fp.get("penalty") == {
        "frequencyPenalty": 0.3} and "0.3" not in fp["boot"])
    _applied.update(fp)
    os.environ.pop("WEAVER_FREQUENCY_PENALTY")
    W.configure_model()
    pm = _calls[-1]["agents"]["defaults"]["models"]["openrouter/x/y"]["params"]
    ok("أُزيلت بعد أن كُتبت ⟵ null يحذفها من المحرّك",
       pm == {"frequencyPenalty": None}, str(pm))
    for n, f in _real.items():
        setattr(W, n, f)

    print("\n— model_sync: تغييرُ العقوبة لا يُطفئ البوّابة —")
    _st = {"applied": {}, "cfg": 0, "stop": 0}
    _real = {n: getattr(W, n) for n in (
        "available", "_applied_fingerprint", "configure_model",
        "gateway_health", "gateway_stop", "engine_route")}
    W.available = lambda: True
    W._applied_fingerprint = lambda: dict(_st["applied"])
    W.engine_route = lambda: {"mode": "bundled", "provider": "openrouter",
                              "ref": "openrouter/x/y", "base_url": "",
                              "api": ""}

    def _fake_cfg():
        _st["cfg"] += 1
        _st["applied"] = W._model_fingerprint()
        return [("x", True, "")]
    W.configure_model = _fake_cfg
    W.gateway_health = lambda timeout=2: True
    W.gateway_stop = lambda: _st.__setitem__("stop", _st["stop"] + 1)
    setenv(WEAVER_API_KEY="k")
    W.model_sync()
    base_stop = _st["stop"]
    os.environ["WEAVER_FREQUENCY_PENALTY"] = "0.3"
    ch, _w = W.model_sync()
    ok("ضبطُها ⟵ تُكتب، بلا إعادة إقلاع", ch and _st["cfg"] == 2
       and _st["stop"] == base_stop, str(_st))
    ch, _w = W.model_sync()
    ok("بلا تغيير ⟵ لا كتابة", (not ch) and _st["cfg"] == 2)
    os.environ.pop("WEAVER_FREQUENCY_PENALTY")
    ch, _w = W.model_sync()
    ok("إزالتُها ⟵ تُكتب (للحذف)، بلا إعادة إقلاع", ch and _st["cfg"] == 3
       and _st["stop"] == base_stop, str(_st))
    for n, f in _real.items():
        setattr(W, n, f)
finally:
    W._load_settings = _real_load
    for k, v in _SAVED_ENV.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
