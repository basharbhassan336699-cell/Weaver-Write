// فحصُ البحث — بدوالّ المحرّك نفسِه، لا بحيلةٍ من عندنا.
//
// آليّةُ أوبن كلاو في البحث (مقروءةٌ من كوده):
//
//   ① النموذجُ يستدعي أداة `web_search`.
//   ② وقد تُحذَف الأداةُ أصلاً إن كان بحثُ Codex الأصليُّ فعّالاً (نماذج GPT):
//        agent-tools-DXxcrXNI.mjs:227     tools.filter(t => t.name !== "web_search")
//        codex-native-web-search-core:122 shouldSuppressManagedWebSearchTool
//      وعندها يبحث المزوّدُ بنفسه بلا أداة.
//   ③ وإلّا فـ`web_search` «المُدارة» تحتاج **مزوّداً**، ويُحَلّ هكذا:
//        runtime-CFtRzJUE.mjs:101  resolveWebSearchProviderId
//        ├─ `tools.web.search.provider` إن ضُبط صراحةً ⟶ هو
//        └─ وإلّا: أوّلُ مزوّدٍ في `autoDetectOrder` عنده **إشارةُ اعتماد**
//                 (hasImplicitProviderSelectionSignal) — أي مفتاحٌ موجود.
//   ④ ولا مزوّدَ ⟶ "" ⟶ `hasUsableWebSearchProvider` = false ⟶ لا بحث.
//
// ومنه نتيجةٌ مهمّة: **duckduckgo لا يُكتشَف تلقائياً أبداً** — لأنّه بلا
// مفتاح، فلا إشارةَ له. يجب تعيينُه صراحةً ليُستعمل. مقيسٌ لا مُخمَّن.
//
// يُنادى: node probe_search.mjs "<استعلام>"    ⟶ JSON
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const query = process.argv[2] || "الإعجاز العلمي في القرآن";
const here = dirname(fileURLToPath(import.meta.url));
const rt = join(here, "runtime", "dist", "runtime-BjhiVv_x.mjs");

const out = { providers: [], configured: [], chosen: "", usable: false,
              ok: false, count: 0, first: "", error: "" };
try {
  const m = await import(rt);
  out.providers = (m.listWebSearchProviders({}) || []).map((p) => p.id);
  out.configured = (m.listConfiguredWebSearchProviders({}) || []).map((p) => p.id);
  out.chosen = m.resolveWebSearchProviderId({}) || "";
  out.usable = !!m.hasUsableWebSearchProvider({});
  if (!out.usable) {
    out.error = "لا مزوّدَ صالح: لا مفتاحَ يُكتشَف، ولا مزوّدَ مُعيَّنٌ صراحةً";
  } else {
    const r = await m.runWebSearch({ query, maxResults: 5 });
    const arr = Array.isArray(r?.results) ? r.results : Array.isArray(r) ? r : [];
    out.count = arr.length;
    out.first = String(arr[0]?.title || arr[0]?.url || "").slice(0, 160);
    out.ok = out.count > 0;
    if (!out.ok) out.error = "المزوّدُ ردّ بلا نتائج";
  }
} catch (e) {
  out.error = String(e?.message || e).slice(0, 300);
}
console.log(JSON.stringify(out, null, 2));
