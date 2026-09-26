---
name: office-charts
description: Draw a chart image (bar, line, pie, donut, scatter, radar…) with correct Arabic labels, or add a chart into a Word or PowerPoint file. Only when a chart or graph is wanted. يرسم رسماً بيانياً أو يضيفه إلى ملفّ وورد أو عرض.
---

# الرسومُ البيانيّة

الأداة: `python3 {{WEAVER}}/pipeline/office.py chart`. ترسم بألوان Weaver،
والعربيُّ فيها بترتيبه الصحيح (مقيس). **لا تكتب كودَ matplotlib بنفسك** —
إلا لشيءٍ لا تفعله الأداة، فقل ذلك.

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

## صورةٌ وحدها
`python3 {{WEAVER}}/pipeline/office.py chart <مجلّد العمل>/chart-spec.json --out <مجلّد العمل>/<اسم>.png`

## داخل ملفٍّ موجود
`python3 {{WEAVER}}/pipeline/office.py chart <مجلّد العمل>/chart-spec.json --into <الملفّ.docx|.pptx>`
⟵ `<الاسم>-edited.docx|pptx` (رسمٌ في آخر المستند، أو شريحةٌ في آخر العرض).
موضعٌ بعينه: أضِف إلى المواصفة `"after": N` (رقمُ فقرةٍ أو شريحةٍ من `info`)،
و`"caption"` لتعليقٍ تحت الرسم في وورد.

## قبل أن تقول «تمّ»
لا تقل «تمّ» إلا بعد `✓`. والأرقامُ من المستخدم أو من مصدرٍ ذكرتَه — لا
أرقامَ مختلَقةً في رسم.
