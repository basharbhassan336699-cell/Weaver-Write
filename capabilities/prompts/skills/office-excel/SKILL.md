---
name: office-excel
description: Create or edit an Excel workbook (.xlsx) — tables, formulas and totals, number formats, native charts, Arabic RTL; or edit a .xlsx the user attached (cells, rows — totals and charts follow). Only when a spreadsheet is wanted. ينشئ جدولَ إكسل أو يعدّل ملفّاً أرسله المستخدم.
---

# جداولُ إكسل (.xlsx)

الأداة: `python3 {{WEAVER}}/pipeline/office.py`. تبني بتنسيق Weaver (ترويسةٌ
ملوّنة، حدود، RTL، سطرُ مجموعٍ بمعادلات) وتعدّل كما يعدّل Excel: **إدراجُ صفٍّ
يُزيح المعادلاتِ والرسوم**، وصفٌّ يُضاف قبل «الإجمالي» يدخل في مجموعه.
**لا تكتب كودَ openpyxl بنفسك** — إلا لشيءٍ لا تفعله الأداة، فقل ذلك.

## متى
- طلب **ملفَّ إكسل** / جدولَ بيانات / xlsx / «جدولٌ أحسبه».
- أرسل ملفَّ `.xlsx` وطلب تعديله.

## متى لا
- جدولٌ صغيرٌ يُقرأ في المحادثة ولم يطلب ملفّاً — جدولُ Markdown يكفي.
- `.xls` القديم أو `.xlsm` (فيه ماكرو): الأداةُ ترفضه؛ قل ذلك.

`<مجلّد العمل>` هو المذكورُ تحت «[مجلّد العمل]» في رسالتك.

## إنشاء
١. `<مجلّد العمل>/office-spec.json` بأداة `write` — الأرقامُ أرقامٌ لا نصوص،
   والمعادلةُ نصٌّ يبدأ بـ`=`:
```json
{"sheets": [
  {"name": "المصاريف", "headers": ["البند", "المبلغ", "النسبة"],
   "rows": [["إيجار", 1500, "=B2/B$5"], ["طعام", 800, "=B3/B$5"], ["مواصلات", 300, "=B4/B$5"]],
   "totals": true,
   "formats": {"B": "#,##0", "C": "0.0%"},
   "chart": {"type": "pie", "title": "توزيع المصاريف", "data": "B1:B4", "categories": "A2:A4"}}]}
```
   `totals` يضيف سطرَ «الإجمالي» بمعادلات SUM. `chart` رسمٌ أصليٌّ في Excel
   (bar · line · pie) يبقى قابلاً للتعديل فيه.
٢. `python3 {{WEAVER}}/pipeline/office.py build <مجلّد العمل>/office-spec.json --out <مجلّد العمل>/<اسم>.xlsx`

## تعديلُ ملفٍّ موجود
١. `python3 {{WEAVER}}/pipeline/office.py info <الملفّ>` — الأوراقُ والخلايا
   بمعادلاتها (`--rows N` · `--find نصّ`). و`⚠ … would DROP` ⟵ قل للمستخدم قبل
   التعديل.
٢. `<مجلّد العمل>/office-ops.json`:
```json
[{"op": "set", "sheet": "المصاريف", "cells": {"B2": 1600, "D1": "ملاحظة"}},
 {"op": "add_rows", "sheet": "المصاريف", "values": [["كهرباء", 200, "=B5/B$6"]]},
 {"op": "insert_rows", "sheet": "المصاريف", "at": 3, "values": [["…", 0]]},
 {"op": "delete_rows", "sheet": "المصاريف", "at": 4, "count": 1},
 {"op": "set_range", "sheet": "المصاريف", "start": "E2", "values": [[1, 2], [3, 4]]},
 {"op": "format", "sheet": "المصاريف", "range": "B2:B9", "number_format": "#,##0", "bold": true},
 {"op": "add_chart", "sheet": "المصاريف", "type": "bar", "data": "B1:B5", "categories": "A2:A5"},
 {"op": "add_sheet", "name": "ملخّص", "headers": ["…"], "rows": [["…"]]},
 {"op": "rename_sheet", "sheet": "Sheet1", "to": "البيانات"}]
```
   `add_rows` يضع الصفوفَ في آخر البيانات، قبل سطر المجموع إن وُجد، ويوسّع
   المجموعَ والرسم. بلا `sheet` ⟵ الورقةُ النشطة.
٣. `python3 {{WEAVER}}/pipeline/office.py edit <الملفّ> <مجلّد العمل>/office-ops.json`
   ⟵ `<الاسم>-edited.xlsx`. والقيمُ تُحسب عند فتح الملفّ.

## الرفضُ حمايةً
`✗ REFUSED: saving would DROP …` ⟵ الحفظُ كان سيُسقط من الملفّ شيئاً (أشكال،
تعليقات، ماكرو…) فلم يُكتب. **قل للمستخدم ما سيضيع، ولا تلتفّ عليه.**

## قبل أن تقول «تمّ»
لا تقل «تمّ» إلا بعد `✓ saved:`. و`✗` لعمليّة: أصلحها أو قل ما لم يتمّ.
