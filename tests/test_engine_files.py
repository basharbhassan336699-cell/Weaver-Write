# -*- coding: utf-8 -*-
"""ملفٌّ كتبه الوكيلُ ⟵ يصل المستخدم: نسخةٌ في «Weaver Write» وبطاقةٌ مع الجواب.

العطبُ المقيس: الوكيلُ كتب مستنداً (٧٣٨٥ بايتاً) في مساحة عمل المحرّك —
~/.weaver-write/state/workspace، مخفيّةٌ داخل Termux — وظهر اسمُه نصّاً في
الجواب ولم يصل المستخدم: لا يراه تطبيقُ الملفّات، والجوابُ بلا output_path،
و/api/output لا يعرض إلا ما في مجلّد الإخراج (قيدُ أمانٍ مقصود، لا يُمَسّ).
"""
import json
import os
import sys
import tempfile
import threading
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "web"))

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


WS = tempfile.mkdtemp()                   # مساحةُ عمل المحرّك
OUT = tempfile.mkdtemp()                  # مجلّدُ «Weaver Write»
for n in ("AGENTS.md", "SOUL.md", "USER.md"):
    open(os.path.join(WS, n), "w").write("داخليّ\n")
os.makedirs(os.path.join(WS, "memory"))
os.makedirs(os.path.join(WS, "skills", "x"))

_real = (W.workspace_dir, S._output_dir, S._engine_ready, S._chat_via_engine)
W.workspace_dir = lambda: WS
S._output_dir = lambda: OUT
S._engine_ready = lambda: True
_writes = {"files": {}}


def _fake_engine(m, h=None, t=120, c=None, mem=None, att=None, session=None):
    """الوكيلُ: يكتب ما في _writes داخل مساحة عمله، ويعدّل ملفّاتٍ داخليّة."""
    for rel, txt in _writes["files"].items():
        p = os.path.join(WS, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(txt)
    open(os.path.join(WS, "SOUL.md"), "a").write("تعديلٌ داخليّ\n")
    open(os.path.join(WS, "memory", "2026-09-24.md"), "w").write("ذاكرة\n")
    open(os.path.join(WS, "skills", "x", "SKILL.md"), "w").write("مهارة\n")
    return {"reply": "تمّ", "engine": "weaver-core", "model": "m"}


S._chat_via_engine = _fake_engine
srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def chat(msg, cid="c1"):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/chat/stream" % port,
        data=json.dumps({"message": msg, "history": [], "chatId": cid}).encode(),
        headers={"Content-Type": "application/json"})
    out = urllib.request.urlopen(req, timeout=60).read().decode()
    return [json.loads(l[6:]) for l in out.splitlines() if l.startswith("data: ")]


try:
    print("\n— ملفٌّ كتبه الوكيل ⟵ يصل —")
    _writes["files"] = {"التعليم-الإلكتروني.md": "# التعليم الإلكتروني\n\nنصّ.\n"}
    ev = chat("اكتب مستنداً")
    rep = next(e for e in ev if e.get("t") == "reply")
    ok("الجوابُ يحمل output_path", bool(rep.get("output_path")), rep)
    ok("  ⟵ في مجلّد «Weaver Write»",
       os.path.dirname(rep.get("output_path", "")) == OUT)
    ok("  ⟵ ومطابقٌ للأصل حرفاً",
       open(rep["output_path"], encoding="utf-8").read()
       == _writes["files"]["التعليم-الإلكتروني.md"])
    ok("  ⟵ والأصلُ باقٍ للوكيل (نسخٌ لا نقل)",
       os.path.isfile(os.path.join(WS, "التعليم-الإلكتروني.md")))
    ok("  ⟵ و/api/output يعرضه (القيدُ نفسُه، بلا توسيع)",
       urllib.request.urlopen(
           "http://127.0.0.1:%d/api/output?path=%s" % (
               port, urllib.request.quote("التعليم-الإلكتروني.md")),
           timeout=30).read().decode().startswith("# التعليم"))
    ok("ملفّاتُ المحرّك الداخليّةُ لم تُنسخ (SOUL · memory · skills)",
       sorted(os.listdir(OUT)) == ["التعليم-الإلكتروني.md"], os.listdir(OUT))
    ok("وبطاقةُ «نوبة الوكيل» ما زالت تُرسَل",
       any(e.get("t") == "tool" and (e.get("tool") or {}).get("kind")
           == "engine" for e in ev))

    print("\n— رسالةٌ بلا ملفّ ⟵ لا بطاقة —")
    _writes["files"] = {}
    ev = chat("شكراً")
    rep = next(e for e in ev if e.get("t") == "reply")
    ok("لا output_path", "output_path" not in rep, rep)
    ok("ولا نسخةَ جديدة", sorted(os.listdir(OUT)) == ["التعليم-الإلكتروني.md"])

    print("\n— ملفّان في نوبةٍ واحدة ⟵ بطاقتان —")
    _writes["files"] = {"أ.md": "أ\n", "تقارير/ب.csv": "x,y\n1,2\n"}
    ev = chat("اكتب ملفّين")
    rep = next(e for e in ev if e.get("t") == "reply")
    extra = [e for e in ev if e.get("t") == "file"]
    ok("الأوّلُ مع الجواب والثاني حدثُ file",
       rep.get("output_path") and len(extra) == 1, (rep, extra))
    ok("  ⟵ والملفُّ في مجلّدٍ فرعيٍّ يُلتقط أيضاً",
       os.path.isfile(os.path.join(OUT, "ب.csv")))

    print("\n— لا يُدهَس ملفٌّ للمستخدم —")
    open(os.path.join(OUT, "تقرير.md"), "w", encoding="utf-8").write("ملفّي أنا\n")
    _writes["files"] = {"تقرير.md": "من الوكيل\n"}
    ev = chat("اكتب تقريراً")
    rep = next(e for e in ev if e.get("t") == "reply")
    ok("اسمٌ مأخوذٌ بمحتوىً مختلف ⟵ «تقرير-2.md»",
       os.path.basename(rep.get("output_path", "")) == "تقرير-2.md", rep)
    ok("  ⟵ وملفُّ المستخدم كما هو",
       open(os.path.join(OUT, "تقرير.md"), encoding="utf-8").read()
       == "ملفّي أنا\n")
    _writes["files"] = {"أ.md": "أ\n"}
    os.utime(os.path.join(WS, "أ.md"), (1, 1))     # يُعَدّ «متغيّراً»
    ev = chat("أعِد")
    rep = next(e for e in ev if e.get("t") == "reply")
    ok("نسخةٌ مطابقةٌ سلفاً ⟵ لا تتكرّر",
       os.path.basename(rep.get("output_path", "")) == "أ.md"
       and not os.path.exists(os.path.join(OUT, "أ-2.md")), rep)

    print("\n— المحرّكُ عجز ⟵ لا شيء يُنسخ —")
    S._chat_via_engine = lambda *a, **k: None
    S._chat_direct = lambda *a, **k: {"reply": "مباشر"}
    ev = chat("سؤال")
    rep = next(e for e in ev if e.get("t") == "reply")
    ok("المسارُ المباشر: بلا output_path", "output_path" not in rep, rep)
finally:
    srv.shutdown()
    (W.workspace_dir, S._output_dir, S._engine_ready,
     S._chat_via_engine) = _real

print("\n— الصفحة —")
_h = open(os.path.join(_ROOT, "web", "index.html"), encoding="utf-8").read()
ok("حدثُ file ⟵ بطاقة", "ev.t === 'file'" in _h and "extraFiles.push" in _h)
ok("وتُحفظ الملفّاتُ الإضافيّة", "amsg.files = extraFiles.slice()" in _h)
ok("وتُعاد عند فتح المحادثة", "m.files.forEach(function (f) { addFileCard(el, f)"
   in _h)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
