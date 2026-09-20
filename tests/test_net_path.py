# -*- coding: utf-8 -*-
"""مسارُ الاتصال — أن تبقى النوبةُ حيّةً حتى تبحث.

العطبُ الذي كلّف ثلاثةَ أيّام: كنّا نقصُّ مهلةَ نوبة الوكيل إلى ٢٢٠ ثانية،
ومهلةُ المحرّك نفسِه ٦٠٠:

    register.agent-turn-gi9D9FTy.mjs:41
      .option("--timeout <seconds>", "Agent deadline in seconds", "600")

ونوباتُ المستخدم المقيسة: ٧ دقائق و٢ و٦ — أي ٤٢٠ و١٢٠ و٣٦٠ ثانية. فنوبتان
من ثلاثٍ تُقتلان، ثمّ يسقط الطلبُ إلى نداءٍ مباشرٍ بلا أدوات، فيُجيب النموذجُ
واثقاً بلا إنترنت. هذه الفحوصُ تمنع عودةَ ذلك.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import weaver_core as wc   # noqa: E402

P = F = 0
def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


print("\n— مهلةُ النوبة —")
ok("الافتراضيُّ ٦٠٠ كما عند المحرّك", wc.agent_deadline() == 600,
   str(wc.agent_deadline()))
ok("لا تنزل تحت ٦٠٠ ولو طُلب أقلّ",
   wc._AGENT_DEADLINE_DEFAULT == 600)
_old = os.environ.get("WEAVER_AGENT_DEADLINE")
os.environ["WEAVER_AGENT_DEADLINE"] = "30"
ok("قيمةٌ سخيفةٌ في البيئة تُرَدّ إلى ٦٠٠", wc.agent_deadline() == 600)
os.environ["WEAVER_AGENT_DEADLINE"] = "1200"
ok("قيمةٌ أوسعُ في البيئة تُحترم", wc.agent_deadline() == 1200)
if _old is None:
    os.environ.pop("WEAVER_AGENT_DEADLINE", None)
else:
    os.environ["WEAVER_AGENT_DEADLINE"] = _old
ok("فسحةُ ساعة الحائط موجبة", wc._AGENT_GRACE >= 60, str(wc._AGENT_GRACE))

print("\n— ask(): المهلةُ لا تُقَصّ —")
_src = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "pipeline", "weaver_core.py"),
    encoding="utf-8").read()
# السطرُ نفسُه يبقى مذكوراً في تعليقٍ يشرح العطب — فيُفحص الكودُ وحده.
_code = "\n".join(l for l in _src.split("\n") if not l.lstrip().startswith("#"))
ok("لم يعد يُطرح ٢٠ من المهلة",
   'str(max(30, int(timeout) - 20))' not in _code)
ok("العلمُ يأخذ مهلةَ المحرّك", '_to = str(_deadline)' in _src)
ok("ساعةُ الحائط أوسعُ من المهلة", 'timeout=_wall' in _src)
ok("وبلا مهلةٍ صريحةٍ ⟶ مهلةُ المحرّك",
   'def ask(text, timeout=None' in _code)
ok("ومهلةُ المتّصلِ الصريحةُ تُحترم ولا تُرفَع",
   '_wall = max(60, int(timeout))' in _code)
ok("المهلةُ تُكتب في إعداد المحرّك",
   '"agents.defaults.timeoutSeconds"' in _src)

print("\n— واجهةُ الويب —")
_ws = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "web", "server.py"), encoding="utf-8").read()
ok("لم تعد ٢٤٠ مُثبَّتةً في الويب",
   'WEAVER_ENGINE_TIMEOUT") or 240' not in _ws)
ok("الويب يأخذ المهلةَ من المحرّك", '_wc.agent_deadline()' in _ws)

print("\n— فحصُ الأدوات —")
ok("probe_tools.mjs موجود", os.path.isfile(wc.PROBE_TOOLS))
ok("tool_inventory موجودة", callable(getattr(wc, "tool_inventory", None)))
ok("net_doctor موجودة", callable(getattr(wc, "net_doctor", None)))
ok("محطّاتُ المسار تسع", len(wc.NET_HOPS) == 9, str(len(wc.NET_HOPS)))
_inv = wc.tool_inventory()
ok("الجردُ لا يرفع استثناءً", isinstance(_inv, dict))
if _inv.get("ok"):
    ok("web_search في جرد النموذج", _inv.get("web_search"),
       "suppress: " + str(_inv.get("suppressReason")))
    ok("web_fetch في جرد النموذج", _inv.get("web_fetch"))
else:
    print("    ⓘ لا node صالحٌ هنا — تُخطَّى محطّةُ الجرد: "
          + str(_inv.get("error"))[:80])

print("\n— مساحةُ العمل: EACCES على link() في أندرويد —")
ok("seed_workspace.mjs موجود", os.path.isfile(wc.SEED_WS))
ok("seed_workspace موجودة", callable(getattr(wc, "seed_workspace", None)))
ok("ensure_workspace موجودة", callable(getattr(wc, "ensure_workspace", None)))
ok("ask تبذر قبل النوبة", "ensure_workspace()" in _src)
ok("والبوّابةُ تبذر عند إقلاعةٍ جديدة",
   "ensure_workspace(say=_say)" in _src)
ok("والفحصُ الرخيصُ ملفٌّ لا عمليّة",
   "os.path.isfile(os.path.join(workspace_dir()" in _src)
_sw = open(wc.SEED_WS, encoding="utf-8").read()
ok("يستعمل resolveAgentWorkspaceDir من المحرّك", "agent-scope-config" in _sw)
ok("وقوالبَ المحرّك ومساراتِها", "resolveWorkspaceTemplateSearchDirs" in _sw
   or "mWs.C(" in _sw)
ok("وينزع الواجهةَ كما ينزعها هو", "frontmatter" in _sw)
ok("ولا يدوس ملفّاً موجوداً", 'flag: "wx"' in _sw)

print("\n— probe_tools.mjs: يستعمل دالّةَ المحرّك لا تقليداً —")
_mj = open(wc.PROBE_TOOLS, encoding="utf-8").read()
ok("يستورد tools-effective-inventory",
   "tools-effective-inventory" in _mj)
ok("يُحمّل إعدادَ المحرّك", "io.runtime" in _mj)
ok("يسأل عن سبب الحذف", "codex-native-web-search-core" in _mj)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
