# -*- coding: utf-8 -*-
"""صفحةٌ بطيئة لا تُعلّق التشغيل كلَّه.

التشغيل: ثلاثَ عشرةَ دقيقةً على «بحث في الويب»، بلا رسالةٍ ولا حدّ. والسبب أن
_extract_full يمشي في سلسلةِ جالبين — UniWeb ثم tool_web_document بـOCR على
«ara+eng» — ولا واحدَ منها يحمل مهلة. مضيفٌ بطيءٌ واحد، أو PDF ممسوحٌ كبير،
فلا يعود الـawait أبداً.

ولا يُفقد شيءٌ بالقطع: مقتطفُ نتيجة البحث في اليد أصلاً، وهو ما يُستعمل."""
import sys, os, re, asyncio, inspect, time
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for k in list(os.environ):
    if k.startswith("WEAVER_"):
        os.environ.pop(k)
from pipeline.orchestrator import WeaverOrchestrator as W
ok = True


def chk(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"   {'✅' if good else '❌'} {label}" + (f" — {detail}" if detail else ""))


print("═" * 70)
print(" ١) سلسلةُ الجلب كانت بلا مهلةٍ إطلاقاً")
print("═" * 70)
_ef = inspect.getsource(W._extract_full)
chk("uniweb.fetch ما زال بلا مهلةٍ خاصّة به (لذا تلزم مهلةٌ من فوقه)",
    "_uniweb.fetch(url)" in _ef and "timeout" not in
    _ef.split("_uniweb.fetch(url)")[0][-200:])
chk("و OCR على ara+eng حاضرٌ في السلسلة", 'ocr_lang": "ara+eng"' in _ef
    or "ocr_lang" in _ef)

print("\n" + "═" * 70)
print(" ٢) والآن لكلّ صفحةٍ مهلة، وللمرحلة ميزانية")
print("═" * 70)
_src = inspect.getsource(W._web_search)
chk("كلُّ صفحةٍ تحت wait_for", "_aio8.wait_for(self._extract_full" in _src)
chk("ومهلةُ الصفحة قابلةٌ للضبط", "WEAVER_FETCH_TIMEOUT" in _src)
chk("وللمرحلة كلِّها ميزانيةٌ زمنية", "WEAVER_FETCH_BUDGET" in _src)
chk("ولا تُبدأ قراءةٌ بعد نفادها", "_left <= 5" in _src)
chk("والتقدّم يُعلَن صفحةً صفحة", "قراءة المصدر" in _src)
chk("والتخطّي يُسجَّل لا يُخفى", "تُخطّيت" in _src)
chk("ويُقال إن المقتطف حلَّ محلّها", "مقتطفُ" in _src)
_defaults = re.findall(r'WEAVER_FETCH_(?:TIMEOUT|BUDGET)", "(\d+)"', _src)
chk(f"الافتراضيّات: {_defaults} ثانية", _defaults == ["45", "150"])

print("\n" + "═" * 70)
print(" ٣) وبالتشغيل: صفحةٌ لا تعود أبداً تُقطع")
print("═" * 70)


async def _hangs_forever(url):
    await asyncio.sleep(3600)
    return "never"


async def _quick(url):
    return "نصٌّ كامل"


async def _probe(fn, per, budget):
    """محاكاةُ حلقة القراءة نفسها: مهلةٌ للصفحة وميزانيةٌ للمرحلة."""
    t0 = time.time()
    reads, skipped = 0, 0
    for i in range(3):
        left = budget - int(time.time() - t0)
        if left <= 5:
            skipped += 1
            continue
        try:
            txt = await asyncio.wait_for(fn(f"u{i}"), timeout=min(per, left))
        except asyncio.TimeoutError:
            txt = None
            skipped += 1
        if txt:
            reads += 1
    return reads, skipped, time.time() - t0


loop = asyncio.new_event_loop()
r, s, el = loop.run_until_complete(_probe(_hangs_forever, 2, 8))
chk(f"ثلاثُ صفحاتٍ معلَّقة ⟶ قُطعت في {el:.1f} ث بدل الأبد",
    el < 10 and s == 3 and r == 0, f"قُرئ {r}، تُخطّي {s}")
r2, s2, el2 = loop.run_until_complete(_probe(_quick, 2, 8))
chk(f"وصفحاتٌ سريعة ⟶ تُقرأ كلُّها ({el2:.2f} ث)", r2 == 3 and s2 == 0)


async def _mixed(url):
    if url == "u0":
        await asyncio.sleep(3600)
    return "نصٌّ كامل"


r3, s3, el3 = loop.run_until_complete(_probe(_mixed, 2, 30))
chk("وواحدةٌ بطيئةٌ بين سريعتين ⟶ لا تُسقط الباقيتين",
    r3 == 2 and s3 == 1, f"قُرئ {r3}، تُخطّي {s3}")

print("\n" + "═" * 70)
print(" ٤) ولا يسقط مصدرٌ بسبب التخطّي")
print("═" * 70)
chk("المقتطفُ يبقى محتوىً للمصدر",
    "content = snippet" in _src and "srcs.append" in _src)
chk("والمصدرُ يُضاف سواءٌ قُرئ كاملاً أم لا",
    _src.index("content = snippet") < _src.index("srcs.append"))

print("\n" + "═" * 70)
print(" النتيجة: " + ("PASS ✅" if ok else "FAIL ❌"))
print("═" * 70)
sys.exit(0 if ok else 1)
