"""عرضُ الأدوات حيّاً: خطواتُ المحرّك تصل الواجهةَ لحظةَ حدوثها.

    python3 tests/test_live_steps.py

قِيس على محرّكٍ حقيقيّ ونموذجٍ وهميّ: جدولُ transcript_events يُكتب أثناء
النوبة (رسالةُ النموذج مع الأداة لحظةَ وصولها، ونتيجتُها لحظةَ انتهائها)،
وجدولُ trajectory_runtime_events في نهايتها فقط. وهنا ما يُفحص آليّاً.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILS = []


def check(name, cond):
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        FAILS.append(name)


def _row(seq, msg):
    return json.dumps({"type": "message", "id": "e%d" % seq, "message": msg},
                      ensure_ascii=False)


def test_events_of():
    from pipeline.live_steps import events_of
    a = json.loads(_row(1, {"role": "assistant", "content": [
        {"type": "text", "text": "سأقرأ الملف أولاً."},
        {"type": "toolCall", "id": "c1", "name": "read", "arguments": {"path": "a.md"}}]}))
    ev = events_of(a)
    check("كلامُ النموذج بين الأدوات ⟵ note", ev[0] == {"k": "note", "text": "سأقرأ الملف أولاً."})
    check("الأداةُ حين تبدأ ⟵ call", ev[1]["k"] == "call" and ev[1]["name"] == "read"
          and ev[1]["args"] == {"path": "a.md"})
    r = json.loads(_row(2, {"role": "toolResult", "toolCallId": "c1", "toolName": "exec",
                            "content": [{"type": "text", "text": "ok"}], "isError": False,
                            "details": {"exitCode": 0, "durationMs": 3100, "junk": 1}}))
    ev = events_of(r)
    check("النتيجةُ حين تنتهي ⟵ result بتفاصيلها",
          ev[0]["k"] == "result" and ev[0]["ok"] and ev[0]["details"] == {"exitCode": 0, "durationMs": 3100})
    fin = json.loads(_row(3, {"role": "assistant", "content": [{"type": "text", "text": "الجواب"}]}))
    check("الجوابُ النهائيُّ لا يتكرّر (يصل بطريقه)", events_of(fin) == [])
    check("غيرُ الرسائل ⟵ لا شيء", events_of({"type": "custom"}) == [])


def test_web():
    from pipeline import live_steps as L
    w = ('SECURITY NOTICE: x\n\n<<<EXTERNAL_UNTRUSTED_CONTENT id="ab">>>\nSource: Web Search\n---\n'
         'عنوان\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id="ab">>>')
    check("علاماتُ المحتوى الخارجيّ تُزال", L.unwrap(w) == "عنوان")
    t = json.dumps({"kind": "results", "query": "q", "results": [
        {"title": w, "url": "https://www.moet.gov.ae/x", "snippet": "s"}]})
    txt, extra, ok = L._web("web_search", t)
    check("نتائجُ البحث ⟵ عنوانٌ ورابطٌ وموقع",
          ok and extra["results"][0] == {"title": "عنوان", "url": "https://www.moet.gov.ae/x",
                                          "site": "moet.gov.ae", "snippet": "s"})
    _, _, ok = L._web("web_search", json.dumps({"status": "error", "error": "no key"}))
    check("بحثٌ فاشل ⟵ يُعلَّم فاشلاً", ok is False)


def test_tail(tmp):
    from pipeline import live_steps as L
    db = os.path.join(tmp, "a.sqlite")
    c = sqlite3.connect(db)
    c.executescript("""
      CREATE TABLE session_windows (session_id TEXT PRIMARY KEY, session_key TEXT);
      CREATE TABLE session_nodes (session_key TEXT PRIMARY KEY, current_session_id TEXT);
      CREATE TABLE transcript_events (session_id TEXT, seq INTEGER, event_json TEXT,
                                      created_at INTEGER, PRIMARY KEY (session_id, seq));
    """)
    key = "agent:main:explicit:weaver-c1"
    c.execute("INSERT INTO session_windows VALUES ('w1', ?)", (key,))
    c.execute("INSERT INTO session_nodes VALUES (?, 'w1')", (key,))
    c.execute("INSERT INTO transcript_events VALUES ('w1', 1, ?, 0)",
              (_row(1, {"role": "assistant", "content": [
                  {"type": "toolCall", "id": "old", "name": "read", "arguments": {}}]}),))
    c.commit()
    L._db_path, L._key = (lambda: db), (lambda s: key)
    t = L.Tail("c1")
    check("Tail: ما قبل النوبة لا يُعرض", t.ok and t.poll() == [])
    c.execute("INSERT INTO transcript_events VALUES ('w1', 2, ?, 0)",
              (_row(2, {"role": "assistant", "content": [
                  {"type": "text", "text": "أبحث."},
                  {"type": "toolCall", "id": "n1", "name": "web_search", "arguments": {"query": "x"}}]}),))
    c.commit()
    ev = t.poll()
    check("Tail: الجديدُ يُقرأ فوراً", [e["k"] for e in ev] == ["note", "call"])
    check("Tail: ولا يُعاد", t.poll() == [])
    # نافذةُ جلسةٍ جديدة أثناء النوبة (أوّلُ رسالةٍ في المحادثة)
    c.execute("INSERT INTO session_windows VALUES ('w2', ?)", (key,))
    c.execute("INSERT INTO transcript_events VALUES ('w2', 0, ?, 0)",
              (_row(0, {"role": "toolResult", "toolCallId": "n1", "toolName": "web_search",
                        "content": [{"type": "text", "text": "{}"}]}),))
    c.commit()
    check("Tail: ونافذةٌ جديدةٌ تُتابَع", [e["k"] for e in t.poll()] == ["result"])
    c.close()
    L2 = L.Tail.__new__(L.Tail)
    L2.path, L2.key, L2.seen, L2.ok = os.path.join(tmp, "none.sqlite"), key, {}, True
    check("Tail: قاعدةٌ غيرُ موجودة ⟵ لا أحداث بلا استثناء", L2.poll() == [])


def test_server_ui():
    s = open(os.path.join(ROOT, "web", "server.py"), encoding="utf-8").read()
    check("server: قارئٌ حيٌّ أثناء النوبة", "_live_pump" in s and '"t": "live"' in s)
    check("server: الكتابةُ للمجرى بقفل (خيطان)", "_sse_lock" in s)
    h = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    check("ui: الأحداثُ الحيّة تُرسم", "ev.t === 'live'" in h and "function wvTlApply" in h)
    check("ui: نافذةُ Summary وتفاصيلُ الأداة",
          "function wvTlOpenSheet" in h and "function wvTlDetail" in h)
    check("ui: تُحفظ مع الرسالة وتعود", "amsg.timeline = wvTlSaved" in h and "wvTlRestore(el, m.timeline)" in h)
    check("ui: لا يُطلب سجلُّ النوبة البطيءُ حين توجد الخطوات",
          "engineTurn && !wvTlSaved" in h)
    check("ui: الخطواتُ لا تُرسل إلى النموذج في السجلّ", "k !== 'timeline'" in h)


if __name__ == "__main__":
    print("live tool steps")
    tmp = tempfile.mkdtemp(prefix="wv-ls-")
    try:
        test_events_of()
        test_web()
        test_tail(tmp)
        test_server_ui()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("FAIL: " + ", ".join(FAILS) if FAILS else "PASS")
    sys.exit(1 if FAILS else 0)
