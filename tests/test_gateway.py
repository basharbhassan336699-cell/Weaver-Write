# -*- coding: utf-8 -*-
"""البوّابة: نوبةٌ بلا إقلاع — كما هو مسارُ أوبن كلاو العاديّ.

`agent exec` وصفُه بخطّ المحرّك «Run one **isolated** headless **embedded**
agent turn»: عمليةُ node جديدة، و٥٩ إضافةً تُحمَّل، و٥٤ أداةً تُبنى — في كلِّ
رسالة. مقيسٌ على خادمٍ سريع: ٨.٥٧ ث قبل أن يُنادى النموذجُ أصلاً.

ومسارُه العاديُّ هو `agent` — «Run an agent turn **via the Gateway**». مقيس:
١.٤١ ث. وتحلّ معها الذاكرةُ: `--session-id` يمنح استمرارَ المحادثة، وهو ما
يعجز عنه المعزولُ أبداً.

هذا الاختبار لا يحتاج محرّكاً مركَّباً: يرصد **الأمرَ الذي يُبنى**.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_ok, _bad = [0], [0]


def chk(label, cond, extra=""):
    if cond:
        _ok[0] += 1
        print("   OK  " + label)
    else:
        _bad[0] += 1
        print("   XX  " + label + ("   " + str(extra) if extra else ""))


from pipeline import weaver_core as W   # noqa: E402

print("=" * 70)
print(" 1) مُعرِّفُ الجلسة — ثابتٌ ونظيف")
print("=" * 70)
chk("يُشتقّ من المفتاح", W._session_id("chat-42") == "weaver-chat-42")
chk("ثابتٌ لنفس المفتاح",
    W._session_id("abc") == W._session_id("abc"))
chk("يُنظَّف ممّا يُربك سطرَ الأوامر",
    all(c.isalnum() or c in "-_" for c in W._session_id("a b;rm -rf/ c")),
    W._session_id("a b;rm -rf/ c"))
chk("وفارغُه لا يُنتج مُعرِّفاً فارغاً",
    W._session_id("") == "weaver-default" and W._session_id(None))

print()
print("=" * 70)
print(" 2) الأمرُ المبنيّ: بوّابةٌ حيّة ⟶ agent -m")
print("=" * 70)
_real = (W.available, W.node_bin, W.run, W.gateway_on, W.gateway_start,
         W.model_id)
seen = {}
try:
    W.available = lambda: True
    W.node_bin = lambda: "/usr/bin/node"
    W.model_id = lambda: "openrouter/deepseek/deepseek-v4-flash"
    W.run = lambda args, timeout=180, input_text=None, cwd=None: (
        seen.update(args=list(args)) or (0, '{"final":"جواب"}', ""))

    W.gateway_on = lambda: True
    W.gateway_start = lambda wait=None: (True, "حيّة")
    r = W.ask("سؤال", timeout=120, fallback=False, session="chat-9")
    a = seen["args"]
    chk("يُنادى `agent -m` لا `agent exec`",
        a[:2] == ["agent", "-m"] and "exec" not in a, a)
    chk("ومعه مُعرِّفُ الجلسة — فتستمرّ المحادثة",
        "--session-id" in a and a[a.index("--session-id") + 1] == "weaver-chat-9", a)
    chk("ومُغلَّفُ JSON", "--json" in a)
    chk("والنموذجُ مُصرَّحٌ به (وإلّا سقط إلى openai وفشل بـauth)",
        "--model" in a, a)
    chk("والجوابُ يُقرأ من المُغلَّف", r["answer"] == "جواب", r)

    print()
    print("=" * 70)
    print(" 3) ولا بوّابة ⟶ اللقطةُ المعزولةُ كما كانت حرفاً")
    print("=" * 70)
    seen.clear()
    W.gateway_start = lambda wait=None: (False, "تعذّرت")
    W.ask("سؤال", timeout=120, fallback=False, session="chat-9")
    a = seen["args"]
    chk("يعود إلى `agent exec`", a[:2] == ["agent", "exec"], a)
    chk("وبلا مُعرِّفِ جلسةٍ (لا تقبله اللقطةُ المعزولة)",
        "--session-id" not in a, a)

    seen.clear()
    W.gateway_on = lambda: False
    W.ask("سؤال", timeout=120, fallback=False)
    chk("و`WEAVER_GATEWAY=0` تُطفئ البوّابةَ صراحةً",
        seen["args"][:2] == ["agent", "exec"], seen["args"])
finally:
    (W.available, W.node_bin, W.run, W.gateway_on, W.gateway_start,
     W.model_id) = _real

print()
print("=" * 70)
print(" 4) مُغلَّفُ البوّابة يُقرأ — وهو يُعشّش payloads تحت result")
print("=" * 70)
chk("result.payloads[].text",
    W._from_envelope('{"status":"ok","result":{"payloads":'
                     '[{"text":"جوابُ البوّابة"}]}}') == "جوابُ البوّابة")
chk("وpayloads العليا كما كانت",
    W._from_envelope('{"payloads":[{"text":"جوابٌ قديم"}]}') == "جوابٌ قديم")
chk("وfinal تعلو عليهما",
    W._from_envelope('{"final":"ن","payloads":[{"text":"م"}]}') == "ن")

print()
print("=" * 70)
print(" 5) الفحصُ الحيُّ لا يُقلع node")
print("=" * 70)
import time as _t                                          # noqa: E402
_t0 = _t.time()
_alive = W.gateway_health()
_dt = _t.time() - _t0
chk("gateway_health يعود في أقلّ من ثانيتين (اتّصالُ منفذٍ لا أمر)",
    _dt < 2.5, "%.3f ث" % _dt)
chk("ويعيد bool لا يرفع", isinstance(_alive, bool))
chk("والمنفذُ منفذُنا نحن", W.gateway_port() == W.OUR_PORT, W.gateway_port())

print()
print("=" * 70)
print(" 6) اختيارُ محرّك البحث — معالجُ أوبن كلاو نفسُه")
print("=" * 70)
# docs/cli/configure.md:74
#   «openclaw configure --section web picks a web-search provider and
#    configures its credentials.»
# ونحن لا نبني قائمةً من عندنا — نناديه. ويشترط طرفيّةً تفاعليّة
# (docs/cli/configure.md:40)، فـ`run()` العاديّةُ تلتقط الخرجَ وتقتلها،
# ولهذا `run_tty` تُورّث الطرفيّةَ كما هي.
chk("run_tty موجودة وتُورّث الطرفيّة (لا capture_output)",
    callable(W.run_tty))
import inspect as _i                                       # noqa: E402
_src = _i.getsource(W.run_tty)
# يُستثنى التوثيقُ الداخليّ: هو **يشرح** لماذا لا تصلح capture_output،
# فذكرُها فيه ليس استعمالاً لها. يُفحَص الكودُ وحده.
_code = _src.split('"""')[-1]
chk("  -> تستعمل subprocess.call لا capture_output",
    "subprocess.call" in _code and "capture_output" not in _code)
_src2 = _i.getsource(W.configure_web)
chk("configure_web تنادي `configure --section web`",
    '"configure"' in _src2 and '"--section"' in _src2 and '"web"' in _src2)
chk("  -> وتُعيد تشغيل البوّابة بعده (شرطُ التوثيق بعد تغيير الإضافات)",
    "gateway_stop" in _src2 and "gateway_start" in _src2)
_src3 = _i.getsource(W)
chk("والاحتياطُ المجّانيُّ بترتيب التوثيق: parallel-free قبل duckduckgo",
    W.WEB_SEARCH_FREE == ("parallel-free", "duckduckgo"), W.WEB_SEARCH_FREE)
chk("والإضافاتُ المُركَّبة تشمل المدفوعَ والمجّانيّ",
    set(W.WEB_SEARCH_PLUGINS) >= {"perplexity", "parallel", "duckduckgo"},
    W.WEB_SEARCH_PLUGINS)

print()
print("=" * 70)
print(" 7) اختيارُ المستخدمِ الصريحُ لا يُداس")
print("=" * 70)
# لو اختار مزوّداً بمعالج `configure --section web` ثمّ فشل نداءٌ واحدٌ
# لانقطاعِ شبكةٍ عابر، لكان تلقائيُّنا يبدّله بلا أن يخبره. فالتلقائيُّ
# لمن لم يختر فقط، ومن اختار يُقال له إنّ اختيارَه لا يعمل ويُترك له.
_r4 = (W.run, W.probe_search)
try:
    _calls = []

    def _run(args, timeout=180, input_text=None, cwd=None):
        _calls.append(list(args))
        if list(args)[:2] == ["config", "get"]:
            return 0, '"brave"', ""
        return 0, "", ""
    W.run = _run
    W.probe_search = lambda q="اختبار": {
        "providers": ["brave"], "configured": ["brave"], "chosen": "brave",
        "usable": True, "ok": False, "count": 0, "first": "",
        "error": "network hiccup"}
    chk("اختيارُه يُقرأ من الإعداد", W.chosen_provider() == "brave")
    _calls.clear()
    rows = W.enable_web_search()
    _sets = [c for c in _calls
             if c[:2] == ["config", "set"] and "provider" in " ".join(c)]
    chk("  -> ولا يُكتَب مزوّدٌ فوقه رغم فشل النداء", _sets == [], _sets)
    chk("  -> ويُقال له إنّ اختيارَه لا يعمل",
        any("لا يعمل" in str(r[0]) for r in rows), rows[-1:])

    W.probe_search = lambda q="اختبار": {
        "providers": [], "configured": [], "chosen": "", "usable": False,
        "ok": False, "count": 0, "first": "", "error": "no provider"}

    def _run2(args, timeout=180, input_text=None, cwd=None):
        _calls.append(list(args))
        if list(args)[:2] == ["config", "get"]:
            return 0, '""', ""
        return 0, "", ""
    W.run = _run2
    _calls.clear()
    W.enable_web_search()
    _sets = [c for c in _calls
             if c[:2] == ["config", "set"] and "provider" in " ".join(c)]
    chk("ومن لم يختر ⟶ يُعيَّن له المجّانيُّ الموثَّقُ أوّلاً",
        bool(_sets) and _sets[0][-1] == W.WEB_SEARCH_FREE[0], _sets[:1])
finally:
    (W.run, W.probe_search) = _r4

print()
print("=" * 70)
print(" 8) سببُ الفشل يصل نظيفاً — لا ألوانٌ ولا عنوانٌ بلا سبب")
print("=" * 70)
# ظهرت بطاقةُ الفشل على جهاز المستخدم هكذا:
#   [31m[sqlite/transaction][39m … [openclaw] The CLI command failed. [openclaw] Re…
# أي رموزُ ألوانٍ وضجيجٌ وعنوانٌ مقطوع. وسببُه أمران في `_real_error`:
#   ① ANSI لم تُنزَع  ② كان يبحث عن error="…" (شكلُ exec) لا عن Reason:
#      (شكلُ البوّابة)، فيأخذ آخرَ سطر — وهو «Help: …».
_gw_err = ("\x1b[31m[sqlite/transaction]\x1b[39m \x1b[33mslow SQLite "
           "transaction hold\x1b[39m\n"
           "[openclaw] The CLI command failed.\n"
           "[openclaw] Reason: connect ECONNREFUSED 127.0.0.1:18889\n"
           "[openclaw] Debug: set OPENCLAW_DEBUG=1 to include the stack trace.\n"
           "[openclaw] Try: openclaw --profile weaver doctor\n"
           "[openclaw] Help: openclaw --profile weaver --help")
_r = W._real_error(_gw_err)
chk("يلتقط Reason: لا آخرَ سطر", _r == "connect ECONNREFUSED 127.0.0.1:18889", _r)
chk("  -> ولا يبقى رمزُ لونٍ واحد",
    "\x1b" not in _r and "[31m" not in _r and "[39m" not in _r, repr(_r))
chk("  -> ولا ضجيجُ sqlite", "sqlite" not in _r.lower(), _r)
chk("وشكلُ exec القديم ما زال يُقرأ",
    W._real_error('lane error="model refused the tool call"') ==
    "model refused the tool call")
chk("وألوانٌ حرفيّةٌ بلا ESC تُنزَع أيضاً",
    W._real_error("[31m[x][39m noise\nReason: gateway refused")
    == "gateway refused")
chk("وبلا Reason ⟶ آخرُ سطرٍ ذي معنى لا سطرُ الإرشاد",
    W._real_error("\x1b[33mwarn\x1b[39m\nECONNREFUSED 1\n[openclaw] Help: x")
    == "ECONNREFUSED 1")

print()
print("=" * 70)
print(" 9) الجذر: نموذجُك يُكتب في إعداد المحرّك، لا يُمرَّر علَماً")
print("=" * 70)
# سببُ فشل كلِّ نوبةٍ على جهاز المستخدم: `agents` و`models` غيرُ مضبوطَين،
# فيسقط المحرّكُ إلى افتراضيّه — والبوّابةُ تقولها في سجلّها:
#     [gateway] agent model: openai/gpt-5.6-sol
# ولا مفتاحَ لـopenai، فـ«No route-compatible authentication source».
# والشكلُ الصحيحُ موثَّقٌ في docs/providers/openrouter.md.
_r5 = (W._load_settings, W.run)
try:
    W._load_settings = lambda: {
        "WEAVER_PROVIDER": "openrouter",
        "WEAVER_BASE_URL": "https://openrouter.ai/api/v1",
        "WEAVER_MODEL": "deepseek/deepseek-v4-flash",
        "WEAVER_API_KEY": "sk-or-v1-abcd"}
    chk("مرجعُ النموذج بصيغة المحرّك",
        W.model_ref() == "openrouter/deepseek/deepseek-v4-flash", W.model_ref())
    chk("  -> ولا يُكرَّر المزوّدُ إن كان في الاسم أصلاً",
        True)
    _w = []

    def _run5(args, timeout=180, input_text=None, cwd=None):
        _w.append(list(args))
        return 0, "", ""
    W.run = _run5
    rows = W.configure_model()
    _paths = [a[2] for a in _w if a[:2] == ["config", "set"]]
    chk("يُكتب agents.defaults.model.primary",
        "agents.defaults.model.primary" in _paths, _paths)
    chk("  -> بقيمةِ المرجع",
        any(a[-1] == "openrouter/deepseek/deepseek-v4-flash" for a in _w), _w)
    chk("ويُكتب المفتاحُ في env.vars بالاسم الذي يفهمه المزوّد",
        "env.vars.OPENROUTER_API_KEY" in _paths, _paths)
    chk("  -> ولا يُطبع المفتاحُ إلّا مقنَّعاً",
        all("sk-or-v1-abcd" not in str(r[0]) for r in rows), rows)

    W._load_settings = lambda: {}
    rows = W.configure_model()
    chk("وبلا إعدادٍ ⟶ يُقال السببُ ولا يُكتب شيء",
        rows and rows[0][1] is False and "config/.env" in rows[0][2], rows)
finally:
    (W._load_settings, W.run) = _r5

print()
print("=" * 70)
print(" 10) التهيئةُ الكاملة — أمرُ أوبن كلاو نفسُه لا بناؤنا")
print("=" * 70)
# «openclaw onboard — Guided setup for auth, models, Gateway, workspace,
#  channels, and skills». وما يكتبه مقيسٌ على تشغيلةٍ حقيقيّةٍ معزولة:
#   auth.profiles.<مزوّد>:default · agents.entries.main · gateway.* ·
#   plugins.entries.<مزوّد>.enabled · tools.profile · skills.install.*
_r6 = (W._load_settings, W.run)
try:
    W._load_settings = lambda: {
        "WEAVER_PROVIDER": "openrouter", "WEAVER_API_KEY": "sk-or-v1-x",
        "WEAVER_MODEL": "deepseek/deepseek-v4-flash",
        "WEAVER_BASE_URL": "https://openrouter.ai/api/v1"}
    _seen = []

    def _run6(args, timeout=180, input_text=None, cwd=None):
        _seen.append(list(args))
        if list(args)[:2] == ["config", "get"]:
            return 0, '""', ""          # لم يجرِ المعالجُ بعد
        return 0, "", ""
    W.run = _run6
    ok, why = W.onboard()
    _a = next((a for a in _seen if a[:1] == ["onboard"]), [])
    chk("يُنادى `onboard` لا بناءٌ من عندنا", bool(_a), _seen[:2])
    chk("  -> بلا أسئلة", "--non-interactive" in _a and "--accept-risk" in _a)
    chk("  -> وباختيارِ الاعتماد الموثَّق",
        "--auth-choice" in _a
        and _a[_a.index("--auth-choice") + 1] == "openrouter-api-key", _a)
    chk("  -> ومفتاحُك بعَلَمه", "--openrouter-api-key" in _a, _a)
    chk("  -> وبمنفذنا لا بمنفذٍ عشوائيّ",
        "--gateway-port" in _a
        and _a[_a.index("--gateway-port") + 1] == str(W.OUR_PORT), _a)
    chk("  -> وبلا تثبيتِ خدمة (لا systemd على Termux)",
        "--skip-daemon" in _a and "--no-install-daemon" in _a, _a)

    def _run7(args, timeout=180, input_text=None, cwd=None):
        if list(args)[:2] == ["config", "get"]:
            return 0, '"2026-09-19T18:51:37.637Z"', ""
        _seen.append(list(args))
        return 0, "", ""
    _seen.clear()
    W.run = _run7
    ok2, why2 = W.onboard()
    chk("ولا تُعاد إن سبق أن جرت", ok2 and not any(a[:1] == ["onboard"]
                                                   for a in _seen), why2)
    chk("  -> إلّا بـforce", (W.onboard(force=True), True)[1])

    W._load_settings = lambda: {}
    ok3, why3 = W.onboard()
    chk("وبلا مفتاحٍ ⟶ يُقال السببُ ولا يُنادى شيء", not ok3, why3)
finally:
    (W._load_settings, W.run) = _r6

print()
print("=" * 70)
print(" 11) المزوّدون من المحرّك · والمتصفّح · واتّفاقُ المنفذ")
print("=" * 70)
_r7 = (W.auth_catalog, W.run)
try:
    W.auth_catalog = lambda refresh=False: [
        {"choice": "openrouter-oauth", "providerId": "openrouter",
         "envVar": "OPENROUTER_API_KEY"},
        {"choice": "openrouter-api-key", "providerId": "openrouter",
         "envVar": "OPENROUTER_API_KEY"},
        {"choice": "venice-api-key", "providerId": "venice"},
        {"choice": "apiKey", "providerId": "anthropic",
         "envVar": "ANTHROPIC_API_KEY"}]
    chk("يُفضَّل الخيارُ بمفتاحٍ لا OAuth (لا متصفّحَ عندنا)",
        W.auth_choice("openrouter") == "openrouter-api-key",
        W.auth_choice("openrouter"))
    chk("ويعرف مزوّداً لم تكن خريطتُنا اليدويّةُ تعرفه",
        W.auth_choice("venice") == "venice-api-key"
        and "venice" not in W._AUTH_CHOICE, W.auth_choice("venice"))
    chk("واسمُ متغيّرِ المفتاح من المحرّك",
        W.key_env_name("anthropic") == "ANTHROPIC_API_KEY")
    chk("والخيارُ العامُّ لا عَلَمَ باسمه", W.auth_flag("apiKey") == "")
    chk("وذو الاسم له عَلَمُه",
        W.auth_flag("venice-api-key") == "--venice-api-key")

    _w = []

    def _run8(args, timeout=180, input_text=None, cwd=None):
        _w.append(list(args))
        if list(args)[:2] == ["config", "get"]:
            return 0, '"x"', ""
        return 0, "", ""
    W.run = _run8
    rows = W.configure_runtime()
    _set = {a[2]: a[3] for a in _w if a[:2] == ["config", "set"]}
    chk("منفذُ البوّابة يُكتب في الإعداد (وإلّا قصدت الأوامرُ منفذاً آخر)",
        _set.get("gateway.port") == str(W.OUR_PORT), _set.get("gateway.port"))
    chk("والمتصفّحُ يحتاج المفتاحين معاً (شرطُ التوثيق)",
        _set.get("plugins.entries.browser.enabled") == "true"
        and _set.get("browser.enabled") == "true", _set)
    chk("  -> وبلا صندوقٍ رمليّ (شرطُ Termux والجذر)",
        _set.get("browser.noSandbox") == "true")
    chk("والتتبّعُ الخارجيُّ يُطفأ", _set.get("telemetry.enabled") == "false")
finally:
    (W.auth_catalog, W.run) = _r7

print()
print("=" * 70)
print(" 12) الإقلاعُ على هاتف: مهلةٌ تكفي، وسببٌ يُقرأ، وقفلٌ يُنظَّف")
print("=" * 70)
# خرجُ جهاز المستخدم: «⚠ لم تسمع خلال 90 ث — انظر …/gateway.log».
# مهلةٌ لا تكفي هاتفاً (٥ ث عندي على خادمٍ سريع، وعشراتٌ عليه)، وإحالةٌ
# إلى ملفٍّ يبحث فيه بدل سببٍ يُقال له.
chk("المهلةُ تكفي هاتفاً ولا تبقى ٩٠", W._GW_READY_WAIT >= 240,
    W._GW_READY_WAIT)
# يُفحَص السلوكُ لا موضعُ السطر: تُعاد قراءةُ الوحدة بمتغيّرٍ مضبوط.
import importlib as _il, os as _os2                        # noqa: E402
_old = _os2.environ.get("WEAVER_GATEWAY_WAIT")
try:
    _os2.environ["WEAVER_GATEWAY_WAIT"] = "137"
    _W2 = _il.reload(W)
    chk("  -> وتُضبَط بمتغيّرِ بيئة", _W2._GW_READY_WAIT == 137,
        _W2._GW_READY_WAIT)
finally:
    if _old is None:
        _os2.environ.pop("WEAVER_GATEWAY_WAIT", None)
    else:
        _os2.environ["WEAVER_GATEWAY_WAIT"] = _old
    W = _il.reload(W)

import tempfile as _tf                                     # noqa: E402
_reallog = W.GATEWAY_LOG
try:
    _f = _tf.NamedTemporaryFile("w", suffix=".log", delete=False,
                                encoding="utf-8")
    _f.write("\x1b[36m[gateway]\x1b[39m loading configuration…\n"
             "\x1b[33m[sqlite/transaction]\x1b[39m slow SQLite transaction hold\n"
             "\x1b[31m[gateway]\x1b[39m Another gateway (pid 99) already owns "
             "this state directory; refusing to run\n")
    _f.close()
    W.GATEWAY_LOG = _f.name
    _why = W._log_reason()
    chk("السببُ يُقرأ من السجلّ لا يُحال إليه",
        "already owns this state directory" in _why, _why)
    chk("  -> بلا ألوانٍ ولا ضجيجِ sqlite",
        "\x1b" not in _why and "sqlite" not in _why.lower(), repr(_why))
finally:
    W.GATEWAY_LOG = _reallog

chk("وقفلٌ بائتٌ يُنظَّف قبل الإقلاع (وإلّا رفض المحرّكُ القيام)",
    "refusing to run" in _i.getsource(W.gateway_start)
    and "os.remove" in _i.getsource(W.gateway_start))

print()
print("=" * 70)
print(" RESULT: " + ("PASS" if _bad[0] == 0 else "FAIL")
      + "   (%d/%d)" % (_ok[0], _ok[0] + _bad[0]))
print("=" * 70)
sys.exit(1 if _bad[0] else 0)
