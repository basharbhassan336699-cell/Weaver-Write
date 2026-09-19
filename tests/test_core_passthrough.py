# -*- coding: utf-8 -*-
"""مَعبرُ المحرّك: `weaver core …` — معماريّتُه كما هي، لا غلافٌ نكتبه.

كنتُ أكتب غلافاً لكلِّ حاجة (`--gateway` · `--model set` · `--web-search`)،
وهي إعادةُ بناءٍ لما عنده. وعنده ٨٧ أمراً بأقسامها وخياراتها وتوثيقها،
وتنمو بترقية الحزمة بلا أن نلمس سطراً.

فهذا مَعبرٌ لا غلاف: تُمرَّر الوسائطُ حرفاً، في بيئتنا المعزولة، وبطرفيّةٍ
موروثة فتعمل معالجاتُه التفاعليّة.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_ok, _bad = [0], [0]


def chk(label, cond, extra=""):
    if cond:
        _ok[0] += 1
        print("   OK  " + label)
    else:
        _bad[0] += 1
        print("   XX  " + label + ("   " + str(extra) if extra else ""))


import weaver                              # noqa: E402
from pipeline import weaver_core as W      # noqa: E402

print("=" * 70)
print(" 1) الوسائطُ تمرّ حرفاً — لا تُحلَّل عندنا ولا تُترجَم")
print("=" * 70)
_real = (W.run_tty, W.available, W.node_bin)
_seen = []
try:
    W.available = lambda: True
    W.node_bin = lambda: "/usr/bin/node"
    W.run_tty = lambda args, timeout=None: (_seen.append(list(args)) or 0)

    weaver.cmd_core(["agent", "-m", "سؤال", "--json", "--timeout", "40"])
    chk("تمرّ كما هي",
        _seen[-1] == ["agent", "-m", "سؤال", "--json", "--timeout", "40"],
        _seen[-1:])

    _seen.clear()
    weaver.cmd_core(["configure", "--section", "web"])
    chk("  -> وأقسامُه كما هي", _seen[-1] == ["configure", "--section", "web"])

    _seen.clear()
    weaver.cmd_core([])
    chk("  -> وبلا وسائطَ يُعرض دليلُه هو", _seen[-1] == ["--help"], _seen[-1:])

    _seen.clear()
    weaver.cmd_core(["browser", "--browser-profile", "openclaw", "doctor"])
    chk("  -> وأعلامٌ لا يعرفها argparse عندنا تمرّ بلا رفض",
        "--browser-profile" in _seen[-1], _seen[-1:])
finally:
    (W.run_tty, W.available, W.node_bin) = _real

print()
print("=" * 70)
print(" 2) وبطرفيّةٍ موروثة — وإلّا ماتت معالجاتُه التفاعليّة")
print("=" * 70)
import inspect as _i                       # noqa: E402
_code = _i.getsource(W.run_tty).split('"""')[-1]
chk("run_tty لا تلتقط الخرج",
    "subprocess.call" in _code and "capture_output" not in _code)
chk("  -> وبالبيئة المعزولة (بروفايل · حالة · منفذ · مفتاح)",
    "engine_env()" in _code)

print()
print("=" * 70)
print(" 3) ولا يكسر أوامرَ النظام")
print("=" * 70)
_p = weaver.build_parser()
_names = set(_p._subparsers._group_actions[0].choices)
for _c in ("install", "keys", "serve", "ask", "doctor", "version"):
    chk("أمرُ `%s` باقٍ" % _c, _c in _names)
chk("و`core` مُعلَنٌ في المساعدة", "core" in _names)

print()
print("=" * 70)
print(" 4) وحين لا محرّك: يُقال السببُ ولا يُنادى شيء")
print("=" * 70)
_real2 = (W.available, W.node_bin, W.why_unavailable)
try:
    W.available = lambda: False
    chk("غيرُ مركَّب ⟶ رمزُ خروجٍ غيرُ صفر", weaver.cmd_core(["doctor"]) == 2)
    W.available = lambda: True
    W.node_bin = lambda: None
    W.why_unavailable = lambda: "node قديم"
    chk("ولا node صالح ⟶ كذلك", weaver.cmd_core(["doctor"]) == 2)
finally:
    (W.available, W.node_bin, W.why_unavailable) = _real2

print()
print("=" * 70)
print(" RESULT: " + ("PASS" if _bad[0] == 0 else "FAIL")
      + "   (%d/%d)" % (_ok[0], _ok[0] + _bad[0]))
print("=" * 70)
sys.exit(1 if _bad[0] else 0)
