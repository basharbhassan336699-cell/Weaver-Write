# -*- coding: utf-8 -*-
"""حتى ٥ محادثاتٍ تعمل معاً في تبويبٍ واحد — وكلُّ ردٍّ إلى محادثته.

العطبُ: الواجهةُ كانت تحفظ الردَّ في «المحادثة المفتوحة الآن». أرسلتَ في (أ)
وانتقلتَ إلى (ب) قبل وصوله ⟵ حُفظ ردُّ (أ) في (ب) وضاع من (أ).

في متصفّحٍ حقيقيّ ووكيلٍ مزيَّفٍ بطيء: خمسُ محادثاتٍ تُرسَل وتُترك، والسادسةُ
تُمنَع بتنبيه، والعودةُ إلى محادثةٍ جاريةٍ تُعيد ردَّها الحيَّ إلى الشاشة، وكلُّ
ردٍّ يُحفَظ في محادثته وحدَها. يحتاج playwright؛ وإن غاب تخطّى بلا فشل.
"""
import glob
import json
import os
import re
import sys
import tempfile
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "web"))

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
from config import keysync as K           # noqa: E402
import pathlib                            # noqa: E402

# الإعدادُ يُكتب في config/.env — فيُعزل في ملفٍّ مؤقّت.
_ENV_TMP = pathlib.Path(tempfile.mkdtemp())
_real_env = (K._ENV_FILE, K._CONF_DIR)
K._CONF_DIR, K._ENV_FILE = _ENV_TMP, _ENV_TMP / ".env"
K._ENV_FILE.write_text("", encoding="utf-8")
os.environ.pop("WEAVER_PARALLEL_CHATS", None)

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


CH = tempfile.mkdtemp()
WS = tempfile.mkdtemp()
_real = {"chats": S._CHATS_DIR, "ws": W.workspace_dir,
         "ready": S._engine_ready, "eng": S._chat_via_engine}
S._CHATS_DIR = CH
W.workspace_dir = lambda: WS
S._engine_ready = lambda: True
_release = threading.Event()


def _fake_engine(m, h=None, t=120, c=None, mem=None, att=None, session=None):
    """يردّ بنصِّ الطلب نفسِه — ويتأخّر حتى يُؤذَن له، لتبقى المحادثاتُ جاريةً."""
    _release.wait(timeout=40)
    tag = re.search(r"طلب-(\d+)", str(m) or "")
    return {"reply": "ردٌّ على طلب-%s" % (tag.group(1) if tag else "?"),
            "engine": "weaver-core", "model": "m"}


S._chat_via_engine = _fake_engine
srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def stored():
    """{رقمُ المحادثة: [نصوصُ الرسائل]} كما حُفظت على الخادم."""
    out = {}
    for f in glob.glob(os.path.join(CH, "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        out[d.get("id")] = [(m.get("role"), m.get("content"))
                            for m in d.get("messages") or []]
    return out


try:
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=_c[0])
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/", wait_until="load", timeout=60000)
        pg.evaluate("()=>{var o=document.getElementById('nameOverlay');"
                    "if(o)o.classList.remove('show')}")
        pg.wait_for_timeout(500)

        def send(txt):
            pg.evaluate("t => { const i=document.getElementById('mainInput');"
                        " i.value=t; sendMessage(); }", txt)
            pg.wait_for_timeout(400)

        print("\n— الحدُّ من الإعدادات —")
        ok("الافتراضيُّ ٢ (حمايةٌ للهاتف)", pg.evaluate("WV_MAX_PARALLEL") == 2
           and pg.evaluate("document.getElementById('parallelLimit').value")
           == "2")
        pg.evaluate("()=>{document.getElementById('parallelLimit').value='5';"
                    "wvSaveParallel();}")
        pg.wait_for_timeout(700)
        ok("اختيارُ ٥ من الإعدادات ⟵ يُحفَظ ويعمل",
           pg.evaluate("WV_MAX_PARALLEL") == 5
           and "WEAVER_PARALLEL_CHATS=5" in K._ENV_FILE.read_text())

        print("\n— خمسُ محادثاتٍ تُرسَل وتُترك تعمل —")
        ids = []
        for i in range(1, 6):
            pg.evaluate("newChat()")
            pg.wait_for_timeout(200)
            send("طلب-%d" % i)
            ids.append(pg.evaluate("currentChatId"))
        ok("خمسُ محادثاتٍ مختلفة", len(set(ids)) == 5, ids)
        ok("كلُّها جارية", pg.evaluate("wvInflightCount()") == 5)
        ok("  ⟵ ونقاطٌ خضراءُ في القائمة", pg.locator(
            ".chat-item.running").count() == 5,
           pg.locator(".chat-item.running").count())

        print("\n— السادسة تُمنَع بتنبيه —")
        pg.evaluate("newChat()")
        pg.wait_for_timeout(200)
        send("طلب-6")
        ok("لم تُرسَل (لا محادثةَ سادسة)", pg.evaluate("currentChatId") is None
           and pg.evaluate("wvInflightCount()") == 5)
        ok("  ⟵ وظهر التنبيه", "انتظر انتهاءَ إحداها" in pg.content()
           or "wait for one to finish" in pg.content())

        print("\n— العودةُ إلى محادثةٍ جارية —")
        pg.evaluate("id => selectChat(id)", ids[1])
        pg.wait_for_timeout(1200)
        ok("ردُّها الحيُّ عاد إلى الشاشة", pg.locator(
            "#messages .msg.ai").count() == 1, pg.locator(
            "#messages .msg.ai").count())

        print("\n— الردودُ تصل وأنت في محادثةٍ أخرى —")
        pg.evaluate("id => selectChat(id)", ids[1])   # نبقى في الثانية
        pg.wait_for_timeout(600)
        _release.set()
        deadline = time.time() + 30
        while time.time() < deadline and pg.evaluate("wvInflightCount()"):
            pg.wait_for_timeout(300)
        pg.wait_for_timeout(1500)
        ok("انتهت كلُّها", pg.evaluate("wvInflightCount()") == 0)
        st = stored()
        good = True
        detail = {}
        for i, cid in enumerate(ids, start=1):
            msgs = st.get(cid) or []
            want = [("user", "طلب-%d" % i), ("assistant", "ردٌّ على طلب-%d" % i)]
            detail[i] = msgs
            if msgs != want:
                good = False
        ok("كلُّ محادثةٍ فيها طلبُها وردُّها هي — لا غيرُه", good, detail)
        ok("  ⟵ والمحادثةُ المفتوحةُ ترى ردَّها على الشاشة",
           "ردٌّ على طلب-2" in pg.locator("#messages").inner_text())
        ok("  ⟵ ولا ردَّ محادثةٍ أخرى على الشاشة",
           "طلب-3" not in pg.locator("#messages").inner_text())
        ok("والنقاطُ الخضراءُ انطفأت", pg.locator(
            ".chat-item.running").count() == 0)
        ok("بلا أخطاءِ JavaScript", not errs, errs[:3])
        b.close()
finally:
    _release.set()
    srv.shutdown()
    S._CHATS_DIR = _real["chats"]
    W.workspace_dir = _real["ws"]
    S._engine_ready = _real["ready"]
    S._chat_via_engine = _real["eng"]
    K._ENV_FILE, K._CONF_DIR = _real_env
    os.environ.pop("WEAVER_PARALLEL_CHATS", None)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
