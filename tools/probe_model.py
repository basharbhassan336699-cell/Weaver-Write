"""
tools/probe_model.py — قياس مباشر لخادم النموذج (لا يمسّ النظام إطلاقاً)
=====================================================================
ملف فحص مستقل تماماً: لا يستورد الطبقات، ولا يكتب أي ملف، ولا يعدّل أي شيء.
يرسل *نداءً واحداً نظيفاً* إلى نموذجك (كما يفعل OpenClaw) ويطبع:
  • الزمن بالثواني
  • هل رجع الرد فارغاً أم لا
  • طول الرد وعدد أسطره
  • أول ~600 حرف من الرد

الهدف: هل يردّ نموذجك على نداءٍ واحد بسرعة وبعمق؟
  - نعم  → المشكلة في تعدّد نداءات نظامي (نُصلحها بأمان).
  - فارغ/بطيء → المشكلة في الخادم/الإعدادات (نُعالجها هناك، لا في الطبقات).

التشغيل في Termux:
    cd ~/Weaver-Write
    python tools/probe_model.py
"""
import os
import sys
import json
import time
import urllib.request

# نقرأ نفس إعدادات النظام (config/.env) دون تشغيل أي طبقة
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    from config import keysync
    keysync.load_env()
except Exception as e:
    print(f"[تنبيه] تعذّر تحميل config/.env تلقائياً: {e}")

KEY = os.environ.get("WEAVER_API_KEY", "").strip()
BASE = os.environ.get("WEAVER_BASE_URL", "http://127.0.0.1:8848/v1").strip()
MODEL = os.environ.get("WEAVER_MODEL", "").strip()
PROVIDER = os.environ.get("WEAVER_PROVIDER", "").strip().lower()

# طلب واحد قوي — نفس نوع ما يُرسل في OpenClaw
PROMPT = (
    "أنت باحث أكاديمي خبير. صمّم هيكلاً بحثياً متكاملاً وعميقاً ومفصّلاً "
    "لموضوع: «الإعجاز العلمي في القرآن الكريم». اجعله بمستويات (فصل/مبحث/مطلب/"
    "فرع) مع مقدمة مقسّمة (تمهيد، إشكالية، أهداف، منهج)، وأشِر إلى الآيات بنصّها "
    "حيث يناسب، واختم بقائمة مصادر ومراجع بأسماء محدّدة. اكتب بالعربية الفصحى."
)


def _is_anthropic():
    if PROVIDER in ("anthropic", "claude"):
        return True
    return "anthropic.com" in BASE.lower()


def main():
    print("=" * 60)
    print("فحص خادم النموذج — نداء واحد مباشر")
    print("=" * 60)
    print(f"BASE_URL : {BASE}")
    print(f"MODEL    : {MODEL or '(غير محدّد)'}")
    print(f"PROVIDER : {PROVIDER or '(openai-compatible)'}")
    print(f"KEY set  : {'نعم' if KEY else 'لا'}")
    print("-" * 60)
    if not KEY:
        print("لا يوجد مفتاح WEAVER_API_KEY في config/.env — لا يمكن الفحص.")
        return

    anthropic = _is_anthropic()
    if anthropic:
        url = BASE.rstrip("/") + "/messages"
        headers = {"x-api-key": KEY, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        payload = {"model": MODEL or "claude-3", "max_tokens": 3000,
                   "temperature": 0.4,
                   "messages": [{"role": "user", "content": PROMPT}]}
    else:
        url = BASE.rstrip("/") + "/chat/completions"
        headers = {"authorization": f"Bearer {KEY}",
                   "content-type": "application/json"}
        payload = {"model": MODEL, "temperature": 0.4, "max_tokens": 3000,
                   "messages": [{"role": "user", "content": PROMPT}]}

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")

    print("أُرسِل النداء الآن... (انتظر رد النموذج)")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            raw = r.read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        dt = time.time() - t0
        print(f"\n[فشل الاتصال بعد {dt:.1f}s] {type(e).__name__}: {e}")
        print("→ المشكلة في الخادم/الشبكة، لا في الطبقات.")
        return
    dt = time.time() - t0

    if anthropic:
        content = "".join(b.get("text", "") for b in data.get("content", [])
                          if isinstance(b, dict))
    else:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = ""

    content = content or ""
    nlines = len([ln for ln in content.splitlines() if ln.strip()])
    print("\n" + "=" * 60)
    print("النتيجة")
    print("=" * 60)
    print(f"الزمن        : {dt:.1f} ثانية")
    print(f"رد فارغ؟     : {'نعم ← الخادم رجع فارغاً' if not content.strip() else 'لا'}")
    print(f"طول الرد     : {len(content)} حرف / {nlines} سطر")
    print("-" * 60)
    print("أول ~600 حرف من الرد:")
    print(content[:600] if content.strip() else "(لا شيء)")
    print("=" * 60)
    # خلاصة تفسيرية
    if content.strip() and dt <= 90 and nlines >= 8:
        print("الخلاصة: نموذجك يردّ على نداءٍ واحد بسرعة وعمق ✓ →")
        print("         السبب في تعدّد نداءات النظام، ويُصلَح بأمان.")
    elif not content.strip():
        print("الخلاصة: الخادم رجع فارغاً حتى لنداءٍ واحد ✗ →")
        print("         المشكلة في الخادم/الإعدادات (max_tokens/الموديل)،")
        print("         لا في الطبقات.")
    else:
        print("الخلاصة: النموذج بطيء/قصير حتى لنداءٍ واحد →")
        print("         نضبط إعداداته، لا الطبقات.")


if __name__ == "__main__":
    main()
