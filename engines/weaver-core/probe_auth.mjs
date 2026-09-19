// كتالوجُ مزوّدي الاعتماد — من المحرّك نفسِه، لا من قائمةٍ نكتبها بيدنا.
//
// كنتُ أكتب ١٤ مزوّداً يدوياً بينما المحرّكُ يدعم ٩٢ خياراً، ويبنيها من
// بيانات إضافاته:
//     auth-choice-options-tnlfLecZ.mjs → buildAuthChoiceGroups (الصادر `t`)
//     provider-auth-choices-G0lyWlAr.mjs → resolveManifestProviderAuthChoices
// فمن رُكّبت إضافتُه ظهر، ومن رُقّيت الحزمةُ بمزوّدٍ جديدٍ ظهر — بلا أن
// نلمس سطراً.
//
// يطبع JSON: [{choice, label, providerId, group, hint}]
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const mod = join(here, "runtime", "dist", "auth-choice-options-tnlfLecZ.mjs");

// وخريطةُ متغيّرات البيئة لكلّ مزوّد — من المحرّك أيضاً:
//   config-provider-contract-BdOif1pq.mjs  resolveHermesProviderApiKeyEnv
// كنتُ أكتب ١٤ اسماً يدوياً، وهو يعرفها كلَّها ويشتقُّ ما لا يعرفه.
const contract = join(here, "runtime", "dist",
                      "config-provider-contract-BdOif1pq.mjs");

const out = [];
try {
  const m = await import(mod);
  const build = m.t || m.buildAuthChoiceGroups;
  const res = build ? build({}) : null;
  for (const g of (res?.groups || [])) {
    for (const o of (g.options || [])) {
      out.push({
        choice: String(o.value || ""),
        label: String(o.label || ""),
        providerId: String(o.providerId || g.providerIds?.[0] || ""),
        group: String(g.value || ""),
        hint: String(o.hint || g.hint || ""),
      });
    }
  }
} catch (e) {
  console.log(JSON.stringify({ error: String(e?.message || e) }));
  process.exit(0);
}
// اسمُ متغيّرِ المفتاح لكلِّ مزوّدٍ ظهر في الكتالوج
const envByProvider = {};
try {
  const c = await import(contract);
  const resolve = c.d || c.resolveHermesProviderApiKeyEnv;
  if (typeof resolve === "function") {
    for (const id of new Set(out.map((r) => r.providerId).filter(Boolean))) {
      try {
        const v = resolve(id);
        if (typeof v === "string" && v) envByProvider[id] = v;
      } catch {}
    }
  }
} catch {}
for (const r of out) if (envByProvider[r.providerId]) r.envVar = envByProvider[r.providerId];
console.log(JSON.stringify(out, null, 1));
