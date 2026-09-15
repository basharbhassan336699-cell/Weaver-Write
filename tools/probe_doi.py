# -*- coding: utf-8 -*-
"""
tools/probe_doi.py — ما الذي يعود فعلاً من رابط DOI؟
=====================================================
ثمانية روابط من ناشرين مختلفين أعادت 140 حرفاً بالضبط — أي ردّاً ثابتاً لا
صفحةَ بحث. هذه الأداة تكشف ما هو: ترى ترويسات HTTP الخام، وسلسلة التحويل،
ونصّ ما أعاده كل مسارٍ من مسارات الجالب على حدة، فيُعرف أين ينقطع الخيط.

    python tools/probe_doi.py                      # على رابطٍ افتراضيّ
    python tools/probe_doi.py 10.36047/1227-000-052-004
"""
from __future__ import annotations
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT = "10.36047/1227-000-052-004"
UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Mobile Safari/537.36")


def _hdr(t):
    print("\n" + "═" * 62 + "\n " + t + "\n" + "═" * 62)


def main():
    doi = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT).replace(
        "https://doi.org/", "").strip()
    url = "https://doi.org/" + doi
    print(f"الرابط: {url}")

    _hdr("١) HTTP الخام — هل يقع تحويل، وإلى أين؟")
    import urllib.request
    import urllib.error

    class _Keep(urllib.request.HTTPRedirectHandler):
        chain = []

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            _Keep.chain.append((code, newurl))
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    op = urllib.request.build_opener(_Keep)
    body = b""
    final = url
    try:
        r = op.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30)
        body = r.read()
        final = r.geturl()
        print(f"  الحالة: {r.status}")
        print(f"  النوع : {r.headers.get('Content-Type')}")
        print(f"  الطول : {len(body)} بايت")
    except urllib.error.HTTPError as e:
        body = e.read()
        final = e.geturl()
        print(f"  HTTPError {e.code} — {len(body)} بايت")
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {str(e)[:90]}")
    for c, u in _Keep.chain:
        print(f"   ↪ {c} → {u[:80]}")
    print(f"  الوجهة النهائية: {final[:90]}")
    if body:
        txt = body.decode("utf-8", "ignore")
        print("  ── أول ٤٠٠ حرف من الردّ الخام ──")
        print("  " + " ".join(txt.split())[:400])

    _hdr("٢) ما الذي يُعيده كل مسارٍ من مسارات الجالب؟")
    from pipeline.orchestrator import WeaverOrchestrator as W
    o = W.__new__(W)
    o.llm_fn = None
    o.system_main = ""

    # trafilatura مباشرةً على الردّ الخام
    try:
        from trafilatura import extract as _tex
        t = _tex(body.decode("utf-8", "ignore"), output_format="markdown",
                 include_comments=False) if body else None
        print(f"  trafilatura على الخام: {len(t or '')} حرفاً")
        if t:
            print("   " + " ".join(t.split())[:300])
    except Exception as e:
        print(f"  trafilatura: ✗ {type(e).__name__}: {str(e)[:60]}")

    # المسار الكامل الذي يستعمله النظام
    try:
        full = asyncio.run(o._extract_full(url))
    except Exception as e:
        full = None
        print(f"  _extract_full: ✗ {type(e).__name__}: {str(e)[:60]}")
    print(f"  _extract_full: {len(str(full or ''))} حرفاً")
    if full:
        print("   ── نصّه كاملاً إن كان قصيراً ──")
        print("   " + " ".join(str(full).split())[:500])

    _hdr("٣) هل تنجح الوجهة النهائية مباشرةً (بلا doi.org)؟")
    if final and final != url:
        try:
            f2 = asyncio.run(o._extract_full(final))
            print(f"  _extract_full على {final[:60]} ⟶ {len(str(f2 or ''))} حرفاً")
            if f2:
                print("   " + " ".join(str(f2).split())[:300])
        except Exception as e:
            print(f"  ✗ {type(e).__name__}: {str(e)[:60]}")
    else:
        print("  لا تحويل — الوجهة هي doi.org نفسه")
    return 0


if __name__ == "__main__":
    sys.exit(main())
