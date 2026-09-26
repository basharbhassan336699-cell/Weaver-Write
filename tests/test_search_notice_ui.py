# -*- coding: utf-8 -*-
"""تنبيهُ البحث في الواجهة: يظهر مرّةً لكلِّ فحص، ولا يتكرّر بعد التحديث.
يحتاج playwright؛ وإن غاب تخطّى بلا فشل."""
import glob
import json
import os
import sys
import tempfile
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_ROOT, os.path.join(_ROOT, "web")]
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("playwright غير مثبت — تُخطّى")
    sys.exit(0)
_c = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
if not _c:
    print("chromium غير موجود — تُخطّى")
    sys.exit(0)
import server as S                        # noqa: E402
from pipeline import weaver_core as W     # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


_real = W.WEB_SEARCH_STATUS
W.WEB_SEARCH_STATUS = os.path.join(tempfile.mkdtemp(), "status.json")
W._json_write(W.WEB_SEARCH_STATUS, {
    "ok": True, "provider": "parallel-free", "origin": "system",
    "switched_from": "duckduckgo", "error": "bot-detection", "ts": time.time()})
srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=_c[0])
        pg = b.new_page()
        pg.goto(f"http://127.0.0.1:{port}/", wait_until="load", timeout=60000)
        pg.wait_for_timeout(1500)
        txt = pg.inner_text("body")
        ok("بُدِّل المزوّد ⟵ تنبيهٌ يذكر القديمَ والجديد",
           "duckduckgo" in txt and "parallel-free" in txt
           and ("now using" in txt or "صار البحث" in txt))
        pg.reload(wait_until="load")
        pg.wait_for_timeout(1500)
        _b = pg.inner_text("body")
        ok("  ⟵ ولا يتكرّر بعد التحديث", "now using" not in _b
           and "صار البحث" not in _b, _b[-200:])
        W._json_write(W.WEB_SEARCH_STATUS, {
            "ok": False, "provider": "brave", "origin": "user",
            "switched_from": "", "error": "401", "ts": time.time() + 5})
        pg.reload(wait_until="load")
        pg.wait_for_timeout(1500)
        c = pg.inner_text("body")
        ok("اختيارُك لا يعمل ⟵ تنبيهٌ بكيفيّة التغيير", "brave" in c
           and "--web-search choose" in c)
        b.close()
finally:
    srv.shutdown()
    W.WEB_SEARCH_STATUS = _real

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
