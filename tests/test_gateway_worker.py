# -*- coding: utf-8 -*-
"""العمليةُ المقيمة (engines/weaver-core/gateway_worker.mjs) — وعودةُ السطر عند عجزها.

قِيس على المحرّك الحقيقيّ والبوّابة مع نموذجٍ مزيَّف (٢٠ ث لكلِّ رد)، خمسُ
محادثاتٍ معاً:
    السطرُ لكلِّ رد:     ذروةُ الذاكرة 2304 MB · عمليّاتُ node: البوّابة + ٥
    العمليةُ المقيمة:    ذروةُ الذاكرة  882 MB · البوّابة + ١
    والردودُ الخمسةُ صحيحةٌ ولكلٍّ محادثتُه في الحالتين.
وهاتفُ المستخدم كان فيه 1.2 GB متاحة — فقتل أندرويد Termux.

هنا: العمليةُ المقيمة بمحرّكٍ مزيَّف (تُحمَّل دالّةٌ باسم agentCliCommand من
dist/agent-via-gateway-*.mjs كما في المحرّك)، والتزامنُ داخلها، وأخطاؤها؛
ثمّ ask(): تستعملها حين تعمل، وتعود إلى السطر كما كان حين لا تعمل.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from pipeline import weaver_core as W   # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


NODE = os.environ.get("WEAVER_NODE") or shutil.which("node") or ""
for _c in sorted(glob.glob("/opt/node*/bin/node")):
    NODE = NODE or _c
WORKER = W.WORKER_JS

FAKE = r"""
export async function agentCliCommand(opts, runtime) {
  if (opts.message.includes("THROW")) throw new Error("gateway said no");
  if (opts.message.includes("EXIT")) { runtime.error("bad option"); runtime.exit(1); }
  await new Promise(r => setTimeout(r, 1500));
  const v = { ok: true, status: "ok", final: "echo:" + opts.message + ":" + (opts.sessionId || ""),
              payloads: [{ text: "echo:" + opts.message }] };
  if (opts.json) runtime.writeJson(v); else runtime.log(v.final);
  return v;
}
"""


def start_worker(root):
    p = subprocess.Popen([NODE, WORKER, root], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    line = p.stdout.readline().strip()
    return p, line


def post(port, body, timeout=30):
    rq = urllib.request.Request("http://127.0.0.1:%d/agent" % port,
                                data=json.dumps(body).encode(),
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(rq, timeout=timeout) as r:
        return json.loads(r.read().decode())


if not NODE:
    print("node غيرُ موجود — اختبارُ العملية المقيمة تُخطّي")
else:
    print("\n— العمليةُ المقيمة بمحرّكٍ مزيَّف —")
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "dist"))
    open(os.path.join(root, "dist", "agent-via-gateway-Xyz.mjs"), "w").write(FAKE)
    os.environ.setdefault("NO_PROXY", "127.0.0.1")
    p, line = start_worker(root)
    try:
        ok("تُقلع وتطبع READY <منفذ>", line.startswith("READY "), line)
        port = int(line.split()[1])
        h = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:%d/health" % port, timeout=10).read())
        ok("/health", h.get("ok") is True and h.get("running") == 0, h)
        r = post(port, {"message": "مرحبا", "sessionId": "weaver-a",
                        "timeout": "600"})
        ok("نوبة ⟵ JSON المحرّك نفسُه (--json)", r.get("ok") and
           r["json"]["final"] == "echo:مرحبا:weaver-a", r)
        res, t0 = {}, time.time()

        def one(i):
            res[i] = post(port, {"message": "m%d" % i, "sessionId": "s%d" % i})
        ts = [threading.Thread(target=one, args=(i,)) for i in range(5)]
        [x.start() for x in ts]
        [x.join(30) for x in ts]
        dt = time.time() - t0
        ok("خمسُ نوباتٍ معاً داخل عمليةٍ واحدة (لا بالتتابع)", dt < 4.5,
           "%.1fs" % dt)
        ok("  ⟵ ولكلٍّ ردُّه وجلستُه", all(
            res[i]["json"]["final"] == "echo:m%d:s%d" % (i, i)
            for i in range(5)), res)
        r = post(port, {"message": "THROW"})
        ok("خطأٌ من المحرّك ⟵ ok:false بالسبب، والعمليةُ باقية",
           r.get("ok") is False and "gateway said no" in r.get("error", "")
           and p.poll() is None, r)
        r = post(port, {"message": "EXIT"})
        ok("runtime.exit ⟵ لا تخرج العمليةُ المقيمة", r.get("ok") is False
           and "bad option" in r.get("error", "") and p.poll() is None, r)
        try:
            post(port, {})
            bad = False
        except urllib.error.HTTPError as e:
            bad = e.code == 400
        ok("طلبٌ بلا رسالة ⟵ 400", bad)
    finally:
        p.terminate()
    empty = tempfile.mkdtemp()
    os.makedirs(os.path.join(empty, "dist"))
    p2, line2 = start_worker(empty)
    ok("محرّكٌ بلا الدالّة ⟵ FAIL ولا تبقى", line2.startswith("FAIL")
       and p2.wait(10) == 3, line2)

print("\n— ask(): العمليةُ المقيمة أوّلاً، والسطرُ عند عجزها —")
_real = {n: getattr(W, n) for n in (
    "available", "node_bin", "gateway_on", "gateway_start", "run",
    "_worker_agent", "model_id", "worker_on")}
_calls = {"run": 0, "worker": []}
try:
    W.available = lambda: True
    W.node_bin = lambda: "node"
    W.gateway_on = lambda: True
    W.gateway_start = lambda *a, **k: (True, "")
    W.model_id = lambda: "weaver/m"
    W.worker_on = lambda: True

    def _run(args, timeout=180, input_text=None, cwd=None):
        _calls["run"] += 1
        return 0, json.dumps({"ok": True, "final": "من السطر"}), ""
    W.run = _run

    def _wa(req, timeout):
        _calls["worker"].append(req)
        return 0, json.dumps({"ok": True, "final": "من المقيمة"}), ""
    W._worker_agent = _wa
    r = W.ask("سؤال", fallback=False, session="chat-7")
    ok("تعمل ⟵ الجوابُ منها، ولا عمليةَ سطرٍ جديدة",
       r["answer"] == "من المقيمة" and _calls["run"] == 0, (r, _calls))
    req = _calls["worker"][-1]
    ok("  ⟵ بالجلسة والمهلة والنموذج نفسِها", req["sessionId"]
       == W._session_id("chat-7") and req["model"] == "weaver/m"
       and req["timeout"], req)

    W._worker_agent = lambda req, timeout: None
    r = W.ask("سؤال", fallback=False, session="chat-7")
    ok("لم تصلها النوبة (None) ⟵ السطرُ كما كان", r["answer"] == "من السطر"
       and _calls["run"] == 1)

    _calls["run"] = 0
    W._worker_agent = lambda req, timeout: (1, "", "auth failed")
    r = W.ask("سؤال", fallback=False, session="chat-7")
    ok("وصلتها وفشلت ⟵ لا تُعاد بالسطر (لا تُنفَّذ مرّتين)",
       _calls["run"] == 0 and "auth failed" in r["note"], r)

    W.worker_on = lambda: False
    W._worker_agent = lambda req, timeout: (_ for _ in ()).throw(
        AssertionError("لا تُستدعى"))
    r = W.ask("سؤال", fallback=False, session="chat-7")
    ok("WEAVER_GATEWAY_WORKER=off ⟵ السطرُ وحدَه", r["answer"] == "من السطر")
finally:
    for n, f in _real.items():
        setattr(W, n, f)

print("\n— لا تُوقَف عمليةٌ حيّةٌ لأنّها بطيئة (قِيس: 143 على الهاتف) —")
class _FakeProc:
    def __init__(self):
        self.killed = False
    def poll(self):
        return None
    def terminate(self):
        self.killed = True
_fp = _FakeProc()
_rh, _ra = W._worker_health, W.available
W._WORKER.update(proc=_fp, port=45678, failed_at=0.0)
W._worker_health = lambda port, timeout=3: False      # مشغولةٌ لا تردّ بسرعة
W.available = lambda: True
try:
    ok("حيّةٌ وبطيئة ⟵ يُستعمل منفذُها ولا تُوقَف",
       W.worker_port() == 45678 and not _fp.killed)
    W._worker_refused(45678)
    ok("رفضت الاتّصال ⟵ تُنسى وتُوقَف (لا نوبةَ فيها)", _fp.killed
       and W._WORKER["proc"] is None and W._WORKER["port"] is None)
    _fp2 = _FakeProc()
    W._WORKER.update(proc=_fp2, port=11111)
    W._worker_refused(45678)
    ok("رفضٌ من منفذٍ قديم ⟵ لا يمسّ العمليةَ الحاليّة", not _fp2.killed
       and W._WORKER["port"] == 11111)
finally:
    W._worker_health, W.available = _rh, _ra
    W._WORKER.update(proc=None, port=None, failed_at=0.0)
src = open(os.path.join(_ROOT, "pipeline", "weaver_core.py"),
           encoding="utf-8").read()
_wp = src[src.index("def worker_port"):src.index("def worker_stop")]
ok("worker_port لا تُوقف عمليةً حيّة", "terminate" not in
   _wp.split("_WORKER[\"proc\"] = _WORKER[\"port\"] = None")[0])

print("\n— _worker_agent: ما لم يصل لا يُحسب فشلاً —")
_rp = W.worker_port
try:
    W.worker_port = lambda: None
    ok("لا عملية ⟵ None", W._worker_agent({"message": "x"}, 5) is None)
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    dead = s.getsockname()[1]
    s.close()
    W.worker_port = lambda: dead
    ok("منفذٌ مغلق (رُفض الاتّصال) ⟵ None", W._worker_agent(
        {"message": "x"}, 5) is None)
finally:
    W.worker_port = _rp
ok("الإطفاءُ بالبيئة", (os.environ.update(WEAVER_GATEWAY_WORKER="off")
                        or not W.worker_on()))
os.environ.pop("WEAVER_GATEWAY_WORKER", None)
ok("ومشغّلةٌ افتراضياً", W.worker_on())

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
