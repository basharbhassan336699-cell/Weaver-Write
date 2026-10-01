# -*- coding: utf-8 -*-
"""الرسمُ التفاعليّ داخل Weaver Write — في متصفّحٍ حقيقيّ.

كانت ملفّاتُ HTML تُعرض في المعاينة **نصّاً مصدريّاً** (<pre>)، فلا يعمل فيها
شيء. الآن: إطارٌ معزول (sandbox=allow-scripts بلا allow-same-origin) والخادمُ
يرسلها بـCSP «sandbox · default-src 'none'» — فيعمل الرسم، ولا تصل الصفحةُ إلى
واجهات التطبيق ولا إلى الشبكة.

Chart.js 4.5.1 المضمَّنة (engines/frontend-core/vendored) تضع الصنفَ في
window.Chart ثمّ يعيد سطرُها الأوّل تعريفَه حاويةً {default} — مقيسٌ هنا:
بلا معالجة «Chart.getChart is not a function».
"""
import glob
import json
import os
import subprocess
import sys
import tempfile
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "web"))
import server as S   # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright غيرُ مثبَّت — تُخطّى")
    sys.exit(0)
_CHROME = (sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
           or [None])[0]

OUT = tempfile.mkdtemp(prefix="weaver-test-ichart-")
spec = os.path.join(OUT, "s.json")
json.dump({"type": "bar", "title": "عدد الحالات", "data": {
    "labels": ["بسيطة", "متوسّطة", "حادّة"], "values": [12, 7, 3]}},
    open(spec, "w", encoding="utf-8"), ensure_ascii=False)
HTML = os.path.join(OUT, "رسم.html")
r = subprocess.run([sys.executable, os.path.join(_ROOT, "pipeline", "office.py"),
                    "chart", spec, "--out", HTML], capture_output=True, text=True,
                   timeout=120)
ok("office.py chart --out رسم.html ⟵ صفحةٌ تفاعليّة", r.returncode == 0
   and "interactive chart bar" in r.stdout and os.path.isfile(HTML), r.stdout + r.stderr)
page = open(HTML, encoding="utf-8").read()
import re   # noqa: E402
# روابطُ تُحمَّل فعلاً (لا «cdn» عَرَضاً داخل بيانات الخطّ base64 — قِيس)
ok("بلا شبكة: لا رابطَ يُحمَّل (src/href/url بـhttp)", not re.search(
    r"""(?:src|href)\s*=\s*["']?https?:|url\(\s*["']?https?:""", page, re.I))
ok("الخطُّ مضمَّن (data:font/ttf)", "data:font/ttf;base64," in page)

_real = S._output_dir
S._output_dir = lambda: OUT
srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    import urllib.request
    import urllib.parse
    u = "http://127.0.0.1:%d/api/output?path=%s" % (port, urllib.parse.quote("رسم.html"))
    resp = urllib.request.urlopen(u, timeout=20)
    csp = resp.headers.get("Content-Security-Policy", "")
    ok("الخادم: CSP sandbox بلا شبكة للمعاينة", "sandbox allow-scripts" in csp
       and "default-src 'none'" in csp and "allow-same-origin" not in csp, csp)
    resp2 = urllib.request.urlopen(u + "&download=1", timeout=20)
    ok("  ⟵ والتحميلُ مرفقٌ كما كان", "attachment" in (
        resp2.headers.get("Content-Disposition") or ""))

    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=_CHROME)
        pg = b.new_page(viewport={"width": 412, "height": 820})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:%d/" % port, wait_until="load", timeout=60000)
        pg.wait_for_timeout(800)
        pg.evaluate("n => wvOpenPreview(n)", "رسم.html")
        pg.wait_for_timeout(2500)
        fr_el = pg.query_selector(".fp-body iframe")
        ok("المعاينة: إطارٌ لا نصٌّ مصدريّ", fr_el is not None
           and pg.query_selector(".fp-body pre") is None)
        sb = fr_el.get_attribute("sandbox") if fr_el else ""
        ok("  ⟵ معزول: allow-scripts بلا allow-same-origin", sb is not None
           and "allow-scripts" in sb and "allow-same-origin" not in sb, sb)
        fr = fr_el.content_frame() if fr_el else None
        info = fr.evaluate("""() => { const c = WeaverChart.getChart('c');
            const m = c.getDatasetMeta(0);
            return {n: m.data.length, first: m.data[0].x, last: m.data[2].x}; }""") \
            if fr else {}
        ok("الرسمُ يعمل داخل التطبيق (٣ أعمدة)", info.get("n") == 3, info)
        ok("  ⟵ والعمودُ الأوّلُ يميناً", info.get("first", 0) > info.get("last", 0),
           info)
        leak = fr.evaluate("""async () => { try { await fetch('/api/outputs');
            return 'reached'; } catch (e) { return 'blocked'; } }""") if fr else ""
        ok("لا تصل الصفحةُ إلى واجهات التطبيق", leak == "blocked", leak)
        net = fr.evaluate("""async () => { try { await fetch('https://example.com');
            return 'reached'; } catch (e) { return 'blocked'; } }""") if fr else ""
        ok("ولا إلى الإنترنت", net == "blocked", net)
        ok("بلا أخطاء", not errs, errs)
        b.close()
finally:
    srv.shutdown()
    S._output_dir = _real

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
