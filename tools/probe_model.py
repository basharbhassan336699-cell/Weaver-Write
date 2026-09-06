"""
tools/probe_model.py — قياس مباشر لخادم النموذج (لا يمسّ النظام إطلاقاً)
=====================================================================
ملف فحص مستقل تماماً: لا يستورد الطبقات، ولا يكتب أي ملف، ولا يعدّل أي شيء.
يرسل نداءات مباشرة إلى نموذجك (أياً كان المزوّد: DeepSeek / OpenAI / Anthropic /
OpenAI-compatible) ويطبع رد الخادم الخام حرفياً + تشخيصاً محايداً.

ما يطبعه:
  • رد الخادم الخام (JSON كما أرسله المزوّد — كلماتهم لا كلماتي)
  • finish_reason (سبب توقّف النموذج)
  • usage (كم توكن استهلك: مطالبة/إكمال/تفكير)
  • هل النص في content أم في حقلٍ آخر (reasoning_content) — عام لأي نموذج مفكِّر
  • تجربة بسقفَي توكن مختلفين (3000 ثم 8000) لكشف أثر السقف

الغرض: حسم سبب «الرد الفارغ» بالدليل الخام، لأي مزوّد — لا اتهام لنموذج بعينه.

التشغيل في Termux:
    cd ~/Weaver-Write
    python tools/probe_model.py
"""
import os
import sys
import json
import time
import urllib.request

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

PROMPT = (
    "أنت باحث أكاديمي خبير. صمّم هيكلاً بحثياً متكاملاً وعميقاً ومفصّلاً "
    "لموضوع: «الإعجاز العلمي في القرآن الكريم». اجعله بمستويات (فصل/مبحث/مطلب/"
    "فرع) مع مقدمة مقسّمة، وأشِر إلى الآيات بنصّها حيث يناسب، واختم بقائمة مصادر "
    "ومراجع بأسماء محدّدة. اكتب بالعربية الفصحى."
)


def _is_anthropic():
    if PROVIDER in ("anthropic", "claude"):
        return True
    return "anthropic.com" in BASE.lower()


def _one_call(max_tokens, extra=None):
    """نداء واحد؛ يعيد (elapsed, http_error, raw_dict). extra=بارامترات إضافية."""
    anthropic = _is_anthropic()
    if anthropic:
        url = BASE.rstrip("/") + "/messages"
        headers = {"x-api-key": KEY, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        payload = {"model": MODEL or "claude-3", "max_tokens": max_tokens,
                   "temperature": 0.4,
                   "messages": [{"role": "user", "content": PROMPT}]}
    else:
        url = BASE.rstrip("/") + "/chat/completions"
        headers = {"authorization": f"Bearer {KEY}",
                   "content-type": "application/json"}
        payload = {"model": MODEL, "temperature": 0.4, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": PROMPT}]}
    if extra:
        payload.update(extra)
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            raw = r.read().decode("utf-8")
        return time.time() - t0, None, json.loads(raw)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        return time.time() - t0, f"HTTP {e.code}: {body[:800]}", None
    except Exception as e:
        return time.time() - t0, f"{type(e).__name__}: {e}", None


def _dig(d, *keys):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return None


def _extract(data):
    """يعيد (content, reasoning, finish_reason, usage) لأي مزوّد."""
    if not isinstance(data, dict):
        return "", "", None, None
    usage = data.get("usage")
    # Anthropic
    if "content" in data and isinstance(data["content"], list):
        txt = "".join(b.get("text", "") for b in data["content"]
                      if isinstance(b, dict))
        return txt, "", data.get("stop_reason"), usage
    # OpenAI-compatible
    choices = data.get("choices") or []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        # نماذج مفكِّرة (DeepSeek-Reasoner وغيرها) تضع التفكير هنا
        reasoning = (msg.get("reasoning_content") or msg.get("reasoning")
                     or "")
        return content, reasoning, choices[0].get("finish_reason"), usage
    return "", "", None, usage


def _report(tag, max_tokens, extra=None):
    print("\n" + "=" * 60)
    print(f"[{tag}] نداء واحد — max_tokens={max_tokens}"
          + (f" + {extra}" if extra else ""))
    print("=" * 60)
    dt, err, data = _one_call(max_tokens, extra)
    if err:
        print(f"الزمن: {dt:.1f}s — فشل: {err}")
        print("→ خطأ من المزوّد/الشبكة (ليس من الطبقات).")
        return
    content, reasoning, finish, usage = _extract(data)
    print(f"الزمن            : {dt:.1f} ثانية")
    print(f"finish_reason    : {finish}")
    print(f"usage            : {json.dumps(usage, ensure_ascii=False)}")
    print(f"طول content      : {len(content or '')} حرف")
    print(f"طول reasoning    : {len(reasoning or '')} حرف "
          f"{'(النص هنا وليس في content!)' if reasoning and not (content or '').strip() else ''}")
    print("-" * 60)
    print("رد الخادم الخام (أول ~1500 حرف — كلمات المزوّد لا كلماتي):")
    print(json.dumps(data, ensure_ascii=False)[:1500])
    print("-" * 60)
    if (content or "").strip():
        print(f"أول ~500 حرف من content:\n{content[:500]}")
    elif (reasoning or "").strip():
        print(f"content فارغ، لكن reasoning يحوي نصاً. أوله:\n{reasoning[:500]}")
    else:
        print("لا content ولا reasoning — رد فارغ فعلاً.")


def main():
    print("=" * 60)
    print("فحص خادم النموذج — رد خام + تشخيص محايد (أي مزوّد)")
    print("=" * 60)
    print(f"BASE_URL : {BASE}")
    print(f"MODEL    : {MODEL or '(غير محدّد)'}")
    print(f"PROVIDER : {PROVIDER or '(openai-compatible)'}")
    print(f"KEY set  : {'نعم' if KEY else 'لا'}")
    if not KEY:
        print("لا يوجد WEAVER_API_KEY في config/.env — لا يمكن الفحص.")
        return
    # علاجان مرشّحان:
    # (ج) ميزانية توكن كبيرة → هل يُنهي التفكير ويكتب content؟
    _report("ج — سقف كبير", 16000)
    # (د) تقليل التفكير عبر reasoning_effort=low (إن دعمه المزوّد) → سرعة + content
    _report("د — تقليل التفكير", 6000, extra={"reasoning_effort": "low"})
    print("\n" + "=" * 60)
    print("خلاصة العلاج (سأطبّقه في عميل النموذج core/llm — مكان واحد يصلح الكل):")
    print("• إن امتلأ content في [ج] → نرفع سقف التوكن للنماذج المفكِّرة.")
    print("• إن امتلأ content في [د] بسرعة → نمرّر reasoning_effort=low (الأفضل: سريع).")
    print("• إن بقي content فارغاً والتفكير ممتلئ → نقرأ reasoning_content كشبكة أمان.")
    print("=" * 60)


if __name__ == "__main__":
    main()
