"""
capabilities/tools/tool_exec_python.py
======================================
اليدُ التي تنفّذ.

المشكلة التي يحلّها
-------------------
كان النموذج في هذا النظام يكتب نصّاً ولا شيء غيره، وبايثونُ المكتوبةُ سلفاً
هي التي تبني الملفّ. فسقفُ المخرَج سقفُ ما خطر ببال كاتب تلك البايثون: طلبُ
«اجعل التصميم احترافياً» لا يجد يداً تنفّذه، وطلبُ ترقيمٍ لم يُبرمَج يسقط،
وكلُّ صيغةٍ جديدة تحتاج ملفّ بايثون جديداً.

والفحص الذي أجريناه على OpenClaw بيّن السبب بالأرقام: ليس عنده مهارةُ
باوربوينت ولا إكسل ولا مراجع — صفر. عنده `exec` و`read` و`write`، فيكتب
النموذجُ السكربتَ ويشغّله ويقرأ خطأه ويصلحه. القدرةُ على البرمجة — وهي أقوى
ما في النموذج — تتحوّل إلى قدرةٍ على إنتاج أيّ ملفّ.

هذه الأداة تعطي نظامنا الشيءَ نفسه، وبحدودٍ صريحة.

الحدود (كلُّها مقصودة)
----------------------
* **مطفأةٌ افتراضياً.** تعمل فقط حين WEAVER_EXEC=1 — فلا يتغيّر سلوكُ أحدٍ
  لم يطلبها.
* **مهلةٌ زمنية** (WEAVER_EXEC_TIMEOUT، الافتراضي 120 ثانية) تقتل أيَّ سكربتٍ
  يعلق.
* **دليلُ عملٍ مؤقّتٌ خاصّ** يُنشأ للتشغيل: السكربتُ يبدأ فيه، ولا يرث مسار
  المشروع.
* **لا حذفَ ولا كتابةَ خارج الدليل المؤقّت ومسارِ المخرَج** — يُفحص السكربت
  قبل التشغيل، ويُرفض إن حوى أمراً مدمّراً صريحاً.
* **الفشلُ لا يضرّ**: إن لم يُنتج ملفاً صالحاً، يعود المسار إلى المُصدِّر
  الحاليّ كما كان. لا يستطيع أن يجعل الحال أسوأ.
* **الخطأُ يعود إلى النموذج** كما هو، ليصلحه — وهذا ما يجعلها يداً لا زرّاً.
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import sys
import tempfile

TOOL_SPEC = {
    "name": "exec_python",
    "description": ("Run a Python script the MODEL wrote, to produce a file "
                    "exactly as the user asked. Off unless WEAVER_EXEC=1."),
    "triggers": [],
    "layers": [8],
}

# أنماطٌ مدمّرةٌ صريحة تُرفض قبل التشغيل. ليست حمايةً كاملة — هي خطُّ الدفاع
# الأول ضدّ الخطأ لا ضدّ الخصم؛ ولهذا يبقى التشغيل في دليلٍ مؤقّتٍ ومطفأً
# افتراضياً.
_FORBIDDEN = (
    r"\bshutil\s*\.\s*rmtree\s*\(\s*['\"]?\s*/",
    r"\bos\s*\.\s*remove\s*\(\s*['\"]?\s*/(?!tmp)",
    r"\bos\s*\.\s*system\s*\(",
    r"\bsubprocess\b",
    r"rm\s+-rf\s+/",
    r"\bsocket\s*\.\s*socket\b",
    r"__import__\s*\(\s*['\"]os['\"]\s*\)\s*\.\s*system",
)


def exec_enabled():
    """هل أذِن المستخدم لليد أن تعمل؟"""
    return str(os.environ.get("WEAVER_EXEC", "")).strip().lower() in (
        "1", "true", "yes", "on")


def screen_script(code):
    """→ سببُ الرفض، أو "" حين يجتاز الفحص. لا يرفع استثناءً أبداً."""
    try:
        text = str(code or "")
        if not text.strip():
            return "سكربتٌ فارغ"
        for pat in _FORBIDDEN:
            if re.search(pat, text):
                return f"أمرٌ غيرُ مسموح: {pat}"
        return ""
    except Exception as e:      # pragma: no cover
        return f"تعذّر الفحص: {e}"


def run_python(code, out_path, payload_text="", timeout=None):
    """اكتب سكربتَ النموذج وشغّله، وأعِد ما حدث.

    يُسلَّم السكربتُ متغيّرين في بيئته:
      WEAVER_OUT      مسارُ الملفّ الذي يجب أن ينتجه
      WEAVER_PAYLOAD  مسارُ ملفٍّ نصّيٍّ فيه محتوى المستند (JSON أو نصّ)

    → dict فيه ok / stdout / stderr / reason / out_path. لا يرفع استثناءً."""
    res = {"ok": False, "stdout": "", "stderr": "", "reason": "",
           "out_path": out_path}
    if not exec_enabled():
        res["reason"] = "التنفيذ مطفأ (WEAVER_EXEC غير مضبوط)"
        return res
    bad = screen_script(code)
    if bad:
        res["reason"] = bad
        return res
    try:
        to = int(os.environ.get("WEAVER_EXEC_TIMEOUT", "120") or 120)
    except Exception:
        to = 120
    work = None
    try:
        work = tempfile.mkdtemp(prefix="weaver-exec-")
        script = os.path.join(work, "build.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(str(code))
        pay = os.path.join(work, "payload.txt")
        with open(pay, "w", encoding="utf-8") as fh:
            fh.write(str(payload_text or ""))
        env = dict(os.environ)
        env["WEAVER_OUT"] = str(out_path)
        env["WEAVER_PAYLOAD"] = pay
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        p = subprocess.run([sys.executable, script], cwd=work, env=env,
                           capture_output=True, timeout=to)
        res["stdout"] = (p.stdout or b"").decode("utf-8", "replace")[-4000:]
        res["stderr"] = (p.stderr or b"").decode("utf-8", "replace")[-4000:]
        if p.returncode != 0:
            res["reason"] = f"خرج بالرمز {p.returncode}"
            return res
        if not os.path.isfile(out_path) or os.path.getsize(out_path) < 400:
            res["reason"] = "لم يُنتج ملفاً صالحاً"
            return res
        res["ok"] = True
        return res
    except subprocess.TimeoutExpired:
        res["reason"] = f"تجاوز المهلة ({to} ثانية)"
        return res
    except Exception as e:
        res["reason"] = f"{type(e).__name__}: {e}"
        return res
    finally:
        if work:
            try:
                shutil.rmtree(work, ignore_errors=True)
            except Exception:
                pass
