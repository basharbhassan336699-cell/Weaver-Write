---
name: office-charts
description: Draw a chart (bar, line, pie, donut, scatter, radar…) with correct Arabic labels — as an image, as an interactive page (hover values, toggle series), or into a Word or PowerPoint file. Only when a chart or graph is wanted. يرسم رسماً بيانياً ثابتاً أو تفاعلياً أو يضيفه إلى ملفّ.
---

# الرسومُ البيانيّة

الأداة: `python3 {{WEAVER}}/pipeline/office.py chart`. ترسم بألوان Weaver،
والعربيُّ فيها متّصلُ الحروف بترتيبه الصحيح — يُقاس على الجهاز نفسِه قبل
الرسم — والتصميمُ من اليمين: الفئةُ الأولى يميناً، والمحورُ يميناً، والدائرةُ
مع عقارب الساعة. **لا تكتب كودَ matplotlib بنفسك** (arabic-reshaper مع
matplotlib الحديث يقلب العربيّ ويقطّعه — مقيس) — إلا لشيءٍ لا تفعله الأداة،
فقل ذلك.

## متى
- طلب **رسماً بيانياً** / مخطّطاً / chart / graph لبيانات.
- طلب إضافةَ رسمٍ إلى ملفّ وورد أو عرض.

## متى لا
- رسمٌ داخل ملفٍّ تبنيه الآن بمهارة office-word أو office-powerpoint: ضعه في
  مواصفته (`"chart": {…}`) — لا حاجةَ لهذه.
- رسمٌ داخل ملفّ إكسل: رسمُ Excel الأصليّ (office-excel).
- مخطّطُ أفكارٍ أو تدفّق (لا أرقام): ليس رسماً بيانياً.

`<مجلّد العمل>` هو المذكورُ تحت «[مجلّد العمل]» في رسالتك.

## المواصفة — `<مجلّد العمل>/chart-spec.json` بأداة `write`
```json
{"type": "bar", "title": "المبيعات", "xlabel": "الشهر", "ylabel": "القيمة",
 "data": {"labels": ["يناير", "فبراير", "مارس"], "values": [10, 15, 12]}}
```
شكلُ `data` بحسب النوع:
- `bar` · `horizontal_bar` · `pie` · `donut` · `radar` · `histogram`: `{"labels": […], "values": […]}`
- `grouped_bar` · `stacked_bar`: `{"labels": […], "series": {"٢٠٢٣": […], "٢٠٢٤": […]}}`
- `line` · `area`: `{"labels": […], "values": […]}` أو `{"x": […], "y": […]}`
- `multi_line`: `{"x": […], "series": {"أ": […], "ب": […]}}`
- `scatter`: `{"x": […], "y": […]}`

`"font": "أميري"` في المواصفة ⟵ يُرسم بالخطّ نفسِه (ما عندنا:
`python3 {{WEAVER}}/pipeline/office.py fonts`؛ وخطٌّ تجاريٌّ لا نملكه يُرسم بأقرب
خطٍّ عندنا ويُقال ذلك في الخرج).

## صورةٌ وحدها
`python3 {{WEAVER}}/pipeline/office.py chart <مجلّد العمل>/chart-spec.json --out <مجلّد العمل>/<اسم>.png`

## رسمٌ تفاعليّ — صفحة HTML
`python3 {{WEAVER}}/pipeline/office.py chart <مجلّد العمل>/chart-spec.json --out <مجلّد العمل>/<اسم>.html`
⟵ صفحةٌ واحدةٌ تعمل بلا إنترنت (Chart.js والخطُّ داخلها)، وتُفتح في Weaver
Write نفسِه أو أيّ متصفّح: لمسُ عنصرٍ يُظهر قيمتَه ونسبتَه، والضغطُ على الدليل
يُخفي سلسلة، وأزرارٌ لنوع الرسم (أعمدة/خطّ/دائرة) وجدولِ البيانات وتحميلِ PNG.
اختره حين يطلب «تفاعليّاً»، أو يريد استكشافَ الأرقام، أو لم يطلب ملفَّ وورد أو
عرضاً. وفي المواصفة: `"subtitle"` و`"source"` (مصدرُ البيانات).

## داخل ملفٍّ موجود
`python3 {{WEAVER}}/pipeline/office.py chart <مجلّد العمل>/chart-spec.json --into <الملفّ.docx|.pptx>`
⟵ `<الاسم>-edited.docx|pptx` (رسمٌ في آخر المستند، أو شريحةٌ في آخر العرض).
موضعٌ بعينه: أضِف إلى المواصفة `"after": N` (رقمُ فقرةٍ أو شريحةٍ من `info`)،
و`"caption"` لتعليقٍ تحت الرسم في وورد.

## قبل أن تقول «تمّ»
لا تقل «تمّ» إلا بعد `✓`. والأرقامُ من المستخدم أو من مصدرٍ ذكرتَه — لا
أرقامَ مختلَقةً في رسم.
