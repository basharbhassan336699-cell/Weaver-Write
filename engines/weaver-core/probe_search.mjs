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
const io = join(here, "runtime", "dist", "io.runtime-4x3HMjSp.mjs");

// تُحمَّل إعداداتُ المحرّك من ملفّها. وبلا هذا كانت الدوالُّ تُنادى بلا
// إعداد، فلا ترى `tools.web.search.provider` المحفوظ وتقول «لا مزوّد» —
// وهو ما خدعني: ضبطتُ المزوّدَ ثمّ قال الفحصُ إنّه غيرُ مضبوط.
async function loadEngineConfig() {
  try {
    const m = await import(io);
    const c = await m.loadConfig?.({});
    return c?.config ?? c ?? undefined;
  } catch { return undefined; }
}

// نزعُ غلافِ الثقة **للعرض وحده**. المحرّكُ يلفّ كلَّ نصٍّ آتٍ من الشبكة:
//     <<<EXTERNAL_UNTRUSTED_CONTENT id="…">>>
//     Source: Web Search
//     ---
//     <النصّ>
//     <<<END_EXTERNAL_UNTRUSTED_CONTENT id="…">>>
// وهو حصنٌ مقصودٌ ضدّ حقن التعليمات (docs/tools/web.md: «re-wrapped exactly
// once at the core boundary, so no provider metadata can spoof the marker»).
// فلا يُمَسُّ في ما يصل النموذج — إنّما يُنزع من سطرِ المعاينة ليقرأه الإنسان.
function unwrap(t) {
  let x = String(t == null ? "" : t);
  x = x.replace(/<<<\/?(END_)?EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>/g, "");
  x = x.replace(/^\s*Source:[^\n]*\n/m, "");
  x = x.replace(/^\s*---\s*$/m, "");
  return x.replace(/\s+/g, " ").trim();
}

const out = { providers: [], configured: [], chosen: "", usable: false,
              ok: false, kind: "", provider: "", count: 0, first: "",
              tookMs: 0, error: "" };
try {
  const m = await import(rt);
  const config = await loadEngineConfig();
  const P = { config };
  out.providers = (m.listWebSearchProviders(P) || []).map((p) => p.id);
  out.configured = (m.listConfiguredWebSearchProviders(P) || []).map((p) => p.id);
  out.chosen = m.resolveWebSearchProviderId(P) || "";
  out.usable = !!m.hasUsableWebSearchProvider(P);
  if (!out.usable) {
    out.error = "لا مزوّدَ صالح: لا مفتاحَ يُكتشَف، ولا مزوّدَ مُعيَّنٌ صراحةً";
  } else {
    // شكلُ الجواب مُوثَّقٌ في docs/tools/web.md — اتّحادٌ موسومٌ بـ`kind`،
    // لا `results` دائماً. وكنتُ أقرأ `results` وحدها فأحسب جوابَ مزوّدٍ
    // مُركِّبٍ (kind:"answer") «بلا نتائج»، وأحسب خطأَه «بلا نتائج» أيضاً:
    //
    //   kind: "error"   ⟶ provider · error · message
    //   kind: "results" ⟶ count · results[{title,url,snippet,…}]
    //   kind: "answer"  ⟶ content · citations[{url,title}]
    //   kind: "raw"     ⟶ data (مزوّدٌ خارجيٌّ لا يُطابق الشكلين)
    //
    // والوسيطُ اسمُه `count` لا `maxResults` (نفسُ الملفّ).
    const raw = await m.runWebSearch({ config, args: { query, count: 5 } });
    // `runWebSearch` تُغلّف الجوابَ الموثَّقَ داخل `result`:
    //   { provider, result: { kind?, query, provider, count, results, … } }
    // وdocs/tools/web.md يصف **الداخلَ** لا الغلاف. فيُفكّ أوّلاً.
    // مقيسٌ على خرج جهاز المستخدم:
    //   {"provider":"duckduckgo","result":{"query":"…","count":5,
    //    "tookMs":2423,"externalContent":{…}}}
    const r = (raw && typeof raw === "object" && raw.result
               && typeof raw.result === "object") ? raw.result : raw;
    out.provider = String((raw && raw.provider) || r?.provider || "");
    // وقد يغيب `kind` في بعض الأغلفة، فيُستنتَج من الحقول الموجودة.
    let kind = r && typeof r === "object" ? (r.kind || "") : "";
    if (!kind && r && typeof r === "object") {
      if (r.error) kind = "error";
      else if (Array.isArray(r.results) || typeof r.count === "number") kind = "results";
      else if (typeof r.content === "string") kind = "answer";
      else if (r.data !== undefined) kind = "raw";
    }
    out.kind = kind || "";
    if (kind === "error") {
      out.error = String(r.message || r.error || "خطأُ مزوّد").slice(0, 300);
    } else if (kind === "results") {
      const arr = Array.isArray(r.results) ? r.results : [];
      out.count = typeof r.count === "number" ? r.count : arr.length;
      out.first = unwrap(arr[0]?.title || arr[0]?.url || "").slice(0, 160);
      out.tookMs = typeof r.tookMs === "number" ? r.tookMs : 0;
      out.ok = out.count > 0;
      if (!out.ok) out.error = "المزوّدُ ردّ بقائمةٍ فارغة";
    } else if (kind === "answer") {
      const c = String(r.content || "");
      out.count = Array.isArray(r.citations) ? r.citations.length : (c ? 1 : 0);
      out.first = unwrap(c).slice(0, 160);
      out.ok = c.trim().length > 0;
      if (!out.ok) out.error = "المزوّدُ ردّ بجوابٍ فارغ";
    } else if (kind === "raw") {
      const t = JSON.stringify(r.data ?? "");
      out.count = (t.match(/https?:\/\//g) || []).length;
      out.first = unwrap(t).slice(0, 160);
      out.ok = t.length > 2;
    } else {
      out.error = "شكلُ جوابٍ غيرُ معروف: " + JSON.stringify(r).slice(0, 200);
    }
  }
} catch (e) {
  out.error = String(e?.message || e).slice(0, 300);
}
console.log(JSON.stringify(out, null, 2));
