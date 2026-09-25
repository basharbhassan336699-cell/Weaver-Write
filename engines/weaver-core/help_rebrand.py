# -*- coding: utf-8 -*-
"""نصوصُ المساعدة: `openclaw <أمر>` ⟶ `weaver core <أمر>` — تجميليٌّ بخطرٍ صفر.

`weaver core --help` كان يطبع «Usage: openclaw …» وأمثلةً بـ`openclaw` — ١٨
موضعاً في المساعدة الجذريّة وحدها (مقيس). والأمرُ الذي يكتبه المستخدمُ فعلاً
`weaver core` (weaver.py). والنصوصُ مطبوخةٌ مسبقاً وتُطبع حرفياً:

    dist/cli-startup-metadata.json   rootHelpText · browserHelpText · …
    dist/help-*.mjs                  مصفوفةُ EXAMPLES

فيُبدَّل `openclaw` **حيث هو كلمةُ أمرٍ فقط** — لا يسبقه حرفُ مُعرِّفٍ ولا
`.` `/` `@` `~` `-`، ويتلوه فراغٌ أو نهايةُ نصّ. فتبقى كما هي — لأنّها أسماءٌ
حقيقيّةٌ يحلّها التشغيل —: `~/.openclaw-dev` · `openclaw.json` ·
`/etc/openclaw/…` · `docs.openclaw.ai/…` · `@openclaw/*` · `OPENCLAW_*`.

ولا يُمَسّ كودٌ تشغيليّ: `CLI_NAME` واسمُ عملية البوّابة (openclaw-gateway)
باقيان، فإطفاءُ البوّابة لا يتأثّر. وحدُّ ذلك: مساعدةُ الأوامر الفرعيّة غيرِ
المطبوخة تُرسم حيّةً من CLI_NAME فتبقى بـ`openclaw` (الخيار ج).

عديمُ الأثر إن أُعيد، ولا يكتب ملفَّ JSON إلا بعد أن يتحقّق أنّه ما زال صالحاً.

    python3 help_rebrand.py <مجلّد المحرّك> [--check]
"""
import glob
import json
import os
import re
import sys

NEW = "weaver core"
# كلمةُ الأمر وحدها. و`\\n` في JSON حرفان («\» و«n») فتُقبل نهايةً أيضاً.
# وبين علامتَي تنصيصٍ وحدَه (`"openclaw"`) اسمٌ في الكود لا أمر ⟵ لا يُمَسّ؛
# وبعد علامةِ تنصيصٍ يتلوها فراغ (`"openclaw setup"`) أمرٌ في مثال ⟵ يُبدَّل.
RX = re.compile(
    r"(?:(?<=[\"'])openclaw(?=[ \t])"
    r"|(?<![\w./@~\-\"'])openclaw(?=[ \t`'\"\]\)]|\\n|$))", re.M)


# وجُملٌ وصفيّةٌ بعينها داخل ملفّات الكود (وصفُ أمرٍ في المساعدة): تُبدَّل
# **حرفاً بحرف** ولا شيءَ سواها — فلا يُمَسّ اسمٌ يحلّه التشغيل.
LITERALS = (("use `openclaw qr` instead", "use `weaver core qr` instead"),)
LITERAL_GLOB = ("dist/argv-*.mjs", "dist/devices-cli-*.mjs")


# وسطرُ «Usage:» نفسُه لا يأتي من النصوص المطبوخة: المحرّكُ يرسمه حيّاً من
# `program.name(CLI_NAME)` (قِيس على المحرّك الحقيقيّ: الأمثلةُ صارت
# «weaver core …» وبقي «Usage: openclaw [options] [command]»). وتغييرُ
# CLI_NAME خطر: يسمّي به العمليّاتِ (process.title) وإكمالَ الصدفة، واسمٌ فيه
# مسافةٌ يكسر الإكمال. فيُبدَّل **عند العرض فقط**: للمحرّك دالّةٌ تمرّ بها كلُّ
# مساعدةٍ قبل طباعتها (formatProgramHelpOutput)، يُضاف فيها سطرٌ واحد — بعد
# فحصه لسطر الجذر، فيبقى تلميحُه كما كان.
USAGE_ANCHOR = ('\treturn output.replace(/^Usage:/gm, theme.heading("Usage:"))')
USAGE_MARK = "/*weaver-usage*/"
USAGE_LINE = ('\toutput = output.replace(/^(Usage:\\s+)openclaw(?=\\s)/gm, '
              '"$1weaver core"); ' + USAGE_MARK + "\n")


def patch_usage_text(text):
    """(النصّ، الحالة): patched · already · absent (المرساةُ ليست مرّةً واحدة)."""
    if USAGE_MARK in text:
        return text, "already"
    if text.count(USAGE_ANCHOR) != 1 or "function formatProgramHelpOutput(" \
            not in text:
        return text, "absent"
    return text.replace(USAGE_ANCHOR, USAGE_LINE + USAGE_ANCHOR), "patched"


def patch_usage(root, check=False):
    """(الحالة، الرسالة). يلمس ملفَّ help-*.mjs الذي فيه الدالّةُ وحده."""
    files = [p for p in sorted(glob.glob(os.path.join(root, "dist", "help-*.mjs")))
             if "function formatProgramHelpOutput(" in
             open(p, encoding="utf-8", errors="replace").read()]
    if len(files) != 1:
        return "bad", "دالّةُ عرض المساعدة غيرُ موجودة — تغيّر الإصدار؟ لم يُمَسّ"
    p = files[0]
    src = open(p, encoding="utf-8").read()
    new, st = patch_usage_text(src)
    if st == "already":
        return "already", os.path.relpath(p, root) + " — سطرُ Usage مُبدَّلٌ سلفاً"
    if st == "absent":
        return "bad", os.path.relpath(p, root) + " — المرساةُ تغيّرت، لم يُمَسّ"
    if check:
        return "patched", os.path.relpath(p, root) + " — قابلٌ للتبديل (فحصٌ فقط)"
    tmp = p + ".tmp-rebrand"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(new)
    os.replace(tmp, p)
    return "patched", os.path.relpath(p, root) + " — Usage: weaver core"


def rebrand_help(text):
    """(النصُّ الجديد، عددُ المواضع)."""
    return RX.subn(NEW, text)


def targets(root):
    out = [os.path.join(root, "dist", "cli-startup-metadata.json")]
    out += sorted(glob.glob(os.path.join(root, "dist", "help-*.mjs")))
    return [p for p in out if os.path.isfile(p)]


def _literal_sub(text):
    n = 0
    for a, b in LITERALS:
        n += text.count(a)
        text = text.replace(a, b)
    return text, n


def patch_file(path_, check=False, literal=False):
    """(الحالة، العدد، الرسالة). الحالات: patched · already · bad."""
    try:
        src = open(path_, encoding="utf-8", errors="strict").read()
    except Exception as e:
        return "bad", 0, "تعذّرت القراءة: %s" % type(e).__name__
    new, n = _literal_sub(src) if literal else rebrand_help(src)
    if n == 0:
        return "already", 0, "لا شيءَ يُبدَّل"
    if path_.endswith(".json"):
        try:
            json.loads(new)
        except Exception:
            return "bad", 0, "الناتجُ ليس JSON صالحاً — لم يُكتب"
    if check:
        return "patched", n, "قابلٌ للتبديل (فحصٌ فقط)"
    try:
        tmp = path_ + ".tmp-rebrand"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(new)
        os.replace(tmp, path_)
    except Exception as e:
        return "bad", 0, "تعذّرت الكتابة: %s" % type(e).__name__
    return "patched", n, "بُدِّل"


def apply(root, check=False, say=print):
    """طبّقه على المحرّك. يعيد True إن لم يفشل شيء. لا يرفع استثناءً."""
    try:
        files = targets(root)
        if not files:
            say("    ؟ نصوصُ المساعدة غيرُ موجودة — تغيّر الإصدار؟ لم يُمَسّ شيء")
            return False
        good = True
        lits = sorted({q for g in LITERAL_GLOB
                       for q in glob.glob(os.path.join(root, g))})
        for p, lit in [(f, False) for f in files] + [(f, True) for f in lits]:
            st, n, msg = patch_file(p, check, literal=lit)
            mark = {"patched": "✓", "already": "·", "bad": "✗"}[st]
            say("    %s %s  — %s%s" % (mark, os.path.relpath(p, root), msg,
                                      (" (%d)" % n) if n else ""))
            good = good and st != "bad"
        # سطرُ Usage الحيّ — تجميليّ: فشلُه يُقال ولا يُفشل الباقي.
        try:
            st, msg = patch_usage(root, check)
            say("    %s %s" % ({"patched": "✓", "already": "·",
                                "bad": "؟"}[st], msg))
        except Exception as e:
            say("    ؟ سطرُ Usage: %s" % type(e).__name__)
        return good
    except Exception as e:
        say("    ✗ %s: %s" % (type(e).__name__, str(e)[:120]))
        return False


if __name__ == "__main__":
    if not sys.argv[1:]:
        print(__doc__)
        sys.exit(2)
    _root = os.path.abspath(sys.argv[1])
    print("  نصوصُ المساعدة: openclaw ⟶ weaver core")
    sys.exit(0 if apply(_root, check="--check" in sys.argv) else 1)
