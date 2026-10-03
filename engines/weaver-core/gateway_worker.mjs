// gateway_worker.mjs — عمليةٌ واحدةٌ مقيمة تُرسل نوباتِ كلِّ المحادثات إلى البوّابة.
//
// كان كلُّ ردٍّ يُقلع عمليةَ node كاملة (`openclaw agent -m …`) بجانب البوّابة.
// قِيس على هاتف المستخدم (Android 15، ذاكرةٌ 3.7 GB): خمسُ محادثاتٍ معاً ⟵
// خمسُ عمليّاتٍ ⟵ نفدت الذاكرةُ فقتل أندرويد Termux كلَّه. والإقلاعُ وحدَه
// عشراتُ الثواني في كلِّ رسالة.
//
// هذه العمليةُ تُقلع مرّةً، وتحمّل دالّةَ المحرّك نفسَها التي يستعملها سطرُ
// أوامره (`agentCliCommand` في dist/agent-via-gateway-*.mjs) — فالبروتوكولُ
// والمصادقةُ وهويّةُ الجهاز كلُّها كودُه هو، لا نسخةٌ منّا. ثمّ تخدم كلَّ نوبةٍ
// بطلب HTTP محلّيّ، والنوباتُ المتزامنةُ تجري داخلها معاً.
//
//     node gateway_worker.mjs <مجلّد المحرّك>
//     ⟵ تطبع سطراً واحداً: READY <منفذ>   (أو FAIL <سبب> وتخرج)
//
//     POST /agent  {"message","sessionId","timeout","model"}
//          ⟵ {"ok":true,"json":<ما يطبعه `agent --json` حرفاً>}
//          ⟵ {"ok":false,"error":"…"}
//     GET  /health ⟵ {"ok":true,"running":<نوباتٌ جارية>}
//     POST /abort  {"sessionId"} ⟵ {"ok":true,"aborted":<عددُ النوبات>}
//          زرُّ «إيقاف» في الواجهة: يُوقف نوبةَ تلك المحادثة وحدها بطريق
//          المحرّك نفسِه — كأنّ المستخدمَ ضغط Ctrl+C على `agent` (يُرسل
//          chat.abort إلى البوّابة ثمّ يخرج بـ130). وغيرُها من النوبات لا يُمسّ.
//
// لا تستمع إلا على 127.0.0.1. وأيُّ عجزٍ في التحميل ⟵ FAIL، فيعود بايثون إلى
// سطر الأوامر كما كان حرفاً.
import http from "node:http";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = path.resolve(process.argv[2] || ".");
const dist = path.join(root, "dist");

function fail(why) {
  process.stdout.write("FAIL " + String(why).replace(/\s+/g, " ").slice(0, 300) + "\n");
  process.exit(3);
}

let agentCliCommand;
try {
  const hits = fs.readdirSync(dist).filter((f) => /^agent-via-gateway-.*\.mjs$/.test(f));
  if (hits.length !== 1) fail("agent-via-gateway module: " + hits.length + " matches");
  const mod = await import(pathToFileURL(path.join(dist, hits[0])).href);
  agentCliCommand = mod.agentCliCommand;
  if (typeof agentCliCommand !== "function") fail("agentCliCommand is not exported");
} catch (e) {
  fail((e && e.message) || e);
}

class WorkerExit extends Error {
  constructor(code) { super("exit " + code); this.code = code; }
}

// مخرجاتٌ لكلِّ نوبةٍ على حدة — لا يختلط ما تكتبه نوبتان متزامنتان.
function captureRuntime() {
  const cap = { json: undefined, logs: [], errors: [] };
  const rt = {
    log: (...a) => { cap.logs.push(a.map(String).join(" ")); },
    error: (...a) => { cap.errors.push(a.map(String).join(" ")); },
    writeStdout: (v) => { cap.logs.push(String(v)); },
    writeJson: (v) => { cap.json = v; },
    exit: (code) => { throw new WorkerExit(code); },
  };
  return { rt, cap };
}

let running = 0;

// «عمليةٌ» لكلِّ نوبة: المحرّكُ يقبلها بدل process (`deps.process` ⟵
// resolveAgentCliProcessLike في agent-via-gateway) ويستمع فيها لـSIGINT/SIGTERM.
// فإشارةٌ عليها تُوقف تلك النوبةَ وحدها. وإشاراتُ العملية الحقيقيّة تُمرَّر
// إليها كما كانت تصلها مباشرةً قبل هذا — فلا يتغيّر سلوكُ الإيقاف الكامل.
const SIGNALS = ["SIGINT", "SIGTERM"];
const inflight = new Set(); // {sessionId, proc}

function turnProcess(sessionId) {
  const proc = new EventEmitter();
  proc.exitCode = undefined;
  const fwd = SIGNALS.map((sig) => [sig, () => proc.emit(sig)]);
  for (const [sig, h] of fwd) process.on(sig, h);
  const entry = { sessionId, proc };
  inflight.add(entry);
  entry.dispose = () => {
    for (const [sig, h] of fwd) process.off(sig, h);
    inflight.delete(entry);
  };
  return entry;
}

function abortSession(sessionId) {
  let n = 0;
  for (const e of [...inflight]) {
    if (sessionId && e.sessionId === sessionId) {
      e.proc.emit("SIGINT");
      n += 1;
    }
  }
  return n;
}

async function runTurn(req) {
  const opts = { message: String(req.message || ""), json: true };
  if (req.sessionId) opts.sessionId = String(req.sessionId);
  if (req.timeout) opts.timeout = String(req.timeout);
  if (req.model) opts.model = String(req.model);
  const { rt, cap } = captureRuntime();
  const turn = turnProcess(opts.sessionId || "");
  running += 1;
  try {
    const response = await agentCliCommand(opts, rt, { process: turn.proc });
    const json = cap.json !== undefined ? cap.json : response;
    if (json === undefined || json === null) {
      return { ok: false, error: cap.errors.join("\n") || "no response from agent" };
    }
    return { ok: true, json };
  } catch (e) {
    const msg = e instanceof WorkerExit
      ? (cap.errors.join("\n") || "agent exited with code " + e.code)
      : ((e && (e.stack || e.message)) || String(e));
    return { ok: false, error: String(msg).slice(0, 4000) };
  } finally {
    running -= 1;
    turn.dispose();
  }
}

function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { "Content-Type": "application/json; charset=utf-8",
                        "Content-Length": Buffer.byteLength(body) });
  res.end(body);
}

const server = http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    return send(res, 200, { ok: true, running });
  }
  if (req.method === "POST" && req.url === "/agent") {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", async () => {
      let body;
      try { body = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}"); }
      catch { return send(res, 400, { ok: false, error: "bad json" }); }
      if (!body.message) return send(res, 400, { ok: false, error: "missing message" });
      send(res, 200, await runTurn(body));
    });
    return;
  }
  if (req.method === "POST" && req.url === "/abort") {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      let body;
      try { body = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}"); }
      catch { return send(res, 400, { ok: false, error: "bad json" }); }
      send(res, 200, { ok: true, aborted: abortSession(String(body.sessionId || "")) });
    });
    return;
  }
  send(res, 404, { ok: false, error: "not found" });
});
// نوبةٌ قد تطول دقائق (مهلةُ المحرّك ٦٠٠ ث) — فلا يقطعها الخادم.
server.requestTimeout = 0;
server.headersTimeout = 0;
server.keepAliveTimeout = 5000;
server.listen(0, "127.0.0.1", () => {
  process.stdout.write("READY " + server.address().port + "\n");
});
process.on("unhandledRejection", () => {});
