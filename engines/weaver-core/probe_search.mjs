// فحصُ مزوّدي البحث المركَّبين — نداءُ بحثٍ حقيقيٌّ لا ادّعاء.
//
// لماذا ملفٌّ منفصل؟ لأنّ الجوابَ الصادقَ على «هل يعمل البحث؟» لا يكون
// بقراءة إعدادٍ، بل بإرسال استعلامٍ ورؤيةِ النتائج. وهذا يحتاج node.
//
// يُنادى: node probe_search.mjs "<استعلام>"
// ويطبع JSON: [{provider, ok, count, first, error}]
import { readdirSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const query = process.argv[2] || "الإعجاز العلمي في القرآن";
const stateDir = process.env.OPENCLAW_STATE_DIR
  || join(process.env.HOME || "", ".weaver-write", "state");
const projects = join(stateDir, "npm", "projects");

function pluginDirs() {
  const out = [];
  if (!existsSync(projects)) return out;
  for (const p of readdirSync(projects)) {
    const nm = join(projects, p, "node_modules", "@openclaw");
    if (!existsSync(nm)) continue;
    for (const pkg of readdirSync(nm)) out.push(join(nm, pkg));
  }
  return out;
}

const results = [];
for (const dir of pluginDirs()) {
  let id = pkgId(dir);
  const entry = join(dir, "dist", "web-search-provider.js");
  if (!existsSync(entry)) continue;          // ليست إضافةَ بحث
  const row = { provider: id, ok: false, count: 0, first: "", error: "" };
  try {
    const mod = await import(entry);
    const make = Object.values(mod).find((v) => typeof v === "function");
    const prov = make({});
    row.provider = prov?.id || id;
    row.requiresKey = !!prov?.requiresCredential;
    row.envVars = prov?.envVars || [];
    const tool = await prov.createTool({ config: {}, maxResults: 5 });
    const out = await tool.execute({ query }, {});
    const txt = typeof out === "string" ? out : JSON.stringify(out);
    const arr = Array.isArray(out?.results) ? out.results
      : Array.isArray(out) ? out : null;
    // بعضُ المزوّدين يعيدون خطأً **داخل** الجواب بدل رميه — فلو عُدَّ ذلك
    // نجاحاً لقلنا «البحث يعمل» وهو لا يعمل. مقيسٌ على perplexity بلا مفتاح:
    //   {"error":"missing_perplexity_api_key","message":"…needs an API key"}
    let inner = null;
    try { inner = typeof out === "string" ? JSON.parse(out) : out; } catch {}
    if (inner && typeof inner === "object" && !Array.isArray(inner) && inner.error) {
      row.error = String(inner.message || inner.error).slice(0, 220);
      row.ok = false;
      results.push(row);
      continue;
    }
    row.count = arr ? arr.length : (txt.match(/https?:\/\//g) || []).length;
    row.first = (arr?.[0]?.title || arr?.[0]?.url || txt.slice(0, 160) || "").trim();
    row.ok = row.count > 0;
  } catch (e) {
    row.error = String(e?.message || e).slice(0, 200);
  }
  results.push(row);
}

function pkgId(dir) {
  try {
    const j = JSON.parse(readFileSync(join(dir, "openclaw.plugin.json"), "utf8"));
    return j.id || dir.split("/").pop();
  } catch { return dir.split("/").pop(); }
}

console.log(JSON.stringify(results, null, 2));
