# -*- coding: utf-8 -*-
"""
tools/verify_refs_live.py — إثباتٌ شبكيّ حقيقيّ، لا اختبار منطق.
=================================================================
يُشغَّل على جهازٍ له شبكة. يطبع أرقاماً فعلية:
  M = كم رابطاً حاول النظام فتحه
  N = كم فُتح وقُرئ بنجاح
ولكل مرجع: وسمه الفعليّ وسببه إن تعذّر.
ثم يختبر المسار العام (سقف الثلاثة) بعدّادٍ حقيقيّ.

    python tools/verify_refs_live.py
    python tools/verify_refs_live.py "موضوعٌ آخر" 9

لا يستدعي نموذجاً لغوياً إطلاقاً — فلا يكلّف توكناً واحداً.
"""
from __future__ import annotations
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOPIC = "الإعجاز العلمي والأخلاقي في القرآن الكريم"
WEB_Q = "سعر آيفون 17 الحالي"
LINE = "─" * 66


def _hdr(t):
    print("\n" + "═" * 66)
    print(" " + t)
    print("═" * 66)


def main():
    from pipeline.orchestrator import WeaverOrchestrator as W

    topic = sys.argv[1] if len(sys.argv) > 1 else TOPIC
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 9

    _hdr("٠) الإعداد الفعليّ في هذه البيئة")
    cap = os.environ.get("WEAVER_VERIFY_REF_MAX")
    print(f"  WEAVER_VERIFY_REF_MAX = {cap if cap else '<غير مضبوط>'}"
          f"  ⟶ {'سقف ' + str(cap) if cap and cap.isdigit() and int(cap) > 0 else 'بلا سقف: يحاول فتح كل الروابط'}")
    print(f"  WEAVER_VERIFY_REFS    = {os.environ.get('WEAVER_VERIFY_REFS', '<غير مضبوط> ⟶ مُفعَّل')}")
    print(f"  الطبقة العامة محمّلة   = {'نعم' if W._wr() else 'لا'}")

    orch = W.__new__(W)
    orch.llm_fn = None
    orch.system_main = ""

    _hdr("١) البحث الأكاديميّ — جلبُ المرشّحين من قواعد البيانات")
    t0 = time.time()
    try:
        srcs = W._scholarly_search(topic, "ar", want) or []
    except Exception as e:
        print(f"  ✗ تعذّر البحث: {type(e).__name__}: {e}")
        srcs = []
    print(f"  الموضوع: {topic}")
    print(f"  رجع {len(srcs)} مرشّحاً في {time.time() - t0:.1f}ث")
    if not srcs:
        print("\n  ⚠ لا مرشّحين — إمّا لا شبكة، أو القواعد لم تُعِد شيئاً.")
        print("     لا يمكن إثبات التحقّق بلا مرشّحين. أوقف هنا وأرسل المخرَج.")
        return 1

    _hdr("٢) التحقّق — فتحُ كل رابط وقراءته فعلاً")
    log = []
    _orig = W._extract_full

    async def probe(url):
        t = time.time()
        try:
            txt = await _orig(orch, url)
        except Exception as e:
            log.append((url, "✗", f"{type(e).__name__}: {str(e)[:70]}",
                        time.time() - t))
            return None
        n = len(str(txt or ""))
        if not txt or n < 120:
            log.append((url, "✗", f"صفحة فارغة/قصيرة ({n} حرفاً)", time.time() - t))
        else:
            log.append((url, "✓", f"{n} حرفاً", time.time() - t))
        return txt

    orch._extract_full = probe
    card = {}
    try:
        res = asyncio.run(orch._verify_references(list(srcs), card, "ar"))
    except Exception as e:
        print(f"  ✗ انهار التحقّق: {type(e).__name__}: {e}")
        return 1

    print(f"  M (روابط حاول فتحها) = {len(log)}")
    for url, mark, why, dt in log:
        print(f"   {mark} [{dt:5.1f}ث] {why[:48]:50s} | {url[:58]}")

    v = card.get("refs_verified") or {}
    _hdr("٣) النتيجة")
    print(f"  من الصفحة الأصلية : {v.get('ok', 0)}/{v.get('total', 0)}")
    print(f"  من سجلّ الـDOI     : {v.get('registry', 0)}")
    print(f"  محجوب باشتراك      : {v.get('paywalled', 0)}")
    print(f"  بلا تحقّق          : {v.get('unverified', 0)}")
    print(LINE)
    for r in res:
        mark = {"verified": "✓ من الصفحة  ",
                "registry": "◐ من السجلّ   ",
                "paywalled": "⚠ محجوب       ",
                "unverified": "⚠ غير مُتحقَّق",
                "unreachable": "⚠ تعذّر الفتح"}.get(str(r.get("verified") or ""),
                                                   "؟ بلا وسم   ")
        fl = "، ".join(r.get("verified_fields") or []) or "—"
        _ba = str(r.get("blocked_at") or "")
        _h = ("@" + _ba.split("//")[-1].split("/")[0]) if _ba else ""
        print(f"  {mark} | {(r.get('title') or '')[:40]:42s} | {fl[:34]} {_h}")
    print(LINE)
    for n in (card.get("skipped_steps") or []):
        s = n if isinstance(n, str) else f"{n.get('step')} — {n.get('reason')}"
        print(f"  • {s}")

    _hdr("٤) المسار العام — سقف الثلاثة كما هو")

    class _Mem:
        def __init__(self):
            self.status = []

        def set_status(self, n, t):
            self.status.append((n, t))

        def add_reference(self, t, source_key=None):
            pass

    class _Task:
        def __init__(self, d, c):
            self.description, self.task_card = d, c

    o2 = W.__new__(W)
    o2.llm_fn = None
    o2.system_main = ""
    fetches = []

    async def probe2(url):
        fetches.append(url)
        try:
            return await _orig(o2, url)
        except Exception:
            return None

    o2._extract_full = probe2
    c2 = {"topic": WEB_Q, "language": "ar", "reference_count": 8}
    m2 = _Mem()
    try:
        asyncio.run(o2._web_search(_Task(WEB_Q, c2), m2))
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {str(e)[:70]}")
    print(f"  الاستعلام: {WEB_Q}")
    print(f"  مصادر جُمعت: {len(c2.get('sources') or [])}")
    print(f"  روابط فُتحت فعلاً: {len(fetches)}   ← يجب ألّا تتجاوز ٣")
    print(f"  web_full_reads (عدّاد النظام): {c2.get('web_full_reads', 0)}")
    for u in fetches:
        print(f"   · {u[:70]}")
    print(f"  الحالة: {m2.status[-1][1] if m2.status else '—'}")
    ok3 = len(fetches) <= 3
    print(f"\n  ⟵ سقف الثلاثة {'سليم ✅' if ok3 else 'مكسور ❌'}")

    _hdr("الخلاصة — انسخ هذا السطر وأرسله")
    print(f"  صفحة={v.get('ok',0)} سجلّ={v.get('registry',0)} "
          f"محجوب={v.get('paywalled',0)} بلا={v.get('unverified',0)} "
          f"/ {v.get('total',0)} · CAP={cap or 'بلا سقف'} · "
          f"web={len(fetches)}/3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
