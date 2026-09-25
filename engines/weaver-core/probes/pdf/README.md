# ملفّاتُ اختبار قارئ PDF (pipeline/pdf_pages.py)

| الملفّ | ما يختبره |
|---|---|
| `pages.pdf` | ٣ صفحات إنجليزيّة، في كلِّ صفحةٍ علامتُها (alpha · bravo · charlie) |
| `ar_text_pdfjs.pdf` | عربيٌّ حقيقيّ: pypdf يقلب ترتيبَ كلماته، وpdftotext يُخرجه صحيحاً |
| `ar_broken_map.pdf` | عربيٌّ خريطةُ حروفه تالفة: القارئان يُخرجان رموزاً ⟵ OCR |
| `ar_scanned.pdf` | صفحاتٌ مصوَّرة بلا نصّ ⟵ OCR |

`ar_text_pdfjs.pdf` هو `test/pdfs/ArabicCIDTrueType.pdf` من مشروع
[pdf.js](https://github.com/mozilla/pdf.js) (Mozilla، رخصة Apache-2.0)، كما هو.
والبقيّةُ مولَّدةٌ لهذا المشروع (خطّ Amiri من engines/fonts-core، رخصة OFL).
