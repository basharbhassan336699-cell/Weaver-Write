#!/usr/bin/env python3
"""
tools/test_search.py — اختبار محرّكات البحث على جهازك (Termux)
==============================================================
يختبر مباشرةً — على شبكتك أنت — سلسلة البحث كاملةً كما يستخدمها النظام:
  SearXNG الأساسي  ←  SearXNG الاحتياطية (ما تضبطه + المضمّنة)  ←  DuckDuckGo
ثم يحاكي اختيار المحرّك لطلب أخبار حقيقي ويطبع أيها فاز.

لا يعدّل شيئاً. لا ينهار. شغّله:
    python3 tools/test_search.py
    python3 tools/test_search.py "أخبار غزة اليوم"
"""
from __future__ import annotations
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def line(t=""):
    print(t, flush=True)


def head(t):
    line("\n" + "=" * 60)
    line(t)
    line("=" * 60)


def ok(t):   line("  ✅ " + t)
def bad(t):  line("  ❌ " + t)
def info(t): line("  •  " + t)


def main():
    from pipeline.orchestrator import (WeaverOrchestrator as W,
                                       _DEFAULT_SEARXNG_FALLBACKS)
    try:
        from core.llm import keysync
        keysync.load_env()
    except Exception:
        pass

    query = sys.argv[1] if len(sys.argv) > 1 else "أخبار غزة اليوم"
    lang = "ar" if any("؀" <= c <= "ۿ" for c in query) else "en"

    head("اختبار البحث — Weaver Write")
    info(f"الطلب: {query}   (لغة: {lang})")

    # ── ٠) هل SearXNG موجود/مثبّت/يعمل على هذا الجهاز؟ ──
    head("٠) وجود SearXNG على جهازك")
    import shutil
    import socket
    import urllib.parse as _up
    primary0 = os.environ.get("WEAVER_SEARXNG_URL", "").strip() or "http://127.0.0.1:8888"
    pu = _up.urlparse(primary0)
    host, port = pu.hostname or "127.0.0.1", pu.port or (443 if pu.scheme == "https" else 80)
    info(f"العنوان المضبوط: {primary0}")

    # أ) هل مثبّت كبرنامج؟
    installed = []
    for c in ("searxng", "searx", "searxng-run"):
        w = shutil.which(c)
        if w:
            installed.append(w)
    try:
        import importlib
        if importlib.util.find_spec("searx") is not None:
            installed.append("python module: searx")
    except Exception:
        pass
    if installed:
        ok("SearXNG مثبّت: " + ", ".join(installed))
    else:
        info("SearXNG غير مثبّت كبرنامج على الجهاز (طبيعي — ليس جزءاً من Weaver).")

    # ب) هل هناك خادم يستمع على المنفذ؟
    listening = False
    try:
        s = socket.create_connection((host, port), timeout=4)
        s.close()
        listening = True
        ok(f"منفذ {host}:{port} مفتوح — هناك خادم يستمع.")
    except Exception as e:
        bad(f"لا خادم يستمع على {host}:{port} ({type(e).__name__}).")

    # ج) هل يردّ فعلاً بـ JSON صحيح؟
    if listening:
        probe = W._searx_query(primary0, "test", "en", 2)
        if probe is not None:
            ok(f"يردّ بـ JSON صحيح ({len(probe)} نتيجة تجريبية) — SearXNG جاهز فعلاً.")
        else:
            bad("الخادم يستمع لكنه لا يعطي format=json (لن يعمل كمصدر بحث).")
    else:
        info("لتشغيل SearXNG محلياً لاحقاً: ثبّته واضبط WEAVER_SEARXNG_URL=http://127.0.0.1:8888")
    info("ملاحظة: لا يلزم SearXNG إطلاقاً — DuckDuckGo (القسم ٤) يعمل بلا خادم.")

    # ── نية الأخبار + حقن التاريخ ──
    head("١) كشف نية الأخبار وحقن التاريخ")
    is_rec = W._is_recency_query(query)
    (ok if is_rec else info)(f"طلب أخبار/حداثة؟  {is_rec}")
    if is_rec:
        aug = W._augment_query_with_date(query, lang)
        info(f"الاستعلام بعد حقن التاريخ:  {aug}")
        eff_query = aug
        sx_time, ddg_df = "week", "w"
    else:
        eff_query, sx_time, ddg_df = query, None, None

    # ── SearXNG الأساسي ──
    head("٢) SearXNG الأساسي")
    primary = os.environ.get("WEAVER_SEARXNG_URL", "").strip() or "http://127.0.0.1:8888"
    info(f"العنوان: {primary}"
         + ("  (محلي)" if "127.0.0.1" in primary or "localhost" in primary else "  (بعيد)"))
    t = time.time()
    r = W._searx_query(primary, eff_query, lang, 6, time_range=sx_time)
    dt = time.time() - t
    winner = None
    if r:
        ok(f"نجح ({dt:.1f}ث): {len(r)} نتيجة")
        for x in r[:3]:
            info(f"   - {(x.get('title') or '')[:60]}")
        winner = ("searxng:" + primary, r)
    else:
        bad(f"لا نتائج ({dt:.1f}ث) — غير مشغّل محلياً أو لا يدعم format=json")

    # ── SearXNG الاحتياطية (env) ──
    head("٣) SearXNG الاحتياطية")
    env_fb = [u.strip() for u in
              os.environ.get("WEAVER_SEARXNG_FALLBACKS", "").split(",") if u.strip()]
    if env_fb:
        info("من WEAVER_SEARXNG_FALLBACKS: " + ", ".join(env_fb))
    else:
        info("لم تضبط WEAVER_SEARXNG_FALLBACKS (اختياري).")
    info("المضمّنة في النظام (تلقائياً بعد DuckDuckGo):")
    for fb in _DEFAULT_SEARXNG_FALLBACKS:
        t = time.time()
        rr = W._searx_query(fb, eff_query, lang, 6, timeout=6, time_range=sx_time)
        dt = time.time() - t
        if rr:
            ok(f"{fb} → {len(rr)} نتيجة ({dt:.1f}ث)")
            if winner is None:
                winner = ("searxng-default:" + fb, rr)
        else:
            bad(f"{fb} → لا JSON/محجوب ({dt:.1f}ث)")

    # ── DuckDuckGo ──
    head("٤) DuckDuckGo (بلا خادم — المحرّك الموثوق)")
    t = time.time()
    ddg = W._ddg_search(eff_query, lang, 6, df=ddg_df)
    dt = time.time() - t
    if ddg:
        ok(f"نجح ({dt:.1f}ث): {len(ddg)} نتيجة")
        for x in ddg[:3]:
            info(f"   - {(x.get('title') or '')[:60]}  | {x.get('url','')[:45]}")
    else:
        bad(f"لا نتائج ({dt:.1f}ث) — تحقّق من الإنترنت/DNS (شغّل tools/diagnose.py)")

    # ── محاكاة اختيار المحرّك بترتيب النظام ──
    head("٥) أي محرّك سيخدم هذا الطلب فعلياً؟")
    used, results = None, None
    if winner:                                   # SearXNG (أساسي أو env)
        used, results = winner
    elif ddg:                                    # ثم DuckDuckGo
        used, results = "duckduckgo", ddg
    else:                                        # ثم المضمّنة (جُرّبت أعلاه)
        for fb in _DEFAULT_SEARXNG_FALLBACKS:
            rr = W._searx_query(fb, eff_query, lang, 6, timeout=6, time_range=sx_time)
            if rr:
                used, results = "searxng-default:" + fb, rr
                break
    if results:
        if is_rec:
            results = W._sort_results_by_recency(results)
            info("طُبّق ترتيب الأحدث أولاً.")
        ok(f"المحرّك الفائز: {used}  —  {len(results)} مصدر")
        for x in results[:5]:
            info(f"   • {(x.get('title') or '')[:65]}")
    else:
        bad("لا محرّك أرجع نتائج — سيكتب النظام من المعرفة العامة مع تنويه.")

    head("انتهى — أرسل لي كل ما فوق")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print("خطأ غير متوقع في الاختبار:")
        traceback.print_exc()
