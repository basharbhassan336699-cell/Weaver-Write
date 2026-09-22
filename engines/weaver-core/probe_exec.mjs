// أيستطيع النموذجُ تشغيلَ سكربتِ القاموس فعلاً؟ — بأداة `exec` الحقيقيّة.
//
// المهارةُ تُملي على النموذج أمراً، والأمرُ يُنفَّذ بأداةِ المحرّك لا بصدفتنا.
// وبين الاثنين أسئلةٌ لا تُجاب بالظنّ: أمسموحٌ مسارٌ خارج مساحة العمل؟
// أيمنع صندوقٌ رمليّ؟ أيوجد `python3` أصلاً في بيئة المحرّك؟
//
// فهذا يبني الأداةَ نفسَها (`createOpenClawCodingTools`) وينفّذ بها الأمرَ
// الذي كُتب في `SKILL.md` حرفاً، ويُخرج ما تراه الأداة.
//
// يُنادى:  node probe_exec.mjs "<الأمر>"      ⟶ JSON
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";

const cmd = process.argv[2] || "";
const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "runtime", "dist");

const out = { ok: false, found: false, exitCode: null, cwd: "",
              text: "", error: "" };
try {
  let cfg;
  try {
    const m = await import(join(dist, "io.runtime-4x3HMjSp.mjs"));
    const c = await m.loadConfig?.({});
    cfg = c?.config ?? c;
  } catch { /* إعدادٌ افتراضيّ */ }

  const mScope = await import(join(dist, "agent-scope-config-Bh5RAia-.mjs"));
  const ws = mScope.m(cfg, "main") || homedir();
  const ad = mScope.u ? (mScope.u(cfg, "main") || "") : "";

  const m = await import(join(dist, "agent-tools-CNTtT1Sj.mjs"));
  const tools = m.createOpenClawCodingTools({
    config: cfg, agentId: "main",
    workspaceDir: ws, agentDir: ad || undefined,
    modelProvider: process.env.WEAVER_PROBE_PROVIDER || undefined,
    modelId: process.env.WEAVER_PROBE_MODEL || undefined,
    modelApi: "openai-completions",
  });
  const exec = (tools || []).find((t) => t && t.name === "exec");
  out.found = !!exec;
  if (!exec) throw new Error("أداةُ exec غيرُ متاحةٍ للنموذج — راجع --tools");
  if (!cmd) throw new Error("لا أمرَ لتنفيذه");

  const r = await exec.execute("weaver-probe", { command: cmd }, undefined);
  const d = r?.details || {};
  out.exitCode = typeof d.exitCode === "number" ? d.exitCode : null;
  out.cwd = String(d.cwd || "");
  out.text = String(d.aggregated
    ?? (r?.content || []).map((c) => c?.text || "").join("\n")).slice(0, 4000);
  out.ok = out.exitCode === 0;
} catch (e) {
  out.error = String(e?.message || e).slice(0, 400);
}
console.log(JSON.stringify(out, null, 2));
