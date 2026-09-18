# -*- coding: utf-8 -*-
"""بطاقاتُ استدعاء الأدوات — اختبارٌ في متصفّحٍ حقيقيّ.

العطب: كانت الخطواتُ تُرسَم في DOM ولا تُحفَظ مع الرسالة، فتختفي عند فتح
محادثةٍ أخرى أو إعادةِ تحميل الصفحة. فصارت بيانات (`msg.tools`) تُحفَظ وتُعاد.

يُشغّل خادمَ الويب الحقيقيّ ومتصفّحاً حقيقياً، ويفحص السلوكَ لا شكلَ الكود.
يحتاج playwright؛ وإن غاب تخطّى بلا فشل.
"""
import os, sys, json, threading, time
sys.path.insert(0, os.getcwd())
from web import server as S

# محرّكٌ مُحاكى يردّ ويُسجّل نوبةً في سجلّ المحرّك
from pipeline import weaver_core as W
os.makedirs(os.path.dirname(W.LAST_LOG), exist_ok=True)
open(W.LAST_LOG, "w", encoding="utf-8").write(
    "# 2026-09-18T22:30:00\n"
    "# args: agent -m ما الطقس؟ --json --timeout 100 --session-id weaver-c1\n"
    "# exit: 0\n\n--- stdout ---\n"
    '{\n  "ok": true,\n  "final": "الطقس صحوٌ اليوم.",\n'
    '  "payloads": [{"text": "الطقس صحوٌ اليوم.", "mediaUrl": null}],\n'
    '  "model": "deepseek/deepseek-v4-flash",\n  "provider": "openrouter"\n}\n')

S._engine_ready = lambda: True
S._chat_via_engine = lambda m, h=None, t=120, c=None, mem=None, att=None, session=None: {
    "reply": "الطقس صحوٌ اليوم.", "engine": "weaver-core",
    "model": "deepseek/deepseek-v4-flash"}

srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("playwright غير مثبت — تُخطّى")
    raise SystemExit(0)
_CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
if not os.path.exists(_CHROME):
    import glob as _g
    _c = _g.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    if not _c:
        print("لا متصفّح — تُخطّى")
        raise SystemExit(0)
    _CHROME = _c[0]
ok, bad = [0], [0]
def chk(l, c, x=""):
    (ok if c else bad)[0] += 1
    print(("   OK  " if c else "   XX  ") + l + (("   " + str(x)) if (x and not c) else ""))

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=_CHROME)
    pg = b.new_page(viewport={"width": 390, "height": 780})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("try{localStorage.setItem('weaver_username','Bashar')}catch(e){}")
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="load", timeout=60000)
    pg.wait_for_timeout(1200)
    pg.evaluate("()=>{var o=document.getElementById('nameOverlay');"
                "if(o)o.classList.remove('show')}")
    pg.wait_for_timeout(300)

    ta = pg.locator("textarea, [contenteditable=true]").first
    ta.click(); ta.type("ما الطقس؟")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(4000)

    chk("بطاقاتُ الأدوات ظهرت", pg.locator(".tool-acc").count() > 0)
    chk("وفيها بطاقةٌ واحدةٌ على الأقلّ", pg.locator(".tcard").count() > 0,
        pg.locator(".tcard").count())

    chk("والأكورديونُ يُطوى ويُفتح",
        pg.locator(".tool-acc").count() > 0)
    if pg.locator(".tool-acc:not(.open)").count():
        pg.locator(".tool-acc-head").last.click(); pg.wait_for_timeout(400)
    if pg.locator(".tcard").count():
        pg.locator(".tcard").last.click()
        pg.wait_for_timeout(700)
        chk("النافذةُ السفليةُ انفتحت", pg.locator("#wvToolSheet.show").count() == 1)
        chk("فيها مقبضُ سحب", pg.locator(".tsheet-grip").count() == 1)
        chk("وزرُّ إغلاق", pg.locator(".tsheet-x").count() == 1)
        chk("وقائمةُ المهام", pg.locator(".tsheet-tasks li").count() > 0)
        chk("وحاويةٌ طرفيّةٌ داكنة", pg.locator(".tterm").count() > 0)
        chk("وفيها تلوينٌ نحويّ", pg.locator(".tterm .k").count() > 0,
            pg.locator(".tterm .k").count())
        body = pg.locator(".tsheet-body").inner_text()
        chk("المدخلاتُ هي الأمرُ الحقيقيّ", "agent -m" in body, body[:80])
        chk("والمخرجاتُ هي المُغلَّف", "deepseek" in body, body[:80])
        pg.locator(".tsheet-x").click(); pg.wait_for_timeout(400)
        chk("والإغلاقُ يُغلق", pg.locator("#wvToolSheet.show").count() == 0)

    # ── الاختبارُ الحاسم: محادثةٌ أخرى ثمّ العودة ──
    n_before = pg.locator(".tcard").count()
    pg.evaluate("newChat()"); pg.wait_for_timeout(900)
    chk("محادثةٌ جديدة ⟶ لا بطاقات", pg.locator(".tcard").count() == 0)
    cid = pg.evaluate("(async()=>{const r=await fetch('/api/chats');const d=await r.json();"
                      "return (d.chats&&d.chats[0]&&d.chats[0].id)||''})()")
    pg.evaluate("id => selectChat(id)", cid); pg.wait_for_timeout(1500)
    chk("العودةُ للمحادثة ⟶ البطاقاتُ باقية",
        pg.locator(".tcard").count() == n_before,
        f"{pg.locator('.tcard').count()} vs {n_before}")

    pg.reload(wait_until="load"); pg.wait_for_timeout(1200)
    pg.evaluate("id => selectChat(id)", cid); pg.wait_for_timeout(1500)
    chk("وبعد إعادةِ تحميلِ الصفحة ⟶ باقية",
        pg.locator(".tcard").count() == n_before,
        pg.locator(".tcard").count())

    chk("ولا خطأَ جافاسكربت", not errs, errs[:2])
    b.close()
srv.shutdown()
print()
print(" RESULT: " + ("PASS" if bad[0] == 0 else "FAIL") + f"   ({ok[0]}/{ok[0]+bad[0]})")
sys.exit(1 if bad[0] else 0)
