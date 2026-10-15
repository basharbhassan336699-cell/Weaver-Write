"""متطلّباتُ المستخدم التزامٌ للمهمّة كلِّها — مهما طال البحث.

    python3 tests/test_requirements_flow.py

الجذورُ المقيسة على هاتف المستخدم (بحثٌ من ١٥ صفحة خرج ١٠–١١، وتوسيعٌ ينسى
التعليمات):
  ١ ملفّاتُ التعريف التي يقرؤها النموذجُ في كلِّ رسالة قوالبُ مساعدٍ شخصيٍّ عامّ
    (Discord، البريد…) لا كلمةَ فيها عن عملنا ⟵ AGENTS.md لنا
  ٢ المهاراتُ والدستورُ لا تُرقّى بعد البذر الأوّل ⟵ workspace_sync كلَّ تشغيل
  ٣ لا مكانَ ثابتاً لمتطلّبات المهمّة ⟵ REQUEST.md يُعرض في كلِّ فحص
  ٤ نصُّ البحث داخل JSON ينكسر بكلِّ تعديل ⟵ أجزاءٌ Markdown، وJSON متسامح
  ٥ لا حجمَ قبل الكتابة ⟵ office.py plan (مقيس: ٥٠ صفحة ⟵ 50.0)
  ٦ مهلةُ النوبة ٦٠٠ ث ⟵ ١٨٠٠
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from pipeline import weaver_core as W  # noqa: E402

OFFICE = os.path.join(ROOT, "pipeline", "office.py")
FAILS = []


def check(name, cond):
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        FAILS.append(name)


def test_workspace_prompts(tmp):
    ws = os.path.join(tmp, "ws")
    os.makedirs(ws)
    saved = W.workspace_dir
    W.workspace_dir = lambda: ws
    try:
        stock_agents = W._stock_template("AGENTS.md")
        check("قالبُ المحرّك يُقرأ (مساعدٌ عامّ: Discord)",
              "Discord" in stock_agents or not stock_agents)
        open(os.path.join(ws, "AGENTS.md"), "w").write(
            stock_agents or "# AGENTS.md - Your Workspace\nDiscord")
        open(os.path.join(ws, "IDENTITY.md"), "w").write(
            "# IDENTITY.md\n_Fill this in during your first conversation._\nTheme: x")
        open(os.path.join(ws, "USER.md"), "w").write("- Always use Times New Roman\n")
        rows = {n: (w_, d) for n, w_, d in W.ws_prompts_apply()}
        ag = open(os.path.join(ws, "AGENTS.md"), encoding="utf-8").read()
        check("AGENTS.md: قالبُ المحرّك ⟵ نسختُنا", rows["AGENTS.md"][0] == "openclaw"
              and "REQUEST.md" in ag and "Discord" not in ag)
        check("ونسخةٌ احتياطيّة .openclaw", os.path.isfile(
            os.path.join(ws, "AGENTS.md.openclaw")))
        check("IDENTITY.md: قالبٌ أضاف إليه المحرّك ⟵ يُعرف ويُستبدل",
              "Weaver Write" in open(os.path.join(ws, "IDENTITY.md")).read())
        check("USER.md فيه تفضيلٌ حقيقيّ ⟵ لا يُمَسّ",
              open(os.path.join(ws, "USER.md")).read().startswith("- Always"))
        check("مرّةً ثانية ⟵ لا شيء (weaver/custom)",
              all(w_ in ("weaver", "custom") for _n, w_, _d in W.ws_prompts_apply()))
    finally:
        W.workspace_dir = saved
    a = open(os.path.join(W.WS_PROMPTS_SRC, "AGENTS.weaver.md"), encoding="utf-8").read()
    for k, why in (("REQUEST.md", "متطلّباتٌ في ملفٍّ ثابت"),
                   ("بلغة المستخدم", "الردُّ والملاحظاتُ بلغته"),
                   ("كلُّ بندٍ آخرَ باقٍ", "التوسيعُ لا يُسقط البنودَ الأخرى"),
                   ("office.py plan", "الحجمُ قبل الكتابة"),
                   ("٥٠ صفحة", "والبحثُ الطويلُ أجزاءٌ في ملفّات"),
                   ("## التقدّم", "ويُستأنف إن انقطعت النوبة")):
        check("AGENTS.md: " + why, k in a)
    check("AGENTS.md أقصرُ من قالب المحرّك", len(a) < len(W._stock_template("AGENTS.md")
                                                    or "x" * 10 ** 6))


def test_sync_once():
    calls = []
    saved = (W.soul_apply, W.skills_apply, W.ws_prompts_apply, dict(W._WS_SYNCED))
    try:
        W._WS_SYNCED.update(done=False, rows=[])
        W.soul_apply = lambda force=False: calls.append("soul") or (True, "")
        W.skills_apply = lambda force=False: calls.append("skills") or (True, [])
        W.ws_prompts_apply = lambda: calls.append("ws") or []
        W.workspace_sync()
        W.workspace_sync()
        check("الدستورُ والمهاراتُ وملفّاتُ التعريف تُرقّى مرّةً لكلِّ تشغيل",
              calls == ["soul", "skills", "ws"])
    finally:
        W.soul_apply, W.skills_apply, W.ws_prompts_apply = saved[:3]
        W._WS_SYNCED.clear()
        W._WS_SYNCED.update(saved[3])
    src = open(os.path.join(ROOT, "pipeline", "weaver_core.py"), encoding="utf-8").read()
    check("ensure_workspace تستدعيها حتى بعد البذر",
          "        workspace_sync(say)\n        return True, \"مبذورة\"" in src)


def build(spec_path, out):
    r = subprocess.run([sys.executable, OFFICE, "build", spec_path, "--out", out],
                       capture_output=True, text=True, timeout=300)
    return r.stdout + r.stderr


def test_office(tmp):
    import office as O
    d = os.path.join(tmp, "chat")
    os.makedirs(os.path.join(d, "sections"))
    open(os.path.join(d, "sections", "s02.md"), "w").write(
        "# المبحث الثاني\n\nفقرةٌ تمهيديّة.\n\n## المطلب\n\n"
        + "نصٌّ طويلٌ في فقرةٍ واحدةٍ يتجاوز ستّةَ أسطرٍ بكثير. " * 25 + "\n")
    open(os.path.join(d, "sections", "s01.md"), "w").write(
        "# المبحث الأوّل\n\nسطرٌ أوّل.\nوسطرٌ ثانٍ في الفقرة نفسِها.\n\n"
        "## المطلب الأوّل\n\n- نقطة\n- أخرى\n\n### أولاً\n\nنصٌّ (جفال، 2010).\n")
    open(os.path.join(d, "refs.md"), "w").write(
        "# المراجع\n- جفال، زياد. (2010). التنظيم الدستوري.\n2. الخطيب. (2021). الوسيط.\n")
    sp = O._expand_sections({"sections": ["sections/*.md"], "references": "refs.md"}, d)
    heads = [(s["level"], s["heading"]) for s in sp["sections"]]
    check("Markdown: «# ## ###» ⟵ مبحثٌ ومطلبٌ وتقسيم، والنمطُ مرتَّب",
          heads == [(1, "المبحث الأوّل"), (2, "المطلب الأوّل"), (3, "أولاً"),
                    (1, "المبحث الثاني"), (2, "المطلب")])
    check("Markdown: النقاطُ تبقى في النصّ", "- نقطة" in sp["sections"][1]["body"])
    check("refs.md: مرجعٌ في كلِّ سطر (بلا «- » ولا «2. »)",
          sp["references"] == ["جفال، زياد. (2010). التنظيم الدستوري.",
                               "الخطيب. (2021). الوسيط."])
    # JSON بسطرٍ حقيقيٍّ داخل نصّ (ما تكتبه أداةُ التعديل)
    raw = os.path.join(d, "raw.json")
    open(raw, "w").write('{"title": "x", "sections": [{"heading": "a", "body": "سطر\nوسطر"}]}')
    check("JSON بسطرٍ حقيقيٍّ داخل النصّ ⟵ يُقبل", O._load_json(raw)["sections"][0][
        "body"] == "سطر\nوسطر")

    spec = {"title": "بحث", "cover": {"author": ""}, "pages": 4,
            "sections": ["sections/*.md"], "references": "refs.md",
            "outline": {"chapters": 2, "per_chapter": 1},
            "rules": {"bullets": True, "references_min": 12, "paragraph_lines": [3, 6]}}
    sj = os.path.join(d, "office-spec.json")
    json.dump(spec, open(sj, "w"), ensure_ascii=False)
    o = build(sj, os.path.join(d, "a.docx"))
    check("references_min ⟵ ✗ حين يقلّ", "✗ references: 2, at least 12" in o)
    check("bullets ⟵ مبحثٌ بلا نقاطٍ يُذكر", "none in: «المبحث الثاني»" in o)
    check("لا REQUEST.md ⟵ يُطلب كتابتُه", "no REQUEST.md next to the spec" in o)
    open(os.path.join(d, "REQUEST.md"), "w").write(
        "# متطلّبات\n- خط Times New Roman\n- كتابة سردية مع نقاط حيث يلزم\n"
        "- الفقرة من 3 إلى 6 أسطر\n")
    o = build(sj, os.path.join(d, "a.docx"))
    check("REQUEST.md ⟵ كلُّ بنودِه في الفحص ليؤكّدها",
          "📋 REQUEST.md" in o and "□ كتابة سردية مع نقاط حيث يلزم" in o
          and "□ الفقرة من 3 إلى 6 أسطر" in o)
    check("paragraph_lines ⟵ يُقاس", "paragraph length" in o)

    # الخطّة: الحجمُ قبل الكتابة يطابق ما يقيسه الفحص
    pl = O.plan_word({"title": "بحث", "pages": 10, "cover": {}, "font": "Amiri",
                      "outline": {"chapters": 3, "per_chapter": 3, "sub_min": 1}})
    check("plan: عددُ كلماتٍ ونصيبُ كلِّ مبحثٍ ومطلبٍ وعددُ ملفّات",
          pl["text_words"] > 1000 and pl["per_section"] > 0 and pl["files"] >= 5)
    secs = O._plan_mock({"title": "بحث", "cover": {}, "font": "Amiri"}, "ar",
                        pl["text_words"], 3, 3, 1, 70)
    out = os.path.join(d, "p.docx")
    O.build_word(secs, out)
    from docx_pages import estimate_pages
    got = estimate_pages(out)["exact"]
    check("plan: مستندٌ بحجم الخطّة ≈ الصفحاتُ المطلوبة (%.1f من 10)" % got,
          abs(got - 10) <= 0.6)
    r = subprocess.run([sys.executable, OFFICE, "plan", sj], capture_output=True,
                       text=True, timeout=300)
    check("office.py plan يعمل من سطر الأوامر", r.returncode == 0 and "plan: 4 pages" in r.stdout)


def test_skill_deadline_media():
    sk = open(os.path.join(W.SKILLS_SRC, "office-word", "SKILL.md"), encoding="utf-8").read()
    check("المهارة: REQUEST.md ثمّ plan ثمّ أجزاءُ Markdown",
          "REQUEST.md" in sk and "office.py plan" in sk and "sections/*.md" in sk
          and "refs.md" in sk)
    check("المهارة: «ولو ٥٠ صفحة»", "ولو ٥٠ صفحة" in sk)
    check("مهلةُ النوبة ١٨٠٠ ث", W._AGENT_DEADLINE_DEFAULT == 1800)
    import server as S
    saved = (W.available, W.node_bin, W.ask)
    try:
        W.available = lambda: True
        W.node_bin = lambda: "node"
        W.ask = lambda text, **k: {"answer": "تمّ:\nMEDIA:حقوق الطفل.docx\nانتهى"}
        r = S._chat_via_engine("اكتب", [], timeout=5)
        check("«MEDIA:…» ⟵ سطرٌ مقروء", r and "📎 حقوق الطفل.docx" in r["reply"]
              and "MEDIA:" not in r["reply"])
    finally:
        W.available, W.node_bin, W.ask = saved


if __name__ == "__main__":
    print("requirements flow: prompts · REQUEST.md · Markdown parts · plan · deadline")
    tmp = tempfile.mkdtemp(prefix="wv-rq-")
    try:
        test_workspace_prompts(tmp)
        test_sync_once()
        test_office(tmp)
        test_skill_deadline_media()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("FAIL: " + ", ".join(FAILS) if FAILS else "PASS")
    sys.exit(1 if FAILS else 0)
