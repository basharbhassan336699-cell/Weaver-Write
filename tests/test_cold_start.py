"""أوّلُ ردٍّ بعد تحديثٍ أو تشغيل، ولغةُ الرد، واتّجاهُه، ومربّعُ الأدوات الفارغ.

    python3 tests/test_cold_start.py

مقيس (نموذجٌ وهميٌّ يردّ فوراً، فكلُّ الوقت للنظام): قبل الإصلاح ٤٠٫٦ ث قبل
أوّل ردّ، منها ٩ ث للبوّابة و١٥ إقلاعاً كاملاً للمحرّك (قراءةُ قيمةٍ واحدة،
كتابةُ إعدادٍ لم يتغيّر، وتجربةُ كلِّ مزوّد بحثٍ واحداً واحداً). وبعده ٧٫١ ث
(البوّابةُ وحدها) وصفرُ إقلاعاتٍ قبل الردّ، والبحثُ في الخلفية. وعلى الهاتف
الإقلاعُ الواحدُ ٢٠–٤٠ ث، فكانت تلك دقائق.
"""
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILS = []


def check(name, cond):
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        FAILS.append(name)


def test_config_fast(tmp):
    from pipeline import weaver_core as wc
    old = wc.CONFIG_FILE
    wc.CONFIG_FILE = os.path.join(tmp, "openclaw.json")
    try:
        check("ملفٌّ غيرُ موجود ⟵ يُسأل المحرّكُ كما كان",
              wc.config_get_fast("gateway.mode") == (False, None))
        cfg = {"gateway": {"mode": "local", "auth": {"token": "t"}},
               "tools": {"web": {"search": {"enabled": True}}},
               "models": {"providers": {"weaver": {"baseUrl": "u", "models": [1]}}}}
        json.dump(cfg, open(wc.CONFIG_FILE, "w"))
        check("قيمةٌ تُقرأ من الملفّ بلا إقلاع", wc.config_get_fast("gateway.mode") == (True, "local"))
        ok, v = wc.config_get_fast("tools.web.search.provider")
        check("ومفتاحٌ غيرُ مضبوط يُعرف", ok and v is wc._CFG_MISSING)
        check("chosen_provider من الملفّ (لا اختيار ⟵ \"\")", wc.chosen_provider() == "")
        check("config_has: المكتوبُ كما هو ⟵ لا كتابة",
              wc.config_has({"gateway": {"mode": "local"}}))
        check("config_has: قيمةٌ مختلفة ⟵ يُكتب", not wc.config_has({"gateway": {"mode": "remote"}}))
        check("config_has: None (حذف) ومفقود ⟵ مطابق", wc.config_has({"x": {"y": None}}))
        check("config_has: None وموجود ⟵ يُكتب", not wc.config_has({"gateway": {"mode": None}}))
        check("config_has: ما يُستبدَل يُطابَق كاملاً لا بعضاً",
              not wc.config_has({"models": {"providers": {"weaver": {"baseUrl": "u"}}}},
                                exact_paths=["models.providers.weaver"]))
        open(wc.CONFIG_FILE, "w").write("{ json5: 'غير صالح', }")
        check("ملفٌّ ليس JSON ⟵ يُسأل المحرّكُ كما كان",
              wc.config_get_fast("gateway.mode") == (False, None) and not wc.config_has({}))
    finally:
        wc.CONFIG_FILE = old


def test_search_bg(tmp):
    from pipeline import weaver_core as wc
    old = wc.WEB_SEARCH_STATUS
    wc.WEB_SEARCH_STATUS = os.path.join(tmp, "st.json")
    try:
        json.dump({"ts": time.time()}, open(wc.WEB_SEARCH_STATUS, "w"))
        check("فحصُ البحث: نتيجةٌ حديثة ⟵ لا يُعاد", wc._search_guard_async() is False)
        os.environ["WEAVER_SEARCH_GUARD_SYNC"] = "1"
        check("والقديمُ (قبل الردّ) يعود بالبيئة", wc._search_guard_sync())
        del os.environ["WEAVER_SEARCH_GUARD_SYNC"]
        check("والافتراضيُّ: في الخلفية", not wc._search_guard_sync())
    finally:
        wc.WEB_SEARCH_STATUS = old
    src = open(os.path.join(ROOT, "pipeline", "weaver_core.py"), encoding="utf-8").read()
    i = src.index("def gateway_start")
    body = src[i:src.index("\ndef ", i + 10)]
    check("gateway_start لا يسأل المحرّكَ عن gateway.mode إن قُرئ الملفّ",
          'config_get_fast("gateway.mode")' in body)


def test_server_ui():
    s = open(os.path.join(ROOT, "web", "server.py"), encoding="utf-8").read()
    check("server: المحرّكُ يُجهَّز عند التشغيل لا عند أوّل رسالة",
          "def _engine_warmup" in s and "target=_engine_warmup" in s)
    check("server: «تجهيز المحرّك…» بدل «التفكير» حين لم يُقلع بعد",
          "Starting the engine…" in s)
    check("server: سطرُ لغة الرد للرسائل غير العربيّة فقط",
          "if not _ar:" in s and "[Reply language]" in s)
    h = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    check("ui: فقراتُ الرد باتّجاهها (عربيّ يميناً)",
          "'<p dir=\"auto\">'" in h and "<li dir=\"auto\">" in h)
    check("ui: مربّعُ الأدوات لا يظهر بلا أداةٍ حقيقيّة",
          "function wvToolsReal" in h and "wvToolsReal(tools).length" in h)
    check("ui: «التفكير» وبطاقةُ النوبة ليستا أدوات",
          "t.kind === 'engine' && t.status !== 'err'" in h)


if __name__ == "__main__":
    print("cold start / reply language / direction / empty tool box")
    tmp = tempfile.mkdtemp(prefix="wv-cs-")
    try:
        test_config_fast(tmp)
        test_search_bg(tmp)
        test_server_ui()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("FAIL: " + ", ".join(FAILS) if FAILS else "PASS")
    sys.exit(1 if FAILS else 0)
