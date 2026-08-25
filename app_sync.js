/*
 * أكواد ربط API Key في الواجهة الأمامية — WeaverCode
 * المصدر: web/static/app.js
 */

// ══════════════════════════════════════════════
// 1. تحميل الإعدادات عند فتح صفحة الإعدادات (GET /api/settings)
// ══════════════════════════════════════════════
  async function loadSettings() {
    const r = await api("/api/settings"); const s = r.settings || {};
    $("#modelInput").value = s.WEAVER_MODEL || "";
    if ($("#baseUrlInput")) $("#baseUrlInput").value = s.WEAVER_BASE_URL || "";
    if ($("#maxTokensInput")) $("#maxTokensInput").value = s.WEAVER_MAX_TOKENS || "";
    if ($("#askPermToggle")) $("#askPermToggle").checked =
      String(s.WEAVER_ASK_PERMISSION || "0").toLowerCase() in { "1": 1, "true": 1, "yes": 1, "on": 1 };
    $("#keyInput").value = ""; $("#keyInput").placeholder = s.WEAVER_API_KEY || "WEAVER_API_KEY";
  }
  $("#askPermToggle") && ($("#askPermToggle").onchange = async (e) => {
    await post("/api/settings", { WEAVER_ASK_PERMISSION: e.target.checked ? "1" : "0" });
    $("#settingsMsg").textContent = e.target.checked
      ? "🔐 وضع الإذن مُفعّل — سيسألك قبل الأدوات الحسّاسة."
      : "▶️ وضع الإذن معطّل — تنفيذ تلقائي.";
  });


// ══════════════════════════════════════════════
// 2. زر إظهار/إخفاء المفتاح + تغيير المزوّد
// ══════════════════════════════════════════════
  $("#keyToggle").onclick = () => { const k = $("#keyInput"); k.type = k.type === "password" ? "text" : "password"; };
  $("#providerSel").onchange = async (e) => { if (!e.target.value) return; await post("/api/command", { command: "/provider " + e.target.value }); loadSettings(); refreshStatus(); };
  $("#saveSettings").onclick = async () => {


// ══════════════════════════════════════════════
// 3. حفظ الإعدادات (POST /api/settings) — يشمل WEAVER_API_KEY
// ══════════════════════════════════════════════
  $("#saveSettings").onclick = async () => {
    const body = {};
    if ($("#modelInput").value.trim()) body.WEAVER_MODEL = $("#modelInput").value.trim();
    if ($("#baseUrlInput") && $("#baseUrlInput").value.trim()) body.WEAVER_BASE_URL = $("#baseUrlInput").value.trim();
    if ($("#maxTokensInput") && $("#maxTokensInput").value.trim()) body.WEAVER_MAX_TOKENS = $("#maxTokensInput").value.trim();
    if ($("#keyInput").value.trim()) body.WEAVER_API_KEY = $("#keyInput").value.trim();
    const r = await post("/api/settings", body);
    let msg = r.saved && r.saved.length
      ? "✅ حُفظت: " + r.saved.join("، ") : (r.error ? "❌ " + r.error : "✅ حُفظت.");
    if (r.detected_platform) msg += " · كُشفت المنصة: " + r.detected_platform + " (اضغط «اكتشاف النماذج»)";
    $("#settingsMsg").textContent = msg;
    refreshStatus(); loadSettings();
  };
  $("#testConn").onclick = async () => { $("#settingsMsg").textContent = "…جارٍ الاختبار"; const r = await post("/api/settings/test-connection", {}); $("#settingsMsg").textContent = (r.success ? "✅ " : "❌ ") + (r.output || ""); };


// ══════════════════════════════════════════════
// 4. اختبار الاتصال
// ══════════════════════════════════════════════
  $("#testConn").onclick = async () => { $("#settingsMsg").textContent = "…جارٍ الاختبار"; const r = await post("/api/settings/test-connection", {}); $("#settingsMsg").textContent = (r.success ? "✅ " : "❌ ") + (r.output || ""); };

  // ── اكتشاف النماذج المتاحة فعلاً من المزوّد (بلا نماذج وهمية) ──
