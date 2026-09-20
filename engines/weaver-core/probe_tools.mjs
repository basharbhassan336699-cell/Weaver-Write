// أيُّ أدواتٍ يراها النموذجُ فعلاً؟ — بحساب المحرّك نفسِه، لا بتخمينٍ منّا.
//
// السؤالُ الذي عجزنا عن الإجابة عليه ثلاثةَ أيّام: «هل يصل `web_search` إلى
// النموذج أصلاً؟» والمحرّكُ يحسبها بدالّةٍ واحدة، وهي نفسُها التي يُجيب بها
// أمرُه `/tools`:
//
//     tools-effective-inventory-CKuogGVg.mjs:246   resolveEffectiveToolInventory
//     commands-handlers.runtime-D9Kkm_k0.mjs:3712  /** Command handler for /tools. */
//
// وهي تحسبُ الجردَ **بعد** كلِّ المصافي، لا قبلها:
//   ① `createOpenClawCodingTools` تبني السطحَ كاملاً
//   ② `applyModelProviderToolPolicy` تُطبّق سياسةَ المزوّد، ومنها:
//        agent-tools-DXxcrXNI.mjs:227   tools.filter(t => t.name !== "web_search")
//      حين يكون بحثُ Codex الأصليُّ فعّالاً. وشرطُ فعاليّته مقروءٌ لا مُخمَّن:
//        codex-native-web-search-core-DKmZL1Sz.mjs:14
//          isCodexNativeSearchEligibleModel = modelApi === "openai-chatgpt-responses"
//      ونحن على `openai-completions`، فلا تُحذَف. لكنّ القياسَ أصدقُ من
//      الاستنتاج — فهذا الفحصُ يقيس.
//   ③ ثمّ ملفُّ الأدوات (`tools.profile`) والسماحُ والمنع.
//
// يُنادى:  node probe_tools.mjs [مزوّد] [نموذج]      ⟶ JSON
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const provider = process.argv[2] || "";
const model = process.argv[3] || "";
const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "runtime", "dist");
const io = join(dist, "io.runtime-4x3HMjSp.mjs");
const inv = join(dist, "tools-effective-inventory-CKuogGVg.mjs");
const codex = join(dist, "codex-native-web-search-core-DKmZL1Sz.mjs");

const out = { ok: false, profile: "", agentId: "", groups: [], tools: [],
              web_search: false, web_fetch: false, browser: false,
              suppressed: false, suppressReason: "", error: "" };

// الإعدادُ من ملفّه — وبدونه تُحسب الأدواتُ على إعدادٍ فارغ، فيكون الجوابُ
// عن نظامٍ آخر لا عن نظامك. (نفسُ العطب الذي خدعني في فحص البحث.)
async function loadEngineConfig() {
  try {
    const m = await import(io);
    const c = await m.loadConfig?.({});
    return c?.config ?? c ?? undefined;
  } catch { return undefined; }
}

try {
  const cfg = await loadEngineConfig();
  const m = await import(inv);
  // المنفذُ المُصغَّر `r` هو `resolveEffectiveToolInventory` (سطرُ التصدير
  // في ذيل الملفّ: `resolveEffectiveToolInventory as r`).
  const res = m.r({
    cfg,
    modelProvider: provider || undefined,
    modelId: model || undefined,
  });
  out.profile = String(res?.profile || "");
  out.agentId = String(res?.agentId || "");
  for (const g of res?.groups || []) {
    const names = (g?.tools || []).map((t) => String(t?.id || "")).filter(Boolean);
    out.groups.push({ id: String(g?.id || ""), label: String(g?.label || ""),
                      count: names.length, tools: names });
    out.tools.push(...names);
  }
  out.web_search = out.tools.includes("web_search");
  out.web_fetch = out.tools.includes("web_fetch");
  out.browser = out.tools.includes("browser");
  out.ok = out.tools.length > 0;

  // ولماذا غاب `web_search` إن غاب؟ المحرّكُ يقول السببَ بنفسه.
  try {
    const cx = await import(codex);
    const act = cx.o({ config: cfg, modelProvider: provider || undefined,
                       modelId: model || undefined });
    out.suppressed = act?.state === "native_active";
    out.suppressReason = String(act?.inactiveReason || act?.state || "");
  } catch { /* لا يُفشِل الفحصَ كلَّه */ }
} catch (e) {
  out.error = String(e?.message || e).slice(0, 300);
}
console.log(JSON.stringify(out, null, 2));
