"""
PaperQA2 — دعم اللغة العربية الكامل
=====================================

يُضيف هذا الملف دعم البحث والإجابة والاستشهاد بالكامل باللغة العربية
دون تعديل أي كود أصلي من PaperQA2.

كيفية الاستخدام:
    from paperqa_arabic import get_arabic_settings, ArabicPaperQA

    # الأبسط
    qa = ArabicPaperQA()
    await qa.add("بحث_عربي.pdf")
    result = await qa.ask("ما النتائج الرئيسية؟")
    print(result.answer)

المصدر: يعتمد فقط على:
    - paperqa.settings.Settings      ← الإعدادات الأصلية
    - paperqa.settings.PromptSettings ← قوالب النصوص
    - paperqa.docs.Docs               ← الواجهة الأصلية
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional


# ══════════════════════════════════════════════════════════════
# ١. قوالب النصوص العربية (Arabic Prompts)
# ══════════════════════════════════════════════════════════════

# رمز الاستشهاد — محفوظ بالصيغة الأصلية (لا يتغير)
ARABIC_CITATION_KEY_CONSTRAINTS = (
    "## أمثلة على الاستشهادات الصحيحة (استخدم الأقواس فقط):\n"
    "- (pqac-d79ef6fa, pqac-0f650d59)\n"
    "- (pqac-d79ef6fa)\n"
    "## أمثلة على الاستشهادات الخاطئة (تجنّبها):\n"
    "- (pqac-d79ef6fa و pqac-0f650d59)\n"
    "- (pqac-d79ef6fa;pqac-0f650d59)\n"
    "- مؤلف وآخرون (2023)\n"
    "- انظر: pqac-d79ef6fa"
)

ARABIC_CANNOT_ANSWER = "لا أستطيع الإجابة"

# قالب ملخص المقطع
arabic_summary_json_prompt = (
    "مقتطف من: {citation}\n\n---\n\n{text}\n\n---\n\nالسؤال: {question}"
)

arabic_summary_prompt = (
    "لخّص المقتطف أدناه للمساعدة في الإجابة على السؤال."
    f"\n\n{arabic_summary_json_prompt}\n\n"
    "لا تُجب على السؤال مباشرةً، بل لخّص المعلومات التي قد تساعد في الإجابة."
    " كن دقيقاً ومفصّلاً؛ أذكر الأرقام والمعادلات والاقتباسات الحرفية"
    ' (مع علامات الاقتباس). أجب بـ "غير ذي صلة" إن كان المقتطف غير متعلق بالسؤال.'
    " في نهاية إجابتك، اكتب درجة صحيحة من 1 إلى 10 على سطر منفصل"
    " تشير إلى مدى صلة المقتطف بالسؤال. لا تشرح الدرجة."
    "\n\nملخص المعلومات ذات الصلة ({summary_length}):"
)

# قالب الإجابة النهائية
arabic_qa_prompt = (
    "أجب على السؤال أدناه بناءً على السياق المقدّم.\n\n"
    "السياق:\n\n{context}\n\n---\n\n"
    "السؤال: {question}\n\n"
    "اكتب إجابة شاملة ومدعومة بالأدلة من السياق. "
    f'إن كان السياق غير كافٍ للإجابة، اكتب: "{ARABIC_CANNOT_ANSWER}". '
    "لكل جزء من إجابتك، أشر إلى المصادر الداعمة باستخدام مفاتيح الاستشهاد"
    " في نهاية الجمل، مثل: {example_citation}. "
    "استخدم فقط مفاتيح الاستشهاد الواردة في السياق أعلاه."
    f"\n\n{ARABIC_CITATION_KEY_CONSTRAINTS}\n\n"
    "لا تدمج مفاتيح الاستشهاد، واستخدمها كما هي. "
    "اكتب بأسلوب المقالات العلمية: جمل موجزة وفقرات متماسكة. "
    "لا تُضف معلومات خارج نطاق السياق المقدّم.\n\n"
    "{prior_answer_prompt}"
    "الإجابة ({answer_length}):"
)

# قالب اختيار الأوراق البحثية
arabic_select_paper_prompt = (
    "اختر الأوراق البحثية التي قد تساعد في الإجابة على السؤال أدناه. "
    "الأوراق مُدرجة بصيغة $المفتاح: $معلومات_الورقة. "
    "أعد قائمة المفاتيح مفصولةً بفواصل. "
    'أعد "لا يوجد" إن لم تكن هناك أوراق مناسبة. '
    "اختر الأوراق ذات الصلة، من مصادر موثوقة، وحديثة إن تطلّب السؤال ذلك.\n\n"
    "السؤال: {question}\n\n"
    "الأوراق: {papers}\n\n"
    "المفاتيح المختارة:"
)

# قالب الاستشهاد (صيغة APA مناسبة للأدبيات العربية + الأجنبية)
arabic_citation_prompt = (
    "أنشئ الاستشهاد الببليوغرافي للنص التالي بأسلوب APA المعدَّل للمصادر العربية. "
    "لا تكتب جملة تمهيدية. "
    "لا تخترع DOI مثل '10.xxxx' إن لم يكن موجوداً، بل احذفه. "
    "في حالة المصادر العربية: ابدأ باسم المؤلف (اللقب، الاسم)، ثم السنة بين قوسين، "
    "ثم العنوان، ثم المجلة أو الناشر، ثم رقم المجلد والعدد والصفحات. "
    f"إن ذكرت تاريخ الوصول، السنة الحالية هي {datetime.now().year}.\n\n"
    "{text}\n\n"
    "الاستشهاد:"
)

# قالب استخراج بيانات الاستشهاد المنظّمة
arabic_structured_citation_prompt = (
    "استخرج العنوان والمؤلفين والـ DOI بصيغة JSON من هذا الاستشهاد. "
    "إن تعذّر إيجاد أي حقل، أعده كـ null. "
    "استخدم المفاتيح: title (العنوان)، authors (قائمة المؤلفين)، doi. "
    "{citation}\n\n"
    "JSON الاستشهاد:"
)

# النظام الافتراضي
arabic_default_system_prompt = (
    "أجب بأسلوب مباشر وموجز باللغة العربية الفصحى. "
    "جمهورك من المختصين، لذا كن دقيقاً ومحدداً. "
    "عرِّف المصطلحات الغامضة أو الاختصارات عند أول استخدام. "
    "الاستشهادات بالمصادر إلزامية ومنسّقة بأسلوب APA."
)

# نظام ملخص JSON
arabic_summary_json_system_prompt = (
    "قدّم ملخصاً للمعلومات ذات الصلة التي قد تساعد في الإجابة على السؤال"
    " بناءً على المقتطف. ملخّصك، مع ملخصات أخرى، سيُعطى للنموذج لتوليد الإجابة."
    " أجب بصيغة JSON التالية:"
    '\n\n{{\n  "summary": "...",\n  "relevance_score": 0-10\n}}'
    "\n\nحيث `summary` هو معلومات ذات صلة من النص - {summary_length}."
    " `relevance_score` عدد صحيح 0-10 يعبّر عن مدى صلة الملخص بالسؤال."
    "\n\nقد يحتوي المقتطف على معلومات ذات صلة أو لا."
    " إن لم يكن كذلك، اترك `summary` فارغاً واجعل `relevance_score` صفراً."
)

# نظام بيئة الوكيل
arabic_env_system_prompt = "أنت مساعد بحثي ذكي متخصص في الأدبيات العلمية والأكاديمية."

arabic_env_reset_prompt = (
    "استخدم الأدوات للإجابة على السؤال: {question}"
    "\n\nعندما تبدو الإجابة كافية، أنهِ بالاستدعاء {complete_tool_name}. "
    "إن لم تكن الإجابة كافية ولقد جرّبت عدة مرات، أنهِ أيضاً بـ {complete_tool_name}. "
    "الوضع الحالي للأدلة/الأوراق/التكلفة: {status}"
)

# قالب إعادة التكرار
arabic_answer_iteration_prompt = (
    "أنت تُحسّن إجابة سابقة مع سياق مختلف محتمل:\n\n"
    "{prior_answer}\n\n"
    "أنشئ إجابة جديدة مستخدماً فقط مفاتيح السياق والبيانات المُدرجة أعلاه. "
    "لا يمكنك استخدام مفاتيح السياق من الإجابة السابقة غير الموجودة في السياق الحالي.\n\n"
)

# ══════════════════════════════════════════════════════════════
# قالب السياق مع رقم الموقع (chunk → بديل رقم الصفحة)
# {name} يحتوي "Author2023 chunk 3" → يُعرض كموقع في الاستشهاد
# ══════════════════════════════════════════════════════════════
arabic_context_inner_prompt = (
    "{name}: {text}\n"
    "المصدر: {citation}"
)

# ══════════════════════════════════════════════════════════════
# قالب الإجابة مع تنصيص حرفي إلزامي
# يُستخدم عند طلب الاقتباس المباشر من المصادر
# ══════════════════════════════════════════════════════════════
arabic_verbatim_qa_prompt = (
    "أجب على السؤال أدناه بناءً على السياق المقدّم.\n\n"
    "السياق:\n\n{context}\n\n---\n\n"
    "السؤال: {question}\n\n"
    "تعليمات التنصيص الإلزامية:\n"
    "- عند الاقتباس الحرفي من المصدر، ضع النص بين علامتي تنصيص «» ثم أضف"
    " الاستشهاد مباشرةً: «النص الحرفي» (pqac-xxxxx)\n"
    "- إن كان الاقتباس من صفحة أو موقع محدد من المقطع، أضفه:"
    " «النص» (pqac-xxxxx، الموقع: Author2023 chunk 3)\n"
    "- لكل جزء تحليلي غير منصوص، استشهد بالمصدر في نهاية الجملة.\n"
    f"- إن كان السياق غير كافٍ: اكتب \"{ARABIC_CANNOT_ANSWER}\"\n\n"
    f"{ARABIC_CITATION_KEY_CONSTRAINTS}\n\n"
    "اكتب بأسلوب أكاديمي مع التمييز الواضح بين الاقتباس الحرفي والتحليل.\n\n"
    "{prior_answer_prompt}"
    "الإجابة ({answer_length}):"
)


# ══════════════════════════════════════════════════════════════
# ٢. إعدادات عربية جاهزة (Arabic Settings Factory)
# ══════════════════════════════════════════════════════════════

def get_arabic_settings(
    llm: str = "claude-sonnet-4-6",
    embedding: str = "text-embedding-3-large",
    answer_length: str = "إجابة تفصيلية من 3 إلى 5 فقرات",
    evidence_k: int = 10,
    verbatim: bool = False,
    **extra_settings,
):
    """
    يُنشئ إعدادات PaperQA2 مُحسَّنة للغة العربية.

    Args:
        llm: النموذج اللغوي (الأفضل: claude-sonnet-4-6 أو gpt-4o)
        embedding: نموذج التضمين (يدعم العربية)
        answer_length: طول الإجابة المطلوب
        evidence_k: عدد المقاطع المسترجعة
        **extra_settings: إعدادات إضافية تُمرَّر لـ Settings

    Returns:
        Settings: إعدادات جاهزة للاستخدام مع اللغة العربية
    """
    # الاستيراد هنا لتجنب دائرة الاستيراد
    from paperqa.settings import Settings, PromptSettings, AnswerSettings

    arabic_prompts = PromptSettings(
        summary=arabic_summary_prompt,
        qa=arabic_verbatim_qa_prompt if verbatim else arabic_qa_prompt,
        select=arabic_select_paper_prompt,
        citation_prompt=arabic_citation_prompt,
        structured_citation_prompt=arabic_structured_citation_prompt,
        system=arabic_default_system_prompt,
        summary_json_system=arabic_summary_json_system_prompt,
        answer_iteration_prompt=arabic_answer_iteration_prompt,
        context_inner_prompt=arabic_context_inner_prompt,
    )

    arabic_answer = AnswerSettings(
        evidence_k=evidence_k,
        answer_length=answer_length,
    )

    settings = Settings(
        llm=llm,
        embedding=embedding,
        prompts=arabic_prompts,
        answer=arabic_answer,
        **extra_settings,
    )

    return settings


def get_arabic_settings_single_key(
    llm: str = "claude-sonnet-4-6",
    st_embedding: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    answer_length: str = "إجابة تفصيلية من 3 إلى 5 فقرات",
    evidence_k: int = 10,
    verbatim: bool = False,
    **extra_settings,
):
    """
    إعدادات بمفتاح API واحد فقط (مفتاح النظام):
    - النموذج اللغوي (llm) يستخدم مفتاح النظام (Anthropic أو غيره).
    - التضمين (embedding) محلي عبر SentenceTransformer متعدد اللغات
      (يدعم العربية) — لا يحتاج مفتاحاً ثانياً ولا اتصالاً سحابياً.

    بهذا يعمل البحث الأكاديمي كاملاً على مفتاح AI واحد.
    """
    from paperqa.settings import Settings, PromptSettings, AnswerSettings

    arabic_prompts = PromptSettings(
        summary=arabic_summary_prompt,
        qa=arabic_verbatim_qa_prompt if verbatim else arabic_qa_prompt,
        select=arabic_select_paper_prompt,
        citation_prompt=arabic_citation_prompt,
        structured_citation_prompt=arabic_structured_citation_prompt,
        system=arabic_default_system_prompt,
        summary_json_system=arabic_summary_json_system_prompt,
        answer_iteration_prompt=arabic_answer_iteration_prompt,
        context_inner_prompt=arabic_context_inner_prompt,
    )
    arabic_answer = AnswerSettings(evidence_k=evidence_k,
                                   answer_length=answer_length)
    # local multilingual embeddings -> no second key
    settings = Settings(
        llm=llm,
        embedding=f"st-{st_embedding}",  # 'st-' prefix = SentenceTransformer (local)
        prompts=arabic_prompts,
        answer=arabic_answer,
        **extra_settings,
    )
    return settings


def get_arabic_settings_local(
    ollama_url: str = "http://localhost:11434",
    llm_model: str = "llama3.2",
    embedding_model: str = "nomic-embed-text",
    **extra_settings,
):
    """
    إعدادات عربية للعمل محلياً مع Ollama (بدون API).

    Args:
        ollama_url: عنوان خادم Ollama
        llm_model: النموذج المحلي
        embedding_model: نموذج التضمين المحلي
    """
    return get_arabic_settings(
        llm=f"ollama/{llm_model}",
        embedding=f"ollama/{embedding_model}",
        llm_config={"api_base": ollama_url},
        **extra_settings,
    )


def get_arabic_settings_deepseek(
    api_key: Optional[str] = None,
    model: str = "deepseek-chat",
    **extra_settings,
):
    """إعدادات عربية مع DeepSeek."""
    import os
    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    return get_arabic_settings(
        llm=f"deepseek/{model}",
        embedding="text-embedding-3-large",
        llm_config={"api_key": key},
        **extra_settings,
    )


# ══════════════════════════════════════════════════════════════
# ٣. واجهة عربية مبسّطة (ArabicPaperQA)
# ══════════════════════════════════════════════════════════════

class ArabicPaperQA:
    """
    واجهة مبسّطة للبحث والاستشهاد بالعربية.

    مثال:
        qa = ArabicPaperQA(llm="claude-sonnet-4-6")
        await qa.add("دراسة_2024.pdf")
        await qa.add("https://doi.org/10.xxxx/yyyy")
        result = await qa.ask("ما أبرز نتائج هذه الدراسات؟")
        print(result.answer)
        for ctx in result.contexts:
            print(f"  [{ctx.text.name}] {ctx.context}")
    """

    def __init__(
        self,
        llm: str = "claude-sonnet-4-6",
        embedding: str = "text-embedding-3-large",
        mode: str = "cloud",        # cloud | local | deepseek
        ollama_url: str = "http://localhost:11434",
        verbatim: bool = False,     # تفعيل التنصيص الحرفي
        settings: Optional[object] = None,
    ):
        if settings is not None:
            self.settings = settings
        elif mode == "local":
            self.settings = get_arabic_settings_local(ollama_url=ollama_url)
        elif mode == "deepseek":
            self.settings = get_arabic_settings_deepseek()
        else:
            self.settings = get_arabic_settings(
                llm=llm, embedding=embedding, verbatim=verbatim
            )
        self._docs = None

    @property
    def docs(self):
        from paperqa.docs import Docs
        if self._docs is None:
            self._docs = Docs()
        return self._docs

    # ── OCR Pipeline (للملفات الممسوحة ضوئياً) ─────────────────
    @staticmethod
    def _ocr_to_text(pdf_path: str, lang: str = "ara+eng") -> Optional[str]:
        """
        يحوّل PDF ممسوح ضوئياً إلى نص عبر Tesseract.
        يعمل على Termux/CPU بدون GPU.

        Args:
            pdf_path: مسار PDF الممسوح
            lang: لغة OCR (ara=عربي، ara+eng=عربي+إنجليزي)

        Returns:
            النص المستخرج أو None عند الفشل
        """
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except ImportError:
            raise ImportError(
                "OCR يحتاج: pip install pdf2image pytesseract\n"
                "وتثبيت Tesseract: apt install tesseract-ocr tesseract-ocr-ara"
            )
        pages = convert_from_path(pdf_path)
        texts = []
        for i, page in enumerate(pages, 1):
            text = pytesseract.image_to_string(page, lang=lang)
            if text.strip():
                # إضافة رقم الصفحة الحقيقي كعلامة
                texts.append(f"[صفحة {i}]\n{text}")
        return "\n\n".join(texts) if texts else None

    @staticmethod
    def _is_scanned_pdf(pdf_path: str, text_threshold: int = 50) -> bool:
        """يكتشف إن كان PDF ممسوحاً ضوئياً (لا يحتوي نصاً كافياً)."""
        try:
            from paperqa.readers import parse_pdf_to_pages  # type: ignore
        except Exception:
            pass
        # طريقة بديلة: pypdf
        try:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            total_text = ""
            for page in reader.pages[:3]:  # فحص أول 3 صفحات فقط
                total_text += page.extract_text() or ""
            return len(total_text.strip()) < text_threshold
        except Exception:
            return False

    async def add(
        self,
        source: str,
        ocr: bool = False,
        ocr_lang: str = "ara+eng",
        ocr_force: bool = False,
        **kwargs,
    ) -> None:
        """
        يضيف وثيقة مع دعم OCR للملفات الممسوحة.

        Args:
            source: مسار PDF أو URL أو DOI
            ocr: تفعيل OCR تلقائياً عند الحاجة
            ocr_lang: لغة OCR (افتراضي: ara+eng)
            ocr_force: إجبار OCR حتى لو كان PDF يحتوي نصاً
        """
        import tempfile, os

        is_url = source.startswith("http://") or source.startswith("https://")
        is_doi = source.startswith("10.")

        if is_url:
            await self.docs.aadd_url(source, settings=self.settings, **kwargs)
            return
        if is_doi:
            await self.docs.aadd_url(
                f"https://doi.org/{source}", settings=self.settings, **kwargs
            )
            return

        # ── ملف محلي ──
        path = source
        needs_ocr = ocr_force or (
            ocr and path.lower().endswith(".pdf") and self._is_scanned_pdf(path)
        )

        if needs_ocr:
            # OCR → ملف نصي مؤقت → PaperQA
            text = self._ocr_to_text(path, lang=ocr_lang)
            if text:
                suffix = ".txt"
                base = os.path.splitext(os.path.basename(path))[0]
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=suffix, prefix=f"{base}_ocr_",
                    delete=False, encoding="utf-8"
                ) as tmp:
                    tmp.write(text)
                    tmp_path = tmp.name
                try:
                    await self.docs.aadd(tmp_path, settings=self.settings, **kwargs)
                finally:
                    os.unlink(tmp_path)
                return
            # OCR فشل → نحاول المسار العادي
        await self.docs.aadd(path, settings=self.settings, **kwargs)

    async def ask(
        self,
        question: str,
        verbatim: bool = False,
        **kwargs,
    ):
        """
        يجيب على سؤال بالعربية مع استشهادات دقيقة.

        Args:
            question: السؤال بالعربية أو الإنجليزية
            verbatim: طلب اقتباسات حرفية مع علامات تنصيص «»

        Returns:
            PQASession: يحتوي answer, contexts, references
        """
        settings = self.settings
        # إن طُلب التنصيص ولم يكن مفعّلاً في الإعدادات — نُنشئ نسخة مؤقتة
        if verbatim:
            from paperqa.settings import Settings
            settings = settings.model_copy(deep=True)
            settings.prompts.qa = arabic_verbatim_qa_prompt

        return await self.docs.aquery(question, settings=settings, **kwargs)

    async def get_evidence(self, question: str, **kwargs):
        """
        يسترجع المقاطع ذات الصلة فقط (بدون إجابة نهائية).
        مفيد لـ WeaverCode للتغذية في context window.
        """
        return await self.docs.aget_evidence(
            question, settings=self.settings, **kwargs
        )


# ══════════════════════════════════════════════════════════════
# ٤. أداة CLI سريعة
# ══════════════════════════════════════════════════════════════

def _cli_main():
    """تشغيل سريع من سطر الأوامر."""
    import argparse, asyncio

    parser = argparse.ArgumentParser(
        description="PaperQA2 باللغة العربية",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
أمثلة:
  python paperqa_arabic.py -d ./papers -q "ما أسباب السكري النوع الثاني؟"
  python paperqa_arabic.py -f paper.pdf -q "ما منهجية البحث؟" --mode local
  python paperqa_arabic.py -f paper.pdf -q "ما النتائج؟" --mode deepseek
        """
    )
    parser.add_argument("-q", "--question", required=True, help="السؤال بالعربية أو الإنجليزية")
    parser.add_argument("-d", "--directory", help="مجلد يحوي PDFs")
    parser.add_argument("-f", "--file", action="append", default=[], help="ملف PDF محدد")
    parser.add_argument("-u", "--url", action="append", default=[], help="رابط URL")
    parser.add_argument(
        "--mode", default="cloud",
        choices=["cloud", "local", "deepseek"],
        help="النموذج: cloud=Claude/GPT, local=Ollama, deepseek=DeepSeek"
    )
    parser.add_argument("--llm", default="claude-sonnet-4-6", help="النموذج السحابي")
    parser.add_argument(
        "--ocr", action="store_true",
        help="تفعيل OCR تلقائياً للملفات الممسوحة ضوئياً (يحتاج tesseract)"
    )
    parser.add_argument(
        "--ocr-force", action="store_true",
        help="إجبار OCR على كل الملفات"
    )
    parser.add_argument(
        "--ocr-lang", default="ara+eng",
        help="لغة OCR (افتراضي: ara+eng)"
    )
    parser.add_argument(
        "--verbatim", action="store_true",
        help="طلب اقتباسات حرفية «» مع مواقع المقاطع"
    )
    args = parser.parse_args()

    async def run():
        qa = ArabicPaperQA(llm=args.llm, mode=args.mode, verbatim=args.verbatim)

        # إضافة الملفات
        import glob, os
        sources = list(args.file) + list(args.url)
        if args.directory:
            sources += glob.glob(os.path.join(args.directory, "**/*.pdf"), recursive=True)

        if not sources:
            print("❌ لا توجد مصادر. استخدم -f أو -d أو -u")
            return

        print(f"⏳ يُفهرس {len(sources)} مصدر...")
        for src in sources:
            print(f"  + {src}")
            await qa.add(src, ocr=args.ocr, ocr_force=args.ocr_force, ocr_lang=args.ocr_lang)

        print(f"\n🔍 السؤال: {args.question}\n")
        result = await qa.ask(args.question, verbatim=args.verbatim)

        print("═" * 60)
        print("الإجابة:\n")
        print(result.answer)
        print("\n" + "═" * 60)
        if hasattr(result, 'references') and result.references:
            print("\nالمراجع:")
            print(result.references)

    asyncio.run(run())


if __name__ == "__main__":
    _cli_main()
