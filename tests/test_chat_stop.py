"""زرُّ «إيقاف»، وطيُّ القائمة الجانبية، ورسالةُ المستخدم (Markdown + نسخ).

    python3 tests/test_chat_stop.py

الإيقافُ الحقيقيُّ عبر المحرّك قِيس يدوياً بنموذجٍ وهميٍّ بطيء وبوّابةٍ حيّة
(العمليةُ المقيمة وسطرُ الأوامر كلاهما: النوبةُ تتوقّف فوراً، واتّصالُ النموذج
يُقطع). وهنا ما يُفحص بلا محرّك:
  · `abort()` يُرسل SIGINT لنوبة سطر الأوامر المسجّلة باسم جلستها وحدها.
  · العمليةُ المقيمة فيها `/abort` و`deps.process` لكلِّ نوبة.
  · الخادمُ فيه `/api/chat/stop` ولا يُعيد الطلبَ بالمسار المباشر بعد الإيقاف.
  · الواجهة: الزرُّ يتبدّل، والقائمةُ لا تُفتح إلا بعبور حدِّ الهاتف، ورسالةُ
    المستخدم تُرسم Markdown ومعها نسخ.
"""
import os
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILS = []


def check(name, cond):
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        FAILS.append(name)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_abort_cli():
    from pipeline import weaver_core as wc
    # عمليتان: واحدةٌ لجلستنا وأخرى لجلسةٍ غيرها — لا تُمسّ.
    code = ("import signal,sys,time\n"
            "signal.signal(signal.SIGINT, lambda *a: sys.exit(130))\n"
            "time.sleep(30)\n")
    mine = subprocess.Popen([sys.executable, "-c", code])
    other = subprocess.Popen([sys.executable, "-c", code])
    time.sleep(0.5)
    sid, sid2 = wc._session_id("chat-A"), wc._session_id("chat-B")
    with wc._CLI_TURNS_LOCK:
        wc._CLI_TURNS.setdefault(sid, set()).add(mine)
        wc._CLI_TURNS.setdefault(sid2, set()).add(other)
    saved = (wc._WORKER.get("proc"), wc._WORKER.get("port"))
    wc._WORKER["proc"], wc._WORKER["port"] = None, None
    try:
        r = wc.abort("chat-A")
        try:
            rc = mine.wait(timeout=10)
        except subprocess.TimeoutExpired:
            rc = None
        check("abort: نوبةُ سطر الأوامر تتلقّى SIGINT وتخرج (130)", rc == 130)
        check("abort: يُبلغ via=cli و aborted=1",
              r.get("via") == "cli" and r.get("aborted") == 1 and r.get("ok"))
        check("abort: نوبةُ محادثةٍ أخرى لا تُمسّ", other.poll() is None)
        check("abort: بلا جلسة ⟵ لا شيء", wc.abort("")["aborted"] == 0)
    finally:
        wc._WORKER["proc"], wc._WORKER["port"] = saved
        for p in (mine, other):
            if p.poll() is None:
                p.kill()
                p.wait()
        with wc._CLI_TURNS_LOCK:
            wc._CLI_TURNS.pop(sid, None)
            wc._CLI_TURNS.pop(sid2, None)


def test_worker_source():
    js = read("engines/weaver-core/gateway_worker.mjs")
    check("worker: نقطةُ /abort", 'req.url === "/abort"' in js)
    check("worker: «عمليةٌ» لكلِّ نوبة يمرّرها للمحرّك",
          "agentCliCommand(opts, rt, { process: turn.proc })" in js)
    check("worker: إشاراتُ العملية الحقيقيّة تُمرَّر للنوبات",
          "process.on(sig, h)" in js and "process.off(sig, h)" in js)
    if subprocess.run(["node", "--version"], capture_output=True).returncode == 0:
        r = subprocess.run(["node", "--check", os.path.join(
            ROOT, "engines/weaver-core/gateway_worker.mjs")],
            capture_output=True, text=True)
        check("worker: node --check", r.returncode == 0)


def test_server():
    sys.path.insert(0, os.path.join(ROOT, "web"))
    import server as srv
    check("server: /api/chat/stop", '"/api/chat/stop"' in read("web/server.py"))
    srv._stop_clear("x1")
    check("server: لا علَمَ قبل الطلب", not srv._stop_requested("x1"))
    with srv._TURNS_LOCK:
        srv._STOPPED["x1"] = time.time()
    check("server: العلَمُ يُرفع", srv._stop_requested("x1"))
    srv._stop_clear("x1")
    check("server: ويُمحى مع رسالةٍ جديدة", not srv._stop_requested("x1"))
    s = read("web/server.py")
    check("server: لا مسارَ مباشرَ بعد الإيقاف",
          'if session and _stop_requested(session):' in s)


def test_ui():
    h = read("web/index.html")
    check("ui: الزرُّ يُرسل أو يوقف", 'onclick="wvSendOrStop()"' in h
          and "function wvSendOrStop()" in h and "ico-stop" in h)
    check("ui: AbortController للردّ", "signal: wvCtrl ? wvCtrl.signal : undefined" in h)
    check("ui: الإيقافُ يصل الخادم", "'/api/chat/stop'" in h)
    check("ui: القائمةُ لا تتبدّل إلا بعبور الحدّ",
          "if (_m === wvWasMobile) return;" in h)
    check("ui: رسالةُ المستخدم Markdown",
          "d.querySelector('.bubble').innerHTML = renderMarkdown(raw);" in h)
    check("ui: نسخُ رسالة المستخدم",
          "btn.closest('.msg.ai') || btn.closest('.msg.user')" in h
          and "wv-user-actions" in h)
    check("ui: إعادةُ التوليد تقرأ النصَّ الأصليّ",
          "userText = el.dataset.raw ||" in h)
    check("ui: قواعدُ الردّ لم تُمسّ",
          h.count(".msg.ai .bubble") == 44)


if __name__ == "__main__":
    print("chat stop / sidebar / user markdown")
    test_abort_cli()
    test_worker_source()
    test_server()
    test_ui()
    print("FAIL: " + ", ".join(FAILS) if FAILS else "PASS")
    sys.exit(1 if FAILS else 0)
