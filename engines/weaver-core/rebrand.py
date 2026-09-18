# -*- coding: utf-8 -*-
"""إعادةُ التسمية: OpenClaw ⟶ Weaver Write — بدقّةٍ لا تكسر التشغيل.

الكلمةُ تظهر في الحزمة ٦٢٩٣ مرّة، وليست كلُّها سواء. ثلاثةُ أصنافٍ لا رابعَ
لها، وقياسُها من الحزمة نفسِها:

  ١) علامةٌ يراها المستخدم   «OpenClaw 2026.9.4»          ⟵ تُبدَّل
  ٢) مُعرِّفٌ في الكود        isSupportedOpenClawNodeVersion ⟵ لا تُمَسّ
  ٣) اسمٌ يحلُّه التشغيل      @openclaw/ai · .openclaw/ ·
                             openclaw.json · OPENCLAW_AGENT_DIR ⟵ لا تُمَسّ

الصنفُ الثالث هو القاتل: `@openclaw/*` اسمُ حزمةٍ في node_modules — تغييرُه
يعني ألّا يجدها node، فينهار كلُّ شيء. و`.openclaw/` مجلّدُ الإعدادات،
و`OPENCLAW_*` متغيّراتُ البيئة. وهذه كلُّها بحروفٍ صغيرةٍ أو كبيرةٍ بالكامل،
فتمييزُها عن العلامة سهلٌ وقاطع.

والقاعدةُ المطبَّقة: يُبدَّل الرمزُ `OpenClaw` بحروفه هذه تماماً، وبشرط ألّا
يسبقَه ولا يتلوَه حرفُ مُعرِّف `[A-Za-z0-9_$]`. فـ«OpenClaw 2026» تُبدَّل
لأنّ قبلها مسافةً وبعدها مسافة؛ و«...OpenClawNode...» لا تُبدَّل لأنّ بعدها
`N`؛ و`@openclaw` و`OPENCLAW_` خارجَ الرمز أصلاً.

    python3 rebrand.py <مجلّد الحزمة> [--check]
"""
import os
import re
import sys

OLD = "OpenClaw"
NEW = "Weaver Write"

# الرمزُ وحده: لا يسبقه ولا يتلوه حرفُ مُعرِّف.
#
# ولحرفٍ سابقٍ استثناءان قِيسا من الحزمة لا خُمِّنا، وكلاهما كان يُفلت
# العلامةَ من إعادة التسمية:
#   ١) هروبٌ نصّيّ: في JSON يُكتب السطرُ الجديد حرفين «\» و«n»، فالحرفُ
#      السابق لـOpenClaw هو «n» — وهو حرفُ مُعرِّف في نظر الحارس. وهكذا بقي
#      «\nOpenClaw 2026.9.4» في cli-startup-metadata.json، وهو نصُّ المساعدة
#      المُهيَّأُ مسبقاً الذي يطبعه `--help`. سطرٌ واحدٌ أفلت، فظلّ الاسمُ
#      القديم يظهر للمستخدم رغم أن كلَّ شيءٍ آخر تبدّل.
#   ٢) رموزُ ألوان الطرفية تنتهي بحرف «m» (\u001b[1m)، فيليها الاسمُ مباشرةً.
TOKEN = re.compile(
    r"(?:(?<=\\n)|(?<=\\t)|(?<=\\r)|(?<=[0-9;]m)|(?<![A-Za-z0-9_$]))"
    r"OpenClaw(?![A-Za-z0-9_$])")

EXT = (".mjs", ".js", ".cjs", ".json", ".md", ".mdx", ".txt", ".ts",
       ".sh", ".html", ".css", ".yaml", ".yml", ".webmanifest",
       ".jsonc", ".json5")
SKIP_FILES = ("LICENSE", "THIRD_PARTY_NOTICES.md")
SKIP_DIRS = ("node_modules", ".git")


def rebrand_text(text):
    return TOKEN.sub(NEW, text)


def walk(root):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f in SKIP_FILES or not f.endswith(EXT):
                continue
            yield os.path.join(base, f)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    root = os.path.abspath(argv[0])
    check = "--check" in argv
    if not os.path.isdir(root):
        print(f"ليس مجلّداً: {root}")
        return 2
    files = changed = hits = 0
    guarded = {"pkg": 0, "ident": 0, "env": 0, "dir": 0}
    for p in walk(root):
        files += 1
        try:
            with open(p, "r", encoding="utf-8", errors="strict") as fh:
                src = fh.read()
        except Exception:
            continue
        if OLD not in src and "openclaw" not in src:
            continue
        guarded["pkg"] += len(re.findall(r"@openclaw/", src))
        guarded["ident"] += len(re.findall(
            r"[A-Za-z0-9_$]OpenClaw|OpenClaw[A-Za-z0-9_$]", src))
        guarded["env"] += len(re.findall(r"OPENCLAW_", src))
        guarded["dir"] += len(re.findall(r"\.openclaw\b", src))
        out = rebrand_text(src)
        if out == src:
            continue
        hits += len(TOKEN.findall(src))
        changed += 1
        if not check:
            try:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(out)
            except Exception as e:
                print(f"  تعذّر: {p} — {type(e).__name__}")
    print(f"  فُحص {files} ملفاً")
    print(f"  بُدِّل   {hits} موضعَ علامةٍ ظاهرة في {changed} ملفاً"
          + ("  (فحصٌ فقط، لم يُكتب شيء)" if check else ""))
    print("  وحُمي:")
    print(f"     {guarded['pkg']:6d}  @openclaw/*        اسمُ حزمةٍ يحلُّه node")
    print(f"     {guarded['ident']:6d}  OpenClawXxx        مُعرِّفٌ في الكود")
    print(f"     {guarded['env']:6d}  OPENCLAW_*         متغيّرُ بيئة")
    print(f"     {guarded['dir']:6d}  .openclaw          مجلّدُ الإعدادات")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
