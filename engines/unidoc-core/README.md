# UniDoc — أداة تحويل المستندات الموحّدة

تجمع **ثلاثة محركات** في واجهة واحدة مع توجيه ذكي تلقائي — دون تعديل منطق أي أداة.

## المحركات الثلاثة

| المحرك | التخصص | المتطلبات |
|---|---|---|
| **anydoc** | Office المهيكل: DOCX, PPTX, XLSX, RTF, EPUB, ODF → Markdown | CPU فقط (سريع، بلا AI) |
| **olmocr** | PDF/صور ممسوحة → Markdown، إزالة رؤوس/تذييل، ترتيب طبيعي | GPU (7B VLM)، اقتصادي |
| **chandra** | PDF/صور → HTML/MD/JSON، 90+ لغة، جداول، رياضيات، نماذج | GPU أو خادم vLLM بعيد |

## كيف يختار المحرك تلقائياً

```
صيغة Office (docx, pptx…)        → anydoc      (لا حاجة لـ AI)
PDF/صورة + جداول/رياضيات/لغات    → chandra     (دقة عالية)
PDF/صورة + HTML أو JSON مطلوب    → chandra     (olmocr لا يدعمها)
PDF/صورة نصية + GPU متاح         → olmocr      (أرخص)
PDF/صورة + لا GPU + خادم بعيد    → chandra remote
PDF/صورة + لا GPU + لا خادم      → Tesseract   (fallback لـ Termux)
```

## التثبيت

```bash
# الأساس (التوجيه فقط)
pip install -e .

# مع محركات محددة
pip install -e .[office]          # anydoc
pip install -e .[chandra-hf]      # chandra محلي GPU
pip install -e .[chandra-remote]  # chandra خادم بعيد
pip install -e .[tesseract]       # fallback للأجهزة الصغيرة
pip install -e .[all]             # كل شيء
```

## الاستخدام

### Python

```python
import unidoc

# تحويل بسيط — يختار المحرك تلقائياً
md = unidoc.convert("report.docx")        # → anydoc
md = unidoc.convert("scan.pdf")           # → olmocr/chandra/tesseract حسب الجهاز

# مع متطلبات دقة
html = unidoc.convert("invoice.pdf", output="html", need_tables=True)   # → chandra
md = unidoc.convert("arabic.pdf", need_multilingual=True)               # → chandra
json_out = unidoc.convert("form.pdf", output="json", need_forms=True)   # → chandra

# إجبار محرك محدد
md = unidoc.convert("doc.pdf", engine="tesseract")

# تفاصيل كاملة
result = unidoc.convert_detailed("scan.pdf")
print(result["engine"])   # أي محرك استُخدم
print(result["reason"])   # ولماذا
print(result["content"])  # النص
print(result["assets"])   # الصور المستخرجة
```

### سطر الأوامر

```bash
# تحويل
python -m unidoc convert report.docx
python -m unidoc convert scan.pdf --output html --need-tables
python -m unidoc convert form.pdf --engine chandra --need-forms --save out.json

# عرض قدرات الجهاز
python -m unidoc detect

# معاينة قرار التوجيه دون تنفيذ
python -m unidoc route scan.pdf --need-math
```

## متغيرات البيئة

```bash
UNIDOC_FORCE_CPU=1              # تعطيل GPU
UNIDOC_FORCE_GPU=1              # إجبار GPU
UNIDOC_VLLM_URL=http://host:8000  # خادم vLLM بعيد لـ chandra
UNIDOC_NO_TESSERACT=1          # تعطيل Tesseract fallback
```

## البنية

```
unidoc-core/
├── unidoc/                    ← طبقة التوحيد (جديدة)
│   ├── __init__.py            ← convert() الواجهة الرئيسية
│   ├── router.py              ← منطق اختيار المحرك
│   ├── device.py              ← كشف GPU/remote/tesseract
│   ├── engines.py             ← أغلفة تستدعي الأدوات الأصلية
│   └── cli.py                 ← واجهة سطر الأوامر
├── engines_src_anydoc/        ← anydoc الأصلي (بلا تعديل)
├── engines_src_olmocr/        ← olmocr الأصلي (بلا تعديل)
└── engines_src_chandra/       ← chandra الأصلي (بلا تعديل)
```

**مبدأ التصميم:** طبقة `unidoc/` لا تعدّل منطق أي أداة — تستدعيها كما هي فقط.

## لـ WeaverCode على Termux/Android

```python
# الأجهزة بلا GPU تستخدم Tesseract تلقائياً
import unidoc

# Office يعمل مباشرة (لا يحتاج GPU)
md = unidoc.convert("document.docx")

# PDF ممسوح يستخدم Tesseract fallback
md = unidoc.convert("scan.pdf", engine="tesseract", lang="ara+eng")
```
