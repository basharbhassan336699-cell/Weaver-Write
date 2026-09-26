---
name: office-word
description: Create or edit a Word file (.docx) — report, research, letter — with Arabic RTL, headings, tables, contents page and charts; or edit a .docx the user attached. Only when a Word file is wanted. ينشئ ملفَّ وورد أو يعدّل ملفّاً أرسله المستخدم.
---

# ملفّاتُ وورد (.docx)

الأداةُ واحدة: `python3 {{WEAVER}}/pipeline/office.py`. تبني بأدوات Weaver
(RTL، ألوان، جداول، فهرس، ترويسة، أرقامُ صفحات) وتفتح الملفَّ بعد كتابته
لتتحقّق منه. **لا تكتب كودَ python-docx بنفسك** — إلا لشيءٍ لا تفعله الأداة،
فقل ذلك للمستخدم.

## متى
- طلب **ملفَّ وورد** / docx / «ملفٌّ أحمّله» / «أرسله لي وورد».
- أرسل ملفَّ `.docx` وطلب تعديله، أو إضافةَ شيءٍ إليه.

## متى لا
- سؤالٌ جوابُه في المحادثة، أو لم يطلب ملفّاً — أجب نصّاً كالمعتاد.
- ملفُّ `.doc` القديم: الأداةُ ترفضه؛ اطلب منه حفظَه `.docx`.

`<مجلّد العمل>` هو المذكورُ في رسالتك تحت «[مجلّد العمل]» (`chats/…/`)؛ فيه
تكتب كلَّ شيء.

## إنشاء
١. اكتب المحتوى كاملاً أوّلاً (بحثٌ حقيقيّ إن لزم)، ثمّ ضعه في مواصفةٍ بأداة
   `write` في `<مجلّد العمل>/office-spec.json`:
```json
{"title": "العنوان", "subtitle": "", "toc": true, "header": "نصُّ الترويسة",
 "cover": {"author": "", "institution": "", "supervisor": "", "date": ""},
 "sections": [
   {"heading": "المقدّمة", "level": 1, "body": "فقرات…\n\n- نقطة\n- نقطة"},
   {"heading": "النتائج", "body": "…",
    "table": {"headers": ["البند", "القيمة"], "rows": [["أ", 10]], "totals": ["المجموع", 10]},
    "chart": {"type": "bar", "data": {"labels": ["أ", "ب"], "values": [3, 5]},
              "title": "…", "caption": "شكل ١"}}],
 "references": ["…"]}
```
   `body` يقبل Markdown (فقرات، نقاط، جداول). `level` ٢ و٣ للعناوين الفرعيّة.
   `cover` اختياريّ (صفحةُ غلاف). اللغةُ تُكتشف من النصّ (أو `"lang": "ar"|"en"`).
٢. `python3 {{WEAVER}}/pipeline/office.py build <مجلّد العمل>/office-spec.json --out <مجلّد العمل>/<اسمٌ واضح>.docx`

## تعديلُ ملفٍّ موجود
١. **اقرأه أوّلاً:** `python3 {{WEAVER}}/pipeline/office.py info <الملفّ>` —
   يسرد الفقرات `¶N` والجداول `T0` بأرقامها (و`--find نصّ` للبحث).
٢. اكتب العمليّات في `<مجلّد العمل>/office-ops.json` — **كلُّ الأرقام من `info`
   قبل التعديل**، ولو تتابعت العمليّات:
```json
[{"op": "replace", "find": "نصٌّ قديم", "with": "نصٌّ جديد"},
 {"op": "set_text", "paragraph": 9, "text": "…"},
 {"op": "insert_paragraph", "after": 9, "text": ["فقرة", "وأخرى"], "style": "Heading 1"},
 {"op": "delete_paragraph", "paragraph": [12, 13]},
 {"op": "set_cell", "table": 0, "row": 1, "col": 1, "text": "15"},
 {"op": "add_row", "table": 0, "after_row": 2, "values": ["ج", "7"]},
 {"op": "add_table", "after": 14, "headers": ["…"], "rows": [["…"]]},
 {"op": "add_chart", "after": 14, "chart": {"type": "line", "data": {…}}, "caption": "…"},
 {"op": "add_image", "after": 14, "path": "<مجلّد العمل>/صورة.png", "caption": "…"}]
```
   الفقرةُ المُدرجةُ تأخذ تنسيقَ ما قبلها (أو فقرةٍ بالنمط `style`، أو `"like": N`).
٣. `python3 {{WEAVER}}/pipeline/office.py edit <الملفّ> <مجلّد العمل>/office-ops.json`
   ⟵ يُحفظ `<الاسم>-edited.docx` بجانبه، والأصلُ لا يُمَسّ.

## قبل أن تقول «تمّ»
- لا تقل «أنشأتُ الملفّ» إلا بعد سطر `✓ saved:` — واذكر اسمَ الملفّ.
- `✗` لعمليّة: أصلحها وأعِدها، أو قل للمستخدم ما لم يتمّ ولماذا.
