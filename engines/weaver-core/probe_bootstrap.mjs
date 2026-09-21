// أيُّ ملفّاتِ التمهيد تدخل البرومبتَ فعلاً، وبكم حرفاً؟ — بدوالّ المحرّك.
//
// السؤالُ الذي لم أُجب عنه قبل اليوم: «الدستورُ أين نضعه كي يقرأه النموذج؟»
// وكنتُ سأبني على ظنّ. فهذا يقيس بدل أن يظنّ:
//
//   workspace-YW5Pl2cf.mjs:743  loadWorkspaceBootstrapFiles(dir)
//     ⟵ يحمّل الستّةَ بمحتواها: AGENTS · SOUL · IDENTITY · USER ·
//        BOOTSTRAP · MEMORY  (وUSER وMEMORY يُتخطّيان إن لم يوجدا)
//   bootstrap-DYYMCrXY.mjs:236  buildBootstrapContextFiles(files, opts)
//     ⟵ يقصُّ كلَّ ملفٍّ على ميزانيّته ثمّ يُخرجه {path, content}
//
// والحدودُ من الكود نفسِه:
//   DEFAULT_BOOTSTRAP_MAX_CHARS       = 20000   لكلِّ ملفّ
//   DEFAULT_BOOTSTRAP_TOTAL_MAX_CHARS = 60000   للمجموع
//   USER_BOOTSTRAP_MAX_CHARS          =  4000   لـUSER.md وحده
// وتُضبَط بـagents.defaults.bootstrapMaxChars / bootstrapTotalMaxChars.
//
// يُنادى:  node probe_bootstrap.mjs      ⟶ JSON
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "runtime", "dist");
const io = join(dist, "io.runtime-4x3HMjSp.mjs");
const ws = join(dist, "workspace-CUDoqsXz.mjs");
const bf = join(dist, "bootstrap-files-BAkC4xBB.mjs");
const scope = join(dist, "agent-scope-config-Bh5RAia-.mjs");

const out = { ok: false, workspace: "", files: [], totalChars: 0,
              totalTokens: 0, warnings: [], error: "" };

try {
  const mIo = await import(io);
  const c = await mIo.loadConfig?.({});
  const cfg = c?.config ?? c ?? undefined;

  const mScope = await import(scope);
  out.workspace = String(mScope.m(cfg, "main") || "");

  const mWs = await import(ws);
  const raw = await mWs.loadWorkspaceBootstrapFiles(out.workspace);

  const mBf = await import(bf);
  const ctx = mBf.n(raw, {
    config: cfg, agentId: "main",
    warn: (w) => out.warnings.push(String(w)),
  });

  // الخامُ مقابلَ المحقون: الفرقُ هو القصّ — وهو ما لا يُخبرك به أحد.
  const rawByName = new Map();
  for (const f of raw || []) rawByName.set(String(f?.name || ""), f);
  for (const e of ctx || []) {
    const name = basename(String(e?.path || ""));
    const injected = String(e?.content || "");
    const orig = String(rawByName.get(name)?.content || "");
    out.files.push({
      name,
      onDisk: orig.length,
      injected: injected.length,
      // القصُّ الحقيقيُّ لا السطرُ الأخير: البناءُ يُشذّب المسافاتِ الطرفيّة،
      // فيكون المحقونُ أقصرَ بحرفٍ دائماً. اعتبارُ ذلك قصّاً إنذارٌ كاذب.
      truncated: orig.trim().length > 0
                 && injected.trim().length < orig.trim().length,
      tokens: Math.round(injected.length / 3.6),
      head: injected.slice(0, 70).replace(/\s+/g, " "),
    });
    out.totalChars += injected.length;
  }
  out.totalTokens = Math.round(out.totalChars / 3.6);
  out.ok = out.files.length > 0;
} catch (e) {
  out.error = String(e?.message || e).slice(0, 300);
}
console.log(JSON.stringify(out, null, 2));
