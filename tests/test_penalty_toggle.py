# -*- coding: utf-8 -*-
"""زرُّ «تقليل التكرار» في الإعدادات ⟵ /api/penalty ⟵ config/.env.

تشغيلٌ يكتب WEAVER_FREQUENCY_PENALTY، وإطفاءٌ يكتب 0 (فتتوقّف فوراً في
الخادم نفسِه بلا إعادة تشغيل)، وقيمةٌ غيرُ صالحة ⟵ 0. وسطورُ المفتاح
وغيرُه في .env لا تُمَسّ.
"""
import json
import os
import pathlib
import sys
import tempfile
import threading
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "web"))

import server as S                        # noqa: E402
from config import keysync as K          # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


_TMP = pathlib.Path(tempfile.mkdtemp())
_real = (K._ENV_FILE, K._CONF_DIR)
_saved = os.environ.get("WEAVER_FREQUENCY_PENALTY")
os.environ.pop("WEAVER_FREQUENCY_PENALTY", None)
K._CONF_DIR = _TMP
K._ENV_FILE = _TMP / ".env"
K._ENV_FILE.write_text("# إعدادي\nWEAVER_API_KEY=sk-secret-1234\n"
                       "WEAVER_MODEL=m1\n", encoding="utf-8")

srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def get():
    return json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/api/penalty" % port, timeout=20).read())


def post(v):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/penalty" % port,
        data=json.dumps({"frequency": v}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def env_text():
    return K._ENV_FILE.read_text(encoding="utf-8")


try:
    print("\n— الافتراض —")
    ok("مطفأة افتراضياً", get() == {"frequency": 0}, str(get()))
    ok("والحمولةُ المباشرةُ بلا عقوبة", S._penalty_payload(
        K.get_settings()) == {})

    print("\n— تشغيل —")
    r = post(0.3)
    ok("POST 0.3 ⟵ ok", r.get("ok") and r.get("frequency") == 0.3, str(r))
    ok("كُتبت في .env", "WEAVER_FREQUENCY_PENALTY=0.3" in env_text(),
       env_text())
    ok("والمفتاحُ والتعليقُ والنموذجُ باقية",
       "WEAVER_API_KEY=sk-secret-1234" in env_text()
       and "# إعدادي" in env_text() and "WEAVER_MODEL=m1" in env_text())
    ok("GET يقرؤها", get() == {"frequency": 0.3}, str(get()))
    ok("والمسارُ المباشرُ يرسلها فوراً",
       S._penalty_payload(K.get_settings()) == {"frequency_penalty": 0.3})

    print("\n— إطفاء —")
    r = post(0)
    ok("POST 0 ⟵ تُكتب 0 (لا يُحذف السطر)",
       "WEAVER_FREQUENCY_PENALTY=0" in env_text()
       and "0.3" not in env_text(), env_text())
    ok("GET ⟵ 0", get() == {"frequency": 0})
    ok("والمسارُ المباشرُ يتوقّف فوراً بلا إعادة تشغيل",
       S._penalty_payload(K.get_settings()) == {})

    print("\n— قيمٌ غيرُ صالحة ⟵ مطفأة —")
    for bad in (-1, 5, "abc", None):
        post(0.5)
        r = post(bad)
        ok("«%s» ⟵ 0" % bad, r.get("frequency") == 0 and get() ==
           {"frequency": 0}, str(r))

    print("\n— الواجهة —")
    html = open(os.path.join(_ROOT, "web", "index.html"),
                encoding="utf-8").read()
    ok("زرٌّ في الإعدادات", 'id="penaltyToggle"' in html
       and 'id="penaltyLevel"' in html)
    ok("  ⟵ داخل لوحة Capabilities", html.index('id="panel-capabilities"')
       < html.index('id="penaltyToggle"') < html.index('id="panel-plugins"'))
    ok("  ⟵ مطفأ افتراضياً في الواجهة",
       'id="penaltyToggle" checked' not in html)
    ok("  ⟵ يحفظ عبر /api/penalty", "fetch('/api/penalty'" in html
       and "function wvSavePenalty" in html and "function wvLoadPenalty" in html)
finally:
    srv.shutdown()
    K._ENV_FILE, K._CONF_DIR = _real
    if _saved is None:
        os.environ.pop("WEAVER_FREQUENCY_PENALTY", None)
    else:
        os.environ["WEAVER_FREQUENCY_PENALTY"] = _saved

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
