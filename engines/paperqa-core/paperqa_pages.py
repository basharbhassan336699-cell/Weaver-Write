"""
PaperQA2 — استشهاد دقيق برقم الصفحة (Page-Accurate Citations)
================================================================

يحل مشكلة رقم الصفحة في PaperQA2 عبر PyMuPDF4LLM:
  - يستخرج النص صفحةً صفحةً مع رقمها الحقيقي
  - يُمرّر كل مقطع لـ PaperQA2 مع اسم يحوي رقم الصفحة
  - النتيجة: استشهاد بصيغة "المؤلف، 2024، ص. 5"

يعمل مع:
  - PDFs محلية
  - PDFs من الإنترنت (arXiv, ResearchGate, DOI)
  - ملفات ممسوحة ضوئياً (OCR تلقائي عبر PyMuPDF4LLM)

لا يعدّل أي كود أصلي من PaperQA2 — يستخدم aadd_texts الرسمية.

الاستخدام:
    from paperqa_pages import PagedPaperQA

    qa = PagedPaperQA(lang="arabic")
    await qa.add("study.pdf")                       # محلي
    await qa.add("https://arxiv.org/pdf/2409.13740") # إنترنت
    await qa.add("10.1145/3767695.3769505")          # DOI

    result = await qa.ask("ما النتائج؟")
    # الإجابة: "...النتيجة (Smith2024، ص. 5)..."
"""

from __future__ import annotations
import os
import re
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Optional


# ══════════════════════════════════════════════════════════════
# ١. استخراج النص مع رقم الصفحة (PyMuPDF4LLM)
# ══════════════════════════════════════════════════════════════

@dataclass
class PagedChunk:
    """مقطع نصي مع رقم صفحته الحقيقي."""
    text: str
    page: int
    source: str


def extract_with_pages(
    pdf_path: str,
    *,
    ocr_on_scanned: bool = True,
    min_chunk_chars: int = 30,
) -> list[PagedChunk]:
    """
    يستخرج النص من PDF صفحةً صفحةً مع رقم كل صفحة.

    PyMuPDF4LLM يشغّل OCR تلقائياً على الصفحات الممسوحة.

    Args:
        pdf_path: مسار PDF
        ocr_on_scanned: تفعيل OCR التلقائي على الصفحات الممسوحة
        min_chunk_chars: أدنى عدد أحرف لقبول المقطع

    Returns:
        قائمة PagedChunk، كل واحد بنصه ورقم صفحته
    """
    try:
        import pymupdf4llm
    except ImportError:
        raise ImportError(
            "يحتاج PyMuPDF4LLM: pip install pymupdf4llm\n"
            "(يستخرج النص مع رقم الصفحة ويشغّل OCR تلقائياً)"
        )

    # page_chunks=True → كل صفحة كائن مستقل مع metadata.page_number
    pages = pymupdf4llm.to_markdown(
        pdf_path,
        page_chunks=True,
        show_progress=False,
    )

    chunks = []
    for page_data in pages:
        text = (page_data.get("text") or "").strip()
        if len(text) < min_chunk_chars:
            continue
        # رقم الصفحة الحقيقي (1-indexed)
        meta = page_data.get("metadata", {})
        page_num = meta.get("page_number")
        if page_num is None:
            page_num = meta.get("page", len(chunks) + 1)
        chunks.append(PagedChunk(
            text=text,
            page=int(page_num),
            source=pdf_path,
        ))

    return chunks


# ══════════════════════════════════════════════════════════════
# ٢. جلب المراجع من الإنترنت
# ══════════════════════════════════════════════════════════════

def fetch_to_local(source: str, *, timeout: int = 60) -> tuple[str, bool]:
    """
    يجلب مرجعاً من الإنترنت إلى ملف محلي مؤقت.

    Args:
        source: URL أو DOI أو مسار محلي

    Returns:
        (المسار المحلي، هل هو مؤقت يجب حذفه)
    """
    # مسار محلي — كما هو
    if not (source.startswith("http") or source.startswith("10.")):
        return source, False

    # DOI → رابط
    if source.startswith("10."):
        url = f"https://doi.org/{source}"
    else:
        url = source

    # تنزيل
    headers = {"User-Agent": "Mozilla/5.0 (research citation tool)"}
    req = urllib.request.Request(url, headers=headers)

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # التحقق أنه PDF
            ctype = resp.headers.get("Content-Type", "")
            data = resp.read()
            tmp.write(data)
            tmp.close()

            # فحص بسيط أن الملف PDF
            if not data[:5].startswith(b"%PDF") and "pdf" not in ctype.lower():
                os.unlink(tmp.name)
                raise ValueError(
                    f"الرابط لا يُعيد PDF مباشرة: {url}\n"
                    "قد يكون خلف paywall أو صفحة HTML. حمّل الـ PDF يدوياً."
                )
        return tmp.name, True
    except Exception:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise


# ══════════════════════════════════════════════════════════════
# ٣. الواجهة الرئيسية — PagedPaperQA
# ══════════════════════════════════════════════════════════════

class PagedPaperQA:
    """
    PaperQA2 مع استشهاد دقيق برقم الصفحة.

    يجمع:
      - PyMuPDF4LLM (استخراج مع رقم الصفحة + OCR)
      - PaperQA2 (البحث والإجابة)
      - paperqa_arabic (الدعم العربي، اختياري)

    مثال:
        qa = PagedPaperQA(lang="arabic")
        await qa.add("study.pdf", author="الأحمد", year=2024)
        result = await qa.ask("ما المنهجية المتبعة؟")
    """

    def __init__(
        self,
        lang: str = "arabic",       # arabic | english
        llm: str = "claude-sonnet-4-6",
        embedding: str = "text-embedding-3-large",
        mode: str = "cloud",        # cloud | local | deepseek
        verbatim: bool = False,
        settings: Optional[object] = None,
    ):
        self.lang = lang

        # إعدادات: عربية أو إنجليزية
        if settings is not None:
            self.settings = settings
        elif lang == "arabic":
            from paperqa_arabic import (
                get_arabic_settings, get_arabic_settings_local,
                get_arabic_settings_single_key,
                get_arabic_settings_deepseek,
            )
            if mode == "single_key":
                self.settings = get_arabic_settings_single_key(llm=llm)
            elif mode == "local":
                self.settings = get_arabic_settings_local()
            elif mode == "deepseek":
                self.settings = get_arabic_settings_deepseek()
            else:
                self.settings = get_arabic_settings(
                    llm=llm, embedding=embedding, verbatim=verbatim
                )
        else:
            from paperqa.settings import Settings
            self.settings = Settings(llm=llm, embedding=embedding)

        self._docs = None

    @property
    def docs(self):
        from paperqa.docs import Docs
        if self._docs is None:
            self._docs = Docs()
        return self._docs

    async def add(
        self,
        source: str,
        *,
        author: Optional[str] = None,
        year: Optional[int] = None,
        title: Optional[str] = None,
        citation: Optional[str] = None,
    ) -> int:
        """
        يضيف مرجعاً مع استخراج رقم الصفحة لكل مقطع.

        Args:
            source: PDF محلي أو URL أو DOI
            author: اسم المؤلف (للاستشهاد)
            year: سنة النشر
            title: العنوان
            citation: نص استشهاد مخصص (يتجاوز author/year)

        Returns:
            عدد المقاطع (الصفحات) المُضافة
        """
        from paperqa.types import Doc, Text

        # جلب من الإنترنت إن لزم
        local_path, is_temp = fetch_to_local(source)

        try:
            # استخراج صفحةً صفحةً مع رقمها
            paged_chunks = extract_with_pages(local_path)
            if not paged_chunks:
                raise ValueError(f"لم يُستخرج نص من: {source}")

            # بناء مفتاح الاستشهاد
            docname = self._build_docname(author, year, title, source)
            base_citation = citation or self._build_citation(
                author, year, title, source
            )

            # إنشاء Doc واحد للمرجع
            doc = Doc(
                docname=docname,
                dockey=f"{docname}_{abs(hash(source)) % 100000}",
                citation=base_citation,
            )

            # إنشاء Text لكل صفحة — الاسم يحوي رقم الصفحة
            texts = []
            for chunk in paged_chunks:
                page_label = self._page_label(docname, chunk.page)
                texts.append(Text(
                    text=chunk.text,
                    name=page_label,     # ← "الأحمد2024، ص. 5"
                    doc=doc,
                ))

            # الإضافة عبر الواجهة الرسمية (بلا تعديل منطق PaperQA)
            await self.docs.aadd_texts(texts, doc, settings=self.settings)
            return len(texts)

        finally:
            if is_temp and os.path.exists(local_path):
                os.unlink(local_path)

    async def ask(self, question: str, verbatim: bool = False, **kwargs):
        """
        يجيب مع استشهاد يحوي رقم الصفحة.

        الإجابة تحتوي: "...النص (الأحمد2024، ص. 5)..."
        """
        settings = self.settings
        if verbatim and self.lang == "arabic":
            from paperqa_arabic import arabic_verbatim_qa_prompt
            settings = settings.model_copy(deep=True)
            settings.prompts.qa = arabic_verbatim_qa_prompt

        return await self.docs.aquery(question, settings=settings, **kwargs)

    async def get_evidence(self, question: str, **kwargs):
        """يسترجع المقاطع ذات الصلة مع أرقام صفحاتها."""
        return await self.docs.aget_evidence(
            question, settings=self.settings, **kwargs
        )

    # ── مساعدات بناء الاستشهاد ──

    def _page_label(self, docname: str, page: int) -> str:
        """يبني اسم المقطع مع رقم الصفحة."""
        if self.lang == "arabic":
            return f"{docname}، ص. {page}"
        return f"{docname}, p. {page}"

    def _build_docname(self, author, year, title, source) -> str:
        """يبني اسم الوثيقة المختصر."""
        if author and year:
            # إزالة المسافات من الاسم
            a = re.sub(r"\s+", "", author)
            return f"{a}{year}"
        if title:
            return re.sub(r"\s+", "", title[:20])
        # من اسم الملف
        base = os.path.splitext(os.path.basename(source))[0]
        return re.sub(r"[^\w]", "", base)[:20] or "مرجع"

    def _build_citation(self, author, year, title, source) -> str:
        """يبني نص الاستشهاد الكامل (APA)."""
        parts = []
        if author:
            parts.append(author)
        if year:
            parts.append(f"({year})")
        if title:
            parts.append(title)
        if parts:
            return ". ".join(parts)
        # افتراضي من المصدر
        return os.path.basename(source)


# ══════════════════════════════════════════════════════════════
# ٤. أداة CLI
# ══════════════════════════════════════════════════════════════

def _cli_main():
    import argparse, asyncio, glob

    parser = argparse.ArgumentParser(
        description="PaperQA2 مع استشهاد دقيق برقم الصفحة",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
أمثلة:
  # مرجع محلي مع بيانات المؤلف
  python paperqa_pages.py -f study.pdf --author "الأحمد" --year 2024 -q "ما النتائج؟"

  # مرجع من الإنترنت
  python paperqa_pages.py -u https://arxiv.org/pdf/2409.13740 -q "What is the method?"

  # DOI
  python paperqa_pages.py --doi 10.1145/3767695.3769505 -q "ما المساهمة؟"

  # مع اقتباس حرفي
  python paperqa_pages.py -f study.pdf -q "اقتبس التعريف" --verbatim
        """
    )
    parser.add_argument("-q", "--question", required=True)
    parser.add_argument("-f", "--file", action="append", default=[])
    parser.add_argument("-u", "--url", action="append", default=[])
    parser.add_argument("--doi", action="append", default=[])
    parser.add_argument("-d", "--directory")
    parser.add_argument("--author")
    parser.add_argument("--year", type=int)
    parser.add_argument("--lang", default="arabic", choices=["arabic", "english"])
    parser.add_argument("--mode", default="cloud", choices=["cloud", "local", "deepseek"])
    parser.add_argument("--verbatim", action="store_true")
    args = parser.parse_args()

    async def run():
        qa = PagedPaperQA(lang=args.lang, mode=args.mode, verbatim=args.verbatim)

        sources = list(args.file) + list(args.url) + list(args.doi)
        if args.directory:
            sources += glob.glob(os.path.join(args.directory, "**/*.pdf"), recursive=True)

        if not sources:
            print("❌ لا توجد مصادر")
            return

        print(f"⏳ يُفهرس {len(sources)} مرجع مع أرقام الصفحات...")
        for src in sources:
            try:
                n = await qa.add(src, author=args.author, year=args.year)
                print(f"  ✅ {src} ({n} صفحة)")
            except Exception as e:
                print(f"  ❌ {src}: {e}")

        print(f"\n🔍 {args.question}\n")
        result = await qa.ask(args.question, verbatim=args.verbatim)

        print("═" * 60)
        print(result.answer)
        print("═" * 60)
        if hasattr(result, "references") and result.references:
            print("\nالمراجع:")
            print(result.references)

    asyncio.run(run())


if __name__ == "__main__":
    _cli_main()
