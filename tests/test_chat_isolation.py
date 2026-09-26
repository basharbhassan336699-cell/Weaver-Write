# -*- coding: utf-8 -*-
"""عزلُ المحادثات: محادثتان في اللحظة نفسِها لا تتداخل ملفّاتُهما.

كانت كلُّ المحادثات تكتب في مجلّدٍ واحد، والواجهةُ تعرف «الملفَّ الجديد»
بلقطةٍ للمجلّد قبل الرسالة وبعدها — فملفُّ محادثةٍ يظهر بطاقةً في أخرى
إن تزامنتا، ومسوّدةُ مهارةٍ (plagiarism-check.txt) تُكتب فوق أختها.

الآن: لكلِّ محادثةٍ مجلّد chats/<رقمها>/ يُذكر للنموذج في كلِّ رسالة، والواجهةُ
لا ترى من مجلّدات المحادثات إلا مجلّدَ المحادثة نفسِها. وملفٌّ كُتب خارجه:
بلا تزامنٍ ⟵ كما كان حرفاً؛ ومع تزامنٍ ⟵ لمن ذكر جوابُه اسمَه فقط.
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


WS = tempfile.mkdtemp()
OUT = tempfile.mkdtemp()
_real = {"ws": W.workspace_dir, "out": S._output_dir,
         "ready": S._engine_ready, "eng": S._chat_via_engine}
W.workspace_dir = lambda: WS
S._output_dir = lambda: OUT
S._engine_ready = lambda: True

print("\n— اسمُ المجلّد —")
ok("رقمُ المحادثة ⟵ chats/<رقمها>",
   S._chat_dir_rel("c1790371259856ep19s") == "chats/c1790371259856ep19s")
ok("رموزٌ خطرة تُنظَّف (لا خروجَ من المجلّد)",
   S._chat_dir_rel("../../etc") == "chats/------etc"
   and "/" not in S._chat_dir_rel("a/b")[len("chats/"):])
ok("بلا رقم ⟵ \"\"", S._chat_dir_rel("") == "" and S._chat_dir_rel(None) == "")

print("\n— السطرُ الذي يصل النموذج —")
_seen = {}
_rw = {n: getattr(W, n) for n in ("available", "node_bin", "ask")}
W.available = lambda: True
W.node_bin = lambda: "node"
W.ask = lambda text, **k: (_seen.update(text=text, session=k.get("session"))
                           or {"answer": "تمّ"})
try:
    S._chat_via_engine("اكتب مستنداً", session="chatA")
    ok("«[مجلّد العمل]» ومعه chats/chatA/",
       "[مجلّد العمل]\nchats/chatA/" in _seen.get("text", ""),
       _seen.get("text", "")[-300:])
    ok("  ⟵ قبل الطلب", _seen["text"].index("[مجلّد العمل]")
       < _seen["text"].index("[الطلب]"))
    ok("  ⟵ والمجلّدُ أُنشئ", os.path.isdir(os.path.join(WS, "chats", "chatA")))
    S._chat_via_engine("سؤال", session=None)
    ok("بلا محادثة ⟵ لا سطر (كما كان)", "[مجلّد العمل]" not in _seen["text"])
    # قِيس على الهاتف: كتب بالإنجليزيّة فردّ بالعربيّة — الغلافُ كان عربيّاً.
    S._chat_via_engine("Search the news and save it in news.md",
                       session="chatE", memory="الاسم: MBH")
    _tx = _seen["text"]
    ok("رسالةٌ إنجليزيّة ⟵ غلافٌ إنجليزيّ ([Request] · [Memory])",
       "[Request]\nSearch the news" in _tx and "[Memory]" in _tx
       and "[الطلب]" not in _tx and "[ذاكرة]" not in _tx, _tx[-300:])
    ok("  ⟵ وسطرُ المجلّد بالإنجليزيّة مع اسمه الذي تُحيل إليه المهارات",
       "[Working folder / مجلّد العمل]\nchats/chatE/ — write every file" in _tx)
    S._chat_via_engine("اكتب", session="chatA", memory="x")
    ok("رسالةٌ عربيّة ⟵ الغلافُ كما كان حرفاً",
       "[ذاكرة]\nx" in _seen["text"] and "[الطلب]\nاكتب" in _seen["text"])
finally:
    for n, f in _rw.items():
        setattr(W, n, f)

# ── الوكيلُ المزيَّف: يكتب ما يُطلب، وينتظر أختَه لتتزامنا فعلاً ──
_plan = {}
_bar = {"b": None}


def _fake_engine(m, h=None, t=120, c=None, mem=None, att=None, session=None):
    job = _plan.get(session) or {}
    if _bar["b"] is not None:
        _bar["b"].wait(timeout=20)         # النوبتان داخل الدور معاً
    for rel, txt in (job.get("files") or {}).items():
        p = os.path.join(WS, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(txt)
    if _bar["b"] is not None:
        _bar["b"].wait(timeout=20)         # ولا تنتهي إحداهما قبل كتابة الأخرى
    return {"reply": job.get("reply", "تمّ"), "engine": "weaver-core",
            "model": "m"}


S._chat_via_engine = _fake_engine
srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def chat(msg, cid):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/chat/stream" % port,
        data=json.dumps({"message": msg, "history": [], "chatId": cid}).encode(),
        headers={"Content-Type": "application/json"})
    out = urllib.request.urlopen(req, timeout=60).read().decode()
    return [json.loads(ln[6:]) for ln in out.splitlines()
            if ln.startswith("data: ")]


def files_of(ev):
    names = []
    for e in ev:
        if e.get("t") == "reply" and e.get("output_path"):
            names.append(os.path.basename(e["output_path"]))
        if e.get("t") == "file" and e.get("path"):
            names.append(os.path.basename(e["path"]))
    return sorted(names)


def together(a, b):
    res = {}
    _bar["b"] = threading.Barrier(2)
    ts = [threading.Thread(target=lambda k=k, m=m: res.__setitem__(k, chat(m, k)))
          for k, m in ((a, "طلب " + a), (b, "طلب " + b))]
    for x in ts:
        x.start()
    for x in ts:
        x.join(60)
    _bar["b"] = None
    return res


try:
    print("\n— محادثتان معاً، كلٌّ في مجلّدها —")
    _plan.clear()
    _plan["A"] = {"files": {"chats/A/تقرير-أ.md": "أ\n",
                            "chats/A/plagiarism-check.txt": "مسوّدة أ"}}
    _plan["B"] = {"files": {"chats/B/تقرير-ب.md": "ب\n",
                            "chats/B/plagiarism-check.txt": "مسوّدة ب"}}
    r = together("A", "B")
    ok("أ تأخذ ملفَّها وحدَه", files_of(r["A"]) == ["تقرير-أ.md"],
       files_of(r["A"]))
    ok("ب تأخذ ملفَّها وحدَه", files_of(r["B"]) == ["تقرير-ب.md"],
       files_of(r["B"]))
    ok("مسوّدتا فحص النقل منفصلتان (لا كتابةَ فوق الأخرى)",
       open(os.path.join(WS, "chats/A/plagiarism-check.txt"),
            encoding="utf-8").read() == "مسوّدة أ"
       and open(os.path.join(WS, "chats/B/plagiarism-check.txt"),
                encoding="utf-8").read() == "مسوّدة ب")
    ok("  ⟵ ولا تُسلَّم مسوّدةٌ بطاقةً", "plagiarism-check.txt"
       not in files_of(r["A"]) + files_of(r["B"]))

    print("\n— معاً، والنموذجُ كتب في الجذر رغم التوجيه —")
    _plan.clear()
    _plan["C"] = {"files": {"جذر-ج.md": "ج\n"},
                  "reply": "حفظتُ المستندَ في ملفّ جذر-ج.md"}
    _plan["D"] = {"files": {}, "reply": "هذا جوابٌ بلا ملفّ"}
    r = together("C", "D")
    ok("ج ذكر اسمَه في جوابه ⟵ لها", files_of(r["C"]) == ["جذر-ج.md"],
       files_of(r["C"]))
    ok("د لم تذكره ⟵ لا يُنسب إليها", files_of(r["D"]) == [],
       files_of(r["D"]))

    print("\n— وحدَها (بلا تزامن) — كما كان حرفاً —")
    _plan.clear()
    _plan["E"] = {"files": {"جذر-ه.md": "ه\n"}, "reply": "تمّ"}
    ok("ملفٌّ في الجذر لم يُذكر اسمُه ⟵ يُسلَّم كما كان",
       files_of(chat("طلب", "E")) == ["جذر-ه.md"])
    _plan["F"] = {"files": {"chats/F/وثيقة.md": "و\n"}}
    ok("وفي مجلّدها ⟵ يُسلَّم", files_of(chat("طلب", "F")) == ["وثيقة.md"])
    _plan["G"] = {"files": {"chats/F/متأخّر.md": "x\n"}, "reply": "متأخّر.md"}
    ok("ملفٌّ في مجلّد محادثةٍ أخرى ⟵ لا يُرى أبداً، ولو ذُكر اسمُه",
       files_of(chat("طلب", "G")) == [])

    print("\n— حارسُ الخادم: لا يتجاوز الحدَّ ولو من تبويبين —")
    os.environ["WEAVER_PARALLEL_CHATS"] = "1"
    _rl = S.keysync.reload_env
    S.keysync.reload_env = lambda: {}          # لا يُقرأ config/.env الحقيقيّ
    _plan.clear()
    _plan["H"] = {"reply": "ردُّ ح"}
    _busy = S._turn_begin()                   # محادثةٌ أخرى تعمل الآن
    try:
        ev = chat("طلب", "H")
        rep = next((e.get("reply") for e in ev if e.get("t") == "reply"), "")
        ok("الحدُّ ١ ومحادثةٌ تعمل ⟵ تنبيهٌ لا تشغيل", "تعمل الآن 1" in rep
           and "ردُّ ح" not in rep, rep)
    finally:
        S._turn_end(_busy)
    ev = chat("طلب", "H")
    ok("وحين تنتهي ⟵ تعمل", any(e.get("reply") == "ردُّ ح" for e in ev))
    os.environ["WEAVER_PARALLEL_CHATS"] = "9"
    ok("قيمةٌ خارج ١–٥ ⟵ الافتراضيُّ ٢", S.parallel_limit() == 2)
    os.environ.pop("WEAVER_PARALLEL_CHATS", None)
    ok("بلا ضبط ⟵ ٢", S.parallel_limit() == 2)
    S.keysync.reload_env = _rl

    print("\n— حالةُ النوبات —")
    ok("لا نوبةَ عالقة بعد الانتهاء", S._TURNS_ACTIVE == {}, S._TURNS_ACTIVE)
    t1 = S._turn_begin()
    t2 = S._turn_begin()
    ok("نوبتان متداخلتان ⟵ كلتاهما تعلم",
       S._turn_end(t1) is True and S._turn_end(t2) is True)
    t3 = S._turn_begin()
    ok("نوبةٌ وحدَها ⟵ لا تداخل", S._turn_end(t3) is False)
finally:
    srv.shutdown()
    W.workspace_dir = _real["ws"]
    S._output_dir = _real["out"]
    S._engine_ready = _real["ready"]
    S._chat_via_engine = _real["eng"]

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
