# -*- coding: utf-8 -*-
"""رقعةُ نقلٍ واحدة: `/tmp` المكتوبُ حرفياً ⟶ `os.tmpdir()`.

المشكلة، مقيسةً من تشغيلٍ حقيقيٍّ على تيرمكس لا من ظنّ:

    EACCES: permission denied, mkdir '/tmp/openclaw-state-locks-10366'

والسببُ سطرٌ واحد، مكرَّرٌ في ملفّين:

    state-database-coordinator-DBce2evc.mjs:25
    managed-handoff-runtime.mjs:9846
        function resolveStateLifecycleRuntimeDirectory() {
          return process.platform === "win32"
            ? path.join(os.homedir(), "AppData", "Local", "…", "locks")
            : "/tmp";                       ← مكتوبٌ بالحرف
        }

وما عملُ هذا المجلّد؟ يحمل قفلاً يمنع عمليتين من تعديل قاعدة الحالة معاً —
احتياطٌ ضروريّ. واسمُ ملفّ القفل يحمل بصمةَ مسار قاعدة البيانات
(`sha256(dbPath)[:8]`)، فلا تتصادم نسختان مهما اشتركتا في المجلّد.

**ولماذا لا يوضع في مجلّد حالتنا؟** لأنّ القفلَ يحرس عملياتِ *دورة حياة*
قاعدة الحالة — إنشاءها وترحيلها وحذفها. فلو سكن داخل المجلّد الذي يحرسه
لأتلف نفسَه في أوّل عمليةٍ تُعيد بناءَ ذلك المجلّد. فوجودُه خارجَه تصميمٌ
صحيحٌ لا عيب. العيبُ هو تثبيتُ `/tmp` بعينه.

وعلى أندرويد `/tmp` موجودٌ لكنّه للقراءة فقط — التطبيقاتُ محبوسةٌ في
صندوقها. و`TMPDIR` لا ينفع لأنّ السطر لا يقرؤه أصلاً.

والتصحيح `os.tmpdir()`:
  · على لينكس وماك تُعيد `/tmp` نفسَه ⟶ **لا يتغيّر شيءٌ هناك**
  · وعلى تيرمكس تُعيد `$PREFIX/tmp` وهو قابلٌ للكتابة، وخارجَ مجلّد حالتنا
    فيبقى التصميمُ سليماً
  · و`os` مستوردٌ في الملفّين أصلاً، فلا استيرادَ يُضاف

أي أنّه تصحيحُ **نقلٍ** لا تغييرُ سلوك: هو ما كان ينبغي أن يُكتب ابتداءً.

وهذه الرقعةُ لا تُعدّل شيئاً لا تفهمه: تبحث عن السطر بنصّه الكامل، فإن لم
تجده بالعدد المتوقَّع توقّفت وأخبرت — ولا تخمّن. وهي عديمةُ الأثر إن أُعيد
تشغيلُها (تتحقّق أنّ الرقعةَ مطبَّقةٌ وتخرج).

    python3 patch_portability.py <مجلّد المحرّك> [--check]
"""
import os
import sys

# تُطابَق **البنية** لا الاسم. أوّلُ كتابةٍ لهذه الرقعة طابقت السطرَ كاملاً
# وفيه اسمُ العلامة "Weaver Write"، فنجحت على نسخةٍ مُعادةِ التسمية وفشلت
# على الأصل — وهي هشاشةٌ كشفها الفحصُ لا التفكير. فصارت تُمسك الدالّةَ
# باسمها، ثمّ تُبدّل نهايةَ سطر `return` وحدها، أيّاً كان ما بينهما.
import re as _re

GUARD = "function resolveStateLifecycleRuntimeDirectory()"
# داخل الدالّة: ‎…‎ : "/tmp";  ⟵ الفرعُ غيرُ الويندوزيّ وحده
TAIL_OLD = _re.compile(r'(:\s*)"/tmp";')
TAIL_NEW = r'\1os.tmpdir();'
DONE = "os.tmpdir();"
WINDOW = 400          # حرفاً بعد اسم الدالّة — جسمُها أقصرُ من ذلك بكثير

TARGETS = ("dist/state-database-coordinator-DBce2evc.mjs",
           "dist/managed-handoff-runtime.mjs")


def patch_file(path_, check=False):
    """(الحالة، الرسالة). الحالات: patched · already · missing · shape."""
    if not os.path.isfile(path_):
        return "missing", "الملفّ غير موجود"
    try:
        src = open(path_, encoding="utf-8", errors="strict").read()
    except Exception as e:
        return "missing", f"تعذّرت القراءة: {type(e).__name__}"
    if src.count(GUARD) != 1:
        return "shape", (f"الدالّةُ المستهدَفة ظهرت {src.count(GUARD)} مرّةً "
                         "لا مرّةً واحدة — تغيّر الإصدار")
    i = src.index(GUARD)
    body = src[i:i + WINDOW]
    if DONE in body and not TAIL_OLD.search(body):
        return "already", "مرقوعٌ مسبقاً"
    hits = TAIL_OLD.findall(body)
    if len(hits) != 1:
        return "shape", f'`: "/tmp";` ظهر {len(hits)} مرّةً داخل الدالّة'
    if check:
        return "patched", "قابلٌ للرقع (فحصٌ فقط)"
    try:
        patched = src[:i] + TAIL_OLD.sub(TAIL_NEW, body, count=1) \
            + src[i + WINDOW:]
        open(path_, "w", encoding="utf-8").write(patched)
    except Exception as e:
        return "shape", f"تعذّرت الكتابة: {type(e).__name__}"
    return "patched", "رُقع"


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    root = os.path.abspath(argv[0])
    check = "--check" in argv
    if not os.path.isdir(root):
        print(f"ليس مجلّداً: {root}")
        return 2
    print("  رقعةُ النقل: /tmp ⟶ os.tmpdir()")
    ok = done = 0
    for rel in TARGETS:
        state, msg = patch_file(os.path.join(root, rel), check)
        mark = {"patched": "✓", "already": "·", "missing": "؟",
                "shape": "✗"}[state]
        print(f"    {mark} {rel}  — {msg}")
        if state in ("patched", "already"):
            ok += 1
            done += 1 if state == "patched" else 0
    if ok != len(TARGETS):
        print()
        print("  ⚠ لم تُطبَّق الرقعةُ كاملةً. لم يُعدَّل ما لم يُفهَم.")
        print("    المحرّكُ يعمل، لكنّ أوامرَ الحالة قد تفشل على أندرويد بـ")
        print("    EACCES على /tmp. أرسل هذا الخرج ليُعالَج.")
        return 1
    print(f"  تمّت ({done} مُعدَّل، {ok - done} كان مرقوعاً)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
