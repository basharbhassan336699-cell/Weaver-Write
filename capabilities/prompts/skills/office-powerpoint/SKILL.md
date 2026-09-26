---
name: office-powerpoint
description: Create or edit a PowerPoint deck (.pptx) — slides, tables, charts, Arabic RTL; or edit a .pptx the user attached (text, add/delete/move slides, notes). Only when a presentation file is wanted. ينشئ عرضاً تقديمياً أو يعدّل عرضاً أرسله المستخدم.
---

# عروضُ باوربوينت (.pptx)

الأداة: `python3 {{WEAVER}}/pipeline/office.py`. تبني بتصميم Weaver (غلاف،
شرائحُ محتوى وأقسام، جداولُ أصليّة، رسوم، ختام، RTL) وتفتح العرضَ بعد كتابته
لتتحقّق منه. **لا تكتب كودَ python-pptx بنفسك** — إلا لشيءٍ لا تفعله الأداة،
فقل ذلك.

## متى
- طلب **عرضاً تقديمياً** / شرائح / باوربوينت / pptx.
- أرسل ملفَّ `.pptx` وطلب تعديله.

## متى لا
- لم يطلب ملفّاً — أجب في المحادثة. و`.ppt` القديم: اطلب حفظَه `.pptx`.

`<مجلّد العمل>` هو المذكورُ تحت «[مجلّد العمل]» في رسالتك.

## إنشاء
١. اكتب `<مجلّد العمل>/office-spec.json` بأداة `write`:
```json
{"title": "عنوان العرض", "subtitle": "…", "closing": "شكراً لكم",
 "slides": [
   {"title": "المحاور", "points": ["نقطةٌ قصيرة", "نقطة"]},
   {"layout": "section", "title": "القسم الثاني"},
   {"title": "الأرقام", "table": {"headers": ["البند", "القيمة"], "rows": [["أ", 1]]}},
   {"title": "الاتّجاه", "chart": {"type": "line", "data": {"labels": ["٢٠٢٣", "٢٠٢٤"], "values": [3, 5]}}}]}
```
   النقاطُ قصيرة (٣–٦ في الشريحة). الغلافُ والختامُ يُضافان وحدَهما.
٢. `python3 {{WEAVER}}/pipeline/office.py build <مجلّد العمل>/office-spec.json --out <مجلّد العمل>/<اسم>.pptx`

## تعديلُ عرضٍ موجود
١. `python3 {{WEAVER}}/pipeline/office.py info <الملفّ>` — الشرائحُ `slide N`
   وأشكالُها `#K` بنصوصها.
٢. `<مجلّد العمل>/office-ops.json` — **الأرقامُ من `info` قبل التعديل**:
```json
[{"op": "replace", "find": "قديم", "with": "جديد"},
 {"op": "set_text", "slide": 2, "shape": 0, "text": "سطر\nسطرٌ ثانٍ"},
 {"op": "add_slide", "after": 2, "title": "…", "points": ["…"]},
 {"op": "add_table_slide", "after": 3, "title": "…", "table": {"headers": [], "rows": []}},
 {"op": "add_chart_slide", "after": 3, "title": "…", "chart": {…}},
 {"op": "delete_slide", "slide": [4, 5]},
 {"op": "move_slide", "slide": 7, "to": 2},
 {"op": "notes", "slide": 1, "text": "ملاحظاتُ المتحدّث"}]
```
   الشريحةُ الجديدةُ تأخذ تخطيطَ العرض نفسِه إن كان مبنيّاً بقوالب.
٣. `python3 {{WEAVER}}/pipeline/office.py edit <الملفّ> <مجلّد العمل>/office-ops.json`
   ⟵ `<الاسم>-edited.pptx`، والأصلُ باقٍ.

## قبل أن تقول «تمّ»
لا تقل «تمّ» إلا بعد `✓ saved:`. و`✗` لعمليّة: أصلحها أو قل ما لم يتمّ.
