#!/usr/bin/env python3
"""
tools/diagnose.py — تشخيص Weaver Write على جهازك مباشرة
=======================================================
شغّله على هاتفك (Termux) وأرسل لي كامل المخرجات. لا يعدّل أي شيء —
فقط يفحص كل نقطة قد يفشل عندها البحث أو الكتابة، ويطبع الحقيقة بلا تخمين.

الاستخدام:
    python3 tools/diagnose.py
    python3 tools/diagnose.py "اكتب تقريراً من ٣ صفحات عن تأثير الذكاء الاصطناعي على الأطفال"
"""
from __future__ import annotations
import os
import sys
import time
import traceback

# اجعل جذر المشروع قابلاً للاستيراد
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def line(t=""):
    print(t, flush=True)


def head(t):
    line()
    line("=" * 60)
    line(t)
    line("=" * 60)


def ok(t):
    line("  ✅ " + t)


def bad(t):
    line("  ❌ " + t)


def info(t):
    line("  •  " + t)


# ─────────────────────────────────────────────────────────
# ١. البيئة
# ─────────────────────────────────────────────────────────
def check_env():
    head("١) البيئة")
    info(f"Python: {sys.version.split()[0]}")
    info(f"المنصّة: {sys.platform}")
    pref = os.environ.get("PREFIX", "")
    termux = "com.termux" in pref or os.path.isdir(
        "/data/data/com.termux/files/usr")
    info("Termux/Android: " + ("نعم" if termux else "لا"))
    info(f"مجلد المشروع: {ROOT}")


# ─────────────────────────────────────────────────────────
# ٢. مفتاح النموذج (LLM) — بدونه لا يُكتب شيء
# ─────────────────────────────────────────────────────────
def check_llm():
    head("٢) مفتاح النموذج (LLM)")
    try:
        from core.llm import get_llm_fn
    except Exception as e:
        bad(f"تعذّر استيراد core.llm: {e}")
        return None
    fn = None
    try:
        fn = get_llm_fn()
    except Exception as e:
        bad(f"get_llm_fn فشل: {e}")
        return None
    if fn is None:
        bad("لا يوجد مفتاح مضبوط (WEAVER_API_KEY فارغ) → النظام لن يكتب أي محتوى!")
        info("اضبطه في config/.env أو المتغيّرات: WEAVER_API_KEY, WEAVER_BASE_URL, WEAVER_MODEL")
        return None
    info("المفتاح مضبوط. أختبر اتصالاً حقيقياً بالنموذج…")
    try:
        t = time.time()
        out = fn("قل كلمة: تم", system="أجب بكلمة واحدة.", temperature=0)
        dt = time.time() - t
        if out and out.strip():
            ok(f"النموذج يردّ ({dt:.1f}ث): {out.strip()[:60]}")
            return fn
        bad("النموذج ردّ فارغاً — تحقّق من الموديل/الرصيد.")
    except Exception as e:
        bad(f"استدعاء النموذج فشل: {type(e).__name__}: {str(e)[:200]}")
        info("غالباً: مفتاح خاطئ، أو BASE_URL خاطئ، أو لا إنترنت، أو الموديل غير متاح.")
    return None


# ─────────────────────────────────────────────────────────
# ٣. الإنترنت الأساسي
# ─────────────────────────────────────────────────────────
def _get(url, timeout=15):
    import urllib.request
    ua = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36")
    req = urllib.request.Request(url, headers={"User-Agent": ua,
                                               "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def check_internet():
    head("٣) الإنترنت الأساسي")
    for url in ("https://example.com", "https://duckduckgo.com"):
        try:
            st, body = _get(url, 15)
            ok(f"{url} → HTTP {st} ({len(body)} حرف)")
        except Exception as e:
            bad(f"{url} → {type(e).__name__}: {str(e)[:160]}")


# ─────────────────────────────────────────────────────────
# ٤. المكتبات الاختيارية
# ─────────────────────────────────────────────────────────
def check_libs():
    head("٤) المكتبات الاختيارية (تحسّن الجودة، غير إجبارية)")
    for m, why in (("curl_cffi", "انتحال بصمة متصفح — يتجاوز حجب البوتات"),
                   ("trafilatura", "تنظيف الصفحة إلى نصّ مقال"),
                   ("bs4", "تحليل HTML"),
                   ("pdfplumber", "قراءة PDF نصّي"),
                   ("pytesseract", "OCR للصور/الـPDF الممسوح")):
        try:
            __import__(m)
            ok(f"{m}: مثبّت ({why})")
        except Exception:
            info(f"{m}: غير مثبّت — {why} (يتدهور بأمان)")


# ─────────────────────────────────────────────────────────
# ٥. البحث في الويب — DuckDuckGo مباشر + SearXNG
# ─────────────────────────────────────────────────────────
def check_search(query):
    head("٥) البحث في الويب")
    from pipeline.orchestrator import WeaverOrchestrator as W

    # 5a) نقطة DuckDuckGo الخام — نطبع الخطأ الحقيقي إن وُجد
    import urllib.parse
    ep = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(
        {"q": query})
    info("أفحص نقطة DuckDuckGo مباشرة…")
    try:
        st, body = _get(ep, 20)
        has = "result__a" in body
        ok(f"DDG HTTP {st}, حجم {len(body)}, فيه نتائج: {'نعم' if has else 'لا'}")
    except Exception as e:
        bad(f"DDG الخام: {type(e).__name__}: {str(e)[:200]}")

    # 5a-2) DNS-over-HTTPS — يتجاوز عطل DNS في الجهاز (يترجم عبر 1.1.1.1 بالـIP)
    info("أفحص DNS-over-HTTPS (الحل لعطل DNS)…")
    try:
        ip = W._doh_resolve("duckduckgo.com")
        if ip:
            ok(f"DoH ترجم duckduckgo.com → {ip} (بلا حاجة لـDNS النظام)")
        else:
            bad("DoH لم يُرجع عنواناً — الشبكة قد تحجب 1.1.1.1/8.8.8.8 أيضاً.")
    except Exception as e:
        bad(f"DoH: {type(e).__name__}: {str(e)[:160]}")

    # 5b) الدالة الفعلية _ddg_search
    info("أفحص _ddg_search (نفس ما يستخدمه النظام)…")
    try:
        res = W._ddg_search(query, "ar", 5)
        if res:
            ok(f"_ddg_search أرجع {len(res)} نتيجة:")
            for r in res[:3]:
                info(f"   - {(r['title'] or '')[:55]} | {r['url'][:60]}")
        else:
            bad("_ddg_search أرجع صفراً (لا نتائج).")
    except Exception as e:
        bad(f"_ddg_search رمى استثناءً: {type(e).__name__}: {e}")

    # 5c) SearXNG الافتراضي
    inst = os.environ.get("WEAVER_SEARXNG_URL", "").strip() or "http://127.0.0.1:8080"
    info(f"أفحص SearXNG على {inst}…")
    try:
        res = W._searx_query(inst, query, "ar", 5)
        if res:
            ok(f"SearXNG أرجع {len(res)} نتيجة")
        else:
            info("SearXNG غير متاح (طبيعي إن لم تُشغّل خادماً) — DDG يكفي.")
    except Exception as e:
        info(f"SearXNG: {type(e).__name__}: {str(e)[:120]}")


# ─────────────────────────────────────────────────────────
# ٦. خط الأنابيب الكامل على طلب حقيقي
# ─────────────────────────────────────────────────────────
def check_pipeline(query):
    head("٦) خط الأنابيب الكامل (نفس مسار الواجهة/الطرفية)")
    info(f"الطلب: {query}")
    try:
        from pipeline.orchestrator import run_pipeline_sync, WeaverOrchestrator
        info("وضع المصادر المكتشَف: " + WeaverOrchestrator._sourcing_mode(query))
        steps = []
        t = time.time()
        r = run_pipeline_sync(query, progress=lambda ev: steps.append(ev))
        dt = time.time() - t
        ok(f"اكتمل في {dt:.0f}ث")
        info("الأدوات: " + ", ".join(r.get("tools") or []))
        info("مسار الملف: " + str(r.get("output_path")))
        reply = (r.get("reply") or "").strip()
        info(f"طول الردّ: {len(reply)} حرف")
        line()
        line("  ── أول ٦٠٠ حرف من الناتج ──")
        line("  " + (reply[:600] or "(فارغ)").replace("\n", "\n  "))
        line("  ───────────────────────────")
        # تشخيص سريع للنتيجة
        low = reply.lower()
        if not reply:
            bad("الناتج فارغ → غالباً لا يوجد مفتاح LLM (راجع القسم ٢).")
        elif any(w in reply for w in ("لا مصادر", "no sources", "لم أتمكن",
                                      "cannot", "غير متاح", "أعتذر")):
            bad("الناتج يبدو رفضاً/اعتذاراً — أرسل لي هذا النص كاملاً.")
        else:
            ok("الناتج يحتوي محتوى فعلياً.")
    except Exception:
        bad("خط الأنابيب رمى استثناءً:")
        line(traceback.format_exc())


def main():
    query = (sys.argv[1] if len(sys.argv) > 1 else
             "اكتب تقريراً قصيراً عن تأثير الذكاء الاصطناعي على الأطفال")
    head("تشخيص Weaver Write — انسخ كل المخرجات وأرسلها")
    check_env()
    check_llm()
    check_internet()
    check_libs()
    check_search(query)
    check_pipeline(query)
    head("انتهى التشخيص — أرسل لي كل ما فوق")


if __name__ == "__main__":
    main()
