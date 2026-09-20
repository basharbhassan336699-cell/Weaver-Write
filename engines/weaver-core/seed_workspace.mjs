// بذرُ ملفّات تمهيد مساحة العمل — بقوالب المحرّك نفسِه ومساراتِه نفسِها.
//
// العطبُ المقيس على جهاز المستخدم (Termux/Android)، وهو الذي كان يقتل كلَّ
// نوبةٍ قبل أن يُنادى النموذجُ أصلاً:
//
//   EACCES: permission denied, link
//     '…/state/workspace/openclaw-bootstrap-IWLWOR/AGENTS.md'
//     -> '…/state/workspace/AGENTS.md'
//
// وموضعُه من كود المحرّك:
//
//   workspace-YW5Pl2cf.mjs:224  publishBootstrapFile(filePath, content, …)
//   :227   const existing = await fs.lstat(targetPath).catch(…)
//   :231   if (existing) return false;           ⟵ الملفُّ موجودٌ ⟶ لا رابطَ أصلاً
//   :233   const staging = await tempFile({ prefix: "openclaw-bootstrap", … })
//   :250   fs.linkSync(staging.path, targetPath)  ⟵ هنا يقع EACCES
//   :255   else if (isHardlinkFallbackError(error)) …
//   :261   else outcome = { kind: "failed", error }   ⟵ فيُرمى خاماً
//
// ولماذا لا يتدارك المحرّكُ؟ لأنّ مصنّفَه لا يعدُّ EACCES من أخطاء السقوط:
//
//   node_modules/@openclaw/fs-safe/dist/publish-file.js:14
//     const HARDLINK_FALLBACK_CODES = new Set([
//       "EPERM", "EXDEV", "ENOTSUP", "EOPNOTSUPP", "ENOSYS" ])
//   :29  isHardlinkFallbackError = (e) => HARDLINK_FALLBACK_CODES.has(e?.code)
//
// وأندرويد يردّ EACCES على link()، لا EPERM. فلا نسخةَ احتياطيّة، ويسقط
// التمهيدُ كلُّه — ومعه النوبة.
//
// والعلاجُ من معماريّة المحرّك لا من عندنا: السطرُ 231 نفسُه. «الموجودُ لا
// يُنشر»، فيكفي أن تكون الملفّاتُ موجودةً قبلَه فلا يُنادى `linkSync` أبداً.
// وتُكتب بقوالبه هو، من مجلّداتِه هو، بعد نزعِ الواجهةِ كما ينزعها هو:
//
//   :36   resolveWorkspaceTemplateSearchDirs  ⟶ <جذرُ الحزمة>/docs/reference/templates
//   :168  stripFrontMatter(c) = extractFrontmatterBlock(c)?.body.replace(/^\s+/,"") ?? c
//   :171  loadTemplate(name)  ⟶ يقرأ أوّلَ قالبٍ يجده ثمّ ينزع الواجهة
//
// فالمحتوى مطابقٌ بايتاً لما كان المحرّكُ سيكتبه، والفرقُ الوحيد: `write`
// بدل `link`. ولا يُمَسّ ملفٌّ موجود (العَلَم "wx").
//
// يُنادى:  node seed_workspace.mjs [--force]      ⟶ JSON
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { writeFileSync, existsSync, mkdirSync } from "node:fs";
import { readFile } from "node:fs/promises";

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "runtime", "dist");
const io = join(dist, "io.runtime-4x3HMjSp.mjs");
const ws = join(dist, "workspace-YW5Pl2cf.mjs");
const scope = join(dist, "agent-scope-config-Bh5RAia-.mjs");
const fm = join(dist, "frontmatter-DniWUaAk.mjs");

const out = { ok: false, workspace: "", templateDirs: [], files: [],
              created: 0, existed: 0, error: "" };

try {
  const mIo = await import(io);
  const c = await mIo.loadConfig?.({});
  const cfg = c?.config ?? c ?? undefined;

  const mScope = await import(scope);
  const mWs = await import(ws);
  const mFm = await import(fm);

  // مجلّدُ العمل: بدالّة المحرّك نفسِها، لا بمسارٍ نكتبه نحن.
  //   agent-scope-config-Bh5RAia-.mjs:402  resolveAgentWorkspaceDir(cfg, agentId)
  const dir = mScope.m(cfg, "main");
  out.workspace = String(dir || "");
  if (!out.workspace) throw new Error("تعذّر حلُّ مجلّد العمل");
  mkdirSync(out.workspace, { recursive: true });

  const dirs = await mWs.C({});          // resolveWorkspaceTemplateSearchDirs
  out.templateDirs = dirs.map(String);
  if (!dirs.length) throw new Error("لا مجلّدَ قوالبَ في الحزمة");

  const strip = (t) => mFm.t(t)?.body.replace(/^\s+/, "") ?? t;

  // نفسُ الملفّات ونفسُ الترتيب الذي ينشره `seedWorkspaceBootstrap`:
  //   :685 AGENTS.md · :686 SOUL.md · :687 IDENTITY.md · :688 USER.md
  //   :721 BOOTSTRAP.md
  const names = [mWs.t, mWs.a, mWs.r, mWs.s, mWs.n].filter(Boolean);
  for (const name of names) {
    const target = join(out.workspace, name);
    if (existsSync(target)) {
      out.files.push({ name, state: "موجود" });
      out.existed += 1;
      continue;
    }
    let body = null, from = "";
    for (const d of dirs) {
      try {
        body = strip(await readFile(join(d, name), "utf-8"));
        from = join(d, name);
        break;
      } catch (e) { if (e?.code !== "ENOENT") throw e; }
    }
    if (body === null) {
      out.files.push({ name, state: "لا قالبَ له" });
      continue;
    }
    try {
      writeFileSync(target, body, { flag: "wx" });   // لا يدوس موجوداً
      out.files.push({ name, state: "كُتب", from, bytes: body.length });
      out.created += 1;
    } catch (e) {
      out.files.push({ name, state: "تعذّر: " + String(e?.code || e?.message) });
    }
  }
  out.ok = out.files.every((f) => f.state !== ""
    && !String(f.state).startsWith("تعذّر"));
} catch (e) {
  out.error = String(e?.message || e).slice(0, 300);
}
console.log(JSON.stringify(out, null, 2));
