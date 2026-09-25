# -*- coding: utf-8 -*-
"""نصوصُ المساعدة: `openclaw <أمر>` ⟶ `weaver core <أمر>` (الخيار ب — تجميليّ).

يُبدَّل حيث هو كلمةُ أمرٍ فقط. وتبقى الأسماءُ التي يحلّها التشغيل: المسارات،
والملفّات، والروابط، و@openclaw/*، وOPENCLAW_*، وCLI_NAME نفسُه."""
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "engines", "weaver-core"))
import help_rebrand as H   # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


print("\n— كلمةُ الأمر وحدها —")
for src, want in (
        ("Usage: openclaw browser [options]", "Usage: weaver core browser [options]"),
        ("Examples:\\n  openclaw onboard\\n", "Examples:\\n  weaver core onboard\\n"),
        ('["openclaw setup", "x"]', '["weaver core setup", "x"]'),
        ("use `openclaw qr` now", "use `weaver core qr` now")):
    ok(repr(src)[:48], H.rebrand_help(src)[0] == want, H.rebrand_help(src)[0])
for keep in ("state under ~/.openclaw-dev", "https://docs.openclaw.ai/cli",
             "schema for openclaw.json", "/etc/openclaw/secrets.json",
             "/tmp/openclaw/uploads", "@openclaw/ai", "OPENCLAW_STATE_DIR",
             'const CLI_NAME = "openclaw";', "openclaw-gateway",
             "./openclaw.patch.json5"):
    ok("يبقى: " + keep, H.rebrand_help(keep)[1] == 0, H.rebrand_help(keep)[0])

print("\n— على ملفّاتٍ بشكل المحرّك —")
_d = tempfile.mkdtemp()
os.makedirs(os.path.join(_d, "dist"))
meta = {"rootHelpText": "Usage: openclaw [options]\n\nExamples:\n  openclaw status\n"
        "Docs: https://docs.openclaw.ai/cli\n  --dev  under ~/.openclaw-dev"}
open(os.path.join(_d, "dist", "cli-startup-metadata.json"), "w").write(
    json.dumps(meta))
open(os.path.join(_d, "dist", "help-X.mjs"), "w").write(
    'const EXAMPLES = [["openclaw onboard", "a"]];\nprogram.name(CLI_NAME);\n')
open(os.path.join(_d, "dist", "argv-X.mjs"), "w").write(
    'description: "codes, use `openclaw qr` instead"; const n = "openclaw";\n')
open(os.path.join(_d, "dist", "other-X.mjs"), "w").write(
    'spawn("openclaw", args); // use `openclaw qr` instead\n')
_out = []
ok("يُطبَّق بلا فشل", H.apply(_d, say=_out.append), _out)
m = json.load(open(os.path.join(_d, "dist", "cli-startup-metadata.json")))
ok("JSON ما زال صالحاً، والأوامرُ بُدّلت",
   "weaver core status" in m["rootHelpText"]
   and "Usage: weaver core [options]" in m["rootHelpText"])
ok("  ⟵ والرابطُ والمسارُ كما هما",
   "docs.openclaw.ai" in m["rootHelpText"] and "~/.openclaw-dev" in m["rootHelpText"])
ok("EXAMPLES بُدّلت", '"weaver core onboard"' in open(
    os.path.join(_d, "dist", "help-X.mjs")).read())
_a = open(os.path.join(_d, "dist", "argv-X.mjs")).read()
ok("الجملةُ الوصفيّةُ بُدّلت حرفاً", "use `weaver core qr` instead" in _a)
ok("  ⟵ والاسمُ في الكود لم يُمَسّ", 'const n = "openclaw"' in _a)
ok("ملفُّ كودٍ خارج القائمة لم يُمَسّ إطلاقاً", open(
    os.path.join(_d, "dist", "other-X.mjs")).read()
   == 'spawn("openclaw", args); // use `openclaw qr` instead\n')
_out = []
H.apply(_d, say=_out.append)
ok("عديمُ الأثر إن أُعيد", all(" بُدِّل" not in l for l in _out), _out)
open(os.path.join(_d, "dist", "cli-startup-metadata.json"), "w").write(
    '{"a": "openclaw status"')                     # JSON مكسورٌ سلفاً
ok("ناتجٌ غيرُ صالح ⟵ لا يُكتب", H.patch_file(
    os.path.join(_d, "dist", "cli-startup-metadata.json"))[0] == "bad")

print("\n— سطرُ «Usage:» الحيّ — عند العرض فقط —")
_FN = ('function formatProgramHelpOutput(str) {\n\tlet output = str;\n'
       '\tif (x) output = y;\n' + H.USAGE_ANCHOR
       + '.replace(/^Options:/gm, "O");\n}\nprogram.name(CLI_NAME);\n')
_n, _st = H.patch_usage_text(_FN)
ok("المرساةُ موجودة ⟵ سطرٌ واحدٌ يُضاف قبلها", _st == "patched"
   and _n.count(H.USAGE_MARK) == 1
   and _n.index(H.USAGE_MARK) < _n.index(H.USAGE_ANCHOR))
ok("  ⟵ وCLI_NAME لا يُمَسّ (العمليّاتُ وإكمالُ الصدفة)",
   "program.name(CLI_NAME);" in _n)
ok("  ⟵ وبعد فحص سطر الجذر (فيبقى تلميحُه)",
   _n.index("if (x)") < _n.index(H.USAGE_MARK))
ok("عديمُ الأثر إن أُعيد", H.patch_usage_text(_n) == (_n, "already"))
ok("المرساةُ غائبة (إصدارٌ آخر) ⟵ لا يُمَسّ",
   H.patch_usage_text("function formatProgramHelpOutput(s) {}")[1] == "absent")
ok("والتبديلُ لا يعيد تسميةَ ما أضافه (RX لا يطابقه)",
   H.rebrand_help(H.USAGE_LINE)[1] == 0)
# السطرُ JavaScript صالحٌ ويفعل المطلوب — بـnode إن وُجد.
import shutil as _sh
import subprocess as _sp
_node = os.environ.get("WEAVER_NODE") or _sh.which("node")
if _node:
    _js = ("let output = 'Usage: openclaw [options] [command]\\n"
           "Usage: openclaw gateway [options]\\n  openclaw.json stays';\n"
           + H.USAGE_LINE + "process.stdout.write(output);")
    _r = _sp.run([_node, "-e", _js], capture_output=True, text=True, timeout=60)
    ok("node: الجذرُ والفرعيُّ ⟵ «Usage: weaver core …»، وغيرُهما كما هو",
       _r.stdout == "Usage: weaver core [options] [command]\n"
       "Usage: weaver core gateway [options]\n  openclaw.json stays",
       (_r.stdout, _r.stderr[:200]))
else:
    print("  – node غيرُ موجود — فحصُ JavaScript تُخطّي")
_d2 = tempfile.mkdtemp()
os.makedirs(os.path.join(_d2, "dist"))
open(os.path.join(_d2, "dist", "help-Z.mjs"), "w").write(_FN)
ok("patch_usage على مجلّد ⟵ patched ثمّ already",
   H.patch_usage(_d2)[0] == "patched" and H.patch_usage(_d2)[0] == "already")
ok("  ⟵ وبلا ملفّ الدالّة ⟵ bad بلا لمس", H.patch_usage(_d)[0] == "bad")

print("\n— الوصل —")
_pp = open(os.path.join(_ROOT, "engines", "weaver-core", "patch_portability.py"),
           encoding="utf-8").read()
ok("--repair يستدعيه بعد رقعة النقل", "help_rebrand.apply(root" in _pp)
ok("  ⟵ وفشلُه لا يُفشل الإصلاح", "تجميليٌّ، والمحرّكُ يعمل" in _pp)

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
