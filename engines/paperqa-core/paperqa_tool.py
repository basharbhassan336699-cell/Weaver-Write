"""
engines/paperqa-core/paperqa_tool.py
======================================
أداة PaperQA-core مُغلّفة للاستدعاء من Weaver Write.

الاستدعاء يتم من طبقتَي البحث (٤) والتحقق (٧) عندما تتطلب
المهمة بحثاً أكاديمياً أو توثيقاً دقيقاً بأرقام الصفحات.

قواعد Direct Code Integration (لا تعديل على المنطق الأصلي):
  - paperqa_pages.py  → يُستورد كما هو
  - paperqa_arabic.py → يُستورد كما هو
  - src/paperqa/      → يُستورد كما هو

كيف يُستدعى:
    from engines.paperqa_core.paperqa_tool import PaperQATool

    tool = PaperQATool()
    result = await tool.run({
        "question": "ما تأثير التكنولوجيا على التعليم؟",
        "sources": ["https://arxiv.org/pdf/...", "study.pdf"],
        "lang": "arabic",
    })
"""

from __future__ import annotations
import os
import sys
import asyncio
from dataclasses import dataclass, field
from typing import Optional

# ── تسجيل مسار المحرك ─────────────────────────────────────────
_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
_PAPERQA_SRC = os.path.join(_ENGINE_DIR, "src")
if _PAPERQA_SRC not in sys.path:
    sys.path.insert(0, _PAPERQA_SRC)
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)


# ══════════════════════════════════════════════════════════════
# ١. مواصفات الأداة (للاستدعاء الآلي من النظام)
# ══════════════════════════════════════════════════════════════

TOOL_SPEC = {
    "name": "paperqa_academic_search",
    "description": (
        "بحث أكاديمي RAG مع استشهاد دقيق يشمل رقم الصفحة. "
        "استخدم عندما تحتاج المهمة إلى: "
        "(١) إيجاد دراسات من Semantic Scholar / CrossRef / OpenAlex / arXiv، "
        "(٢) استشهاد بصيغة (مؤلف، سنة، ص. X)، "
        "(٣) تحقق من أن المعلومة موجودة فعلاً في المرجع."
    ),
    "triggers": [
        "بحث علمي", "مراجع أكاديمية", "دراسات سابقة", "literature review",
        "استشهاد", "توثيق", "مرجع", "PDF أكاديمي", "arXiv", "DOI",
        "Semantic Scholar", "CrossRef", "OpenAlex", "Unpaywall",
        "ص.", "p.", "page", "صفحة", "تحقق من المرجع",
    ],
    "layers": [4, 7],
    "required_inputs": ["question"],
    "optional_inputs": ["sources", "lang", "mode", "verbatim"],
    "output_fields": ["answer", "references", "citations", "verified", "pages_found"],
}


# ══════════════════════════════════════════════════════════════
# ٢. نتيجة الأداة
# ══════════════════════════════════════════════════════════════

@dataclass
class PaperQAResult:
    """نتيجة استدعاء PaperQA-core."""
    answer: str = ""
    references: str = ""
    citations: list[dict] = field(default_factory=list)
    pages_found: dict = field(default_factory=dict)
    verified: bool = False
    verification_report: dict = field(default_factory=dict)
    sources_indexed: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "references": self.references,
            "citations": self.citations,
            "pages_found": self.pages_found,
            "verified": self.verified,
            "verification_report": self.verification_report,
            "sources_indexed": self.sources_indexed,
            "error": self.error,
        }


# ══════════════════════════════════════════════════════════════
# ٣. الأداة الرئيسية
# ══════════════════════════════════════════════════════════════

class PaperQATool:
    """
    أداة PaperQA-core لـ Weaver Write.

    تُغلّف PagedPaperQA وتضيف واجهة موحدة مع بقية أدوات النظام.

    المتطلبات:
        pip install paper-qa pymupdf4llm
        (اختياري للـ OCR: apt install tesseract-ocr tesseract-ocr-ara)
    """

    TOOL_NAME = "paperqa_academic_search"

    def __init__(
        self,
        lang: str = "arabic",
        mode: str = "cloud",
        llm: str = "claude-sonnet-4-6",
        embedding: str = "text-embedding-3-large",
    ):
        self.lang = lang
        self.mode = mode
        self.llm = llm
        self.embedding = embedding
        self._qa = None

    def _get_qa(self):
        if self._qa is None:
            from paperqa_pages import PagedPaperQA
            self._qa = PagedPaperQA(
                lang=self.lang,
                mode=self.mode,
                llm=self.llm,
                embedding=self.embedding,
            )
        return self._qa

    async def run(self, inputs: dict) -> PaperQAResult:
        """
        الواجهة الموحدة للاستدعاء من Pipeline.

        inputs:
            question   (مطلوب): السؤال البحثي
            sources    (اختياري): قائمة PDFs / URLs / DOIs
            lang       (اختياري): arabic | english
            mode       (اختياري): cloud | local | deepseek
            verbatim   (اختياري): اقتباس حرفي
        """
        question = inputs.get("question", "").strip()
        if not question:
            return PaperQAResult(error="السؤال مطلوب")

        sources  = inputs.get("sources", [])
        lang     = inputs.get("lang", self.lang)
        mode     = inputs.get("mode", self.mode)
        verbatim = inputs.get("verbatim", False)

        if lang != self.lang or mode != self.mode:
            self._qa = None
            self.lang = lang
            self.mode = mode

        result = PaperQAResult()

        try:
            qa = self._get_qa()

            for src in sources:
                try:
                    author, year = self._parse_source_meta(src)
                    n = await qa.add(src, author=author, year=year)
                    result.sources_indexed += 1
                    print(f"    📄 PaperQA: فُهرس {src} ({n} صفحة)")
                except Exception as e:
                    print(f"    ⚠️  PaperQA: تخطّي {src}: {e}")

            pqa_result = await qa.ask(question, verbatim=verbatim)

            result.answer     = getattr(pqa_result, "answer", "") or ""
            result.references = getattr(pqa_result, "references", "") or ""
            result.citations    = self._parse_citations(result.answer, lang)
            result.pages_found  = self._extract_pages(result.citations)
            result.verified     = len(result.citations) > 0

        except ImportError as e:
            result.error = (
                f"paperqa-core غير مثبت: {e}\n"
                "pip install paper-qa pymupdf4llm"
            )
        except Exception as e:
            result.error = str(e)

        return result

    async def verify(self, text: str, question: str) -> PaperQAResult:
        """طبقة ٧: تحقق من استشهادات نص موجود."""
        result = PaperQAResult()
        citations = self._parse_citations(text, self.lang)
        verified_list, failed_list, partial_list = [], [], []
        qa = self._get_qa()

        for cit in citations:
            key  = cit.get("key", "")
            page = cit.get("page")
            try:
                evidence = await qa.get_evidence(f"ما محتوى صفحة {page} في {key}؟")
                contexts = getattr(evidence, "contexts", [])
                found_page = any(
                    key in getattr(c, "text", {}).get("name", "")
                    and str(page) in getattr(c, "text", {}).get("name", "")
                    for c in contexts
                )
                if found_page:
                    verified_list.append(cit)
                elif contexts:
                    partial_list.append({**cit, "note": "المرجع موجود لكن الصفحة غير مؤكدة"})
                else:
                    failed_list.append({**cit, "note": "المرجع غير موجود في قاعدة RAG"})
            except Exception as e:
                failed_list.append({**cit, "note": str(e)})

        total = len(citations) or 1
        score = int((len(verified_list) / total) * 100)
        result.verified = score >= 70
        result.verification_report = {
            "verified": verified_list,
            "partial":  partial_list,
            "failed":   failed_list,
            "score":    score,
            "total":    len(citations),
            "summary":  f"{len(verified_list)}/{len(citations)} استشهاد مؤكد ({score}%)",
        }
        result.citations = citations
        return result

    @staticmethod
    def _parse_source_meta(source: str):
        import re
        basename = os.path.splitext(os.path.basename(source))[0]
        year_match = re.search(r"(19|20)\d{2}", basename)
        year = int(year_match.group()) if year_match else None
        author = re.sub(r"(19|20)\d{2}.*", "", basename).strip("_- ") or None
        return author, year

    @staticmethod
    def _parse_citations(text: str, lang: str = "arabic") -> list[dict]:
        import re
        citations, seen = [], set()
        pattern = (r"\(([^،()]+?)،?\s*ص\.\s*(\d+)\)" if lang == "arabic"
                   else r"\(([^,()]+?),?\s*p\.\s*(\d+)\)")
        for match in re.finditer(pattern, text):
            key, page = match.group(1).strip(), int(match.group(2))
            uid = f"{key}:{page}"
            if uid not in seen:
                seen.add(uid)
                start = max(0, match.start() - 80)
                end   = min(len(text), match.end() + 80)
                citations.append({
                    "key": key, "page": page,
                    "context": text[start:end].strip(),
                    "raw": match.group(0),
                })
        return citations

    @staticmethod
    def _extract_pages(citations: list[dict]) -> dict:
        pages: dict = {}
        for cit in citations:
            key = cit["key"]
            if key not in pages:
                pages[key] = []
            if cit["page"] not in pages[key]:
                pages[key].append(cit["page"])
        return pages


# ══════════════════════════════════════════════════════════════
# ٤. دوال مساعدة للاستدعاء المباشر من الطبقات
# ══════════════════════════════════════════════════════════════

def register_tool(registry: dict):
    """يُسجّل PaperQATool في سجل أدوات النظام."""
    tool = PaperQATool()
    registry[PaperQATool.TOOL_NAME] = {
        "instance": tool,
        "spec":     TOOL_SPEC,
        "run":      tool.run,
        "verify":   tool.verify,
    }
    print(f"  ✅ أداة مسجّلة: {PaperQATool.TOOL_NAME}")
    return tool


async def academic_search(
    question: str,
    sources: list = None,
    lang: str = "arabic",
    mode: str = "cloud",
    verbatim: bool = False,
) -> PaperQAResult:
    """واجهة مبسّطة للاستدعاء المباشر من أي طبقة."""
    tool = PaperQATool(lang=lang, mode=mode)
    return await tool.run({
        "question": question,
        "sources":  sources or [],
        "verbatim": verbatim,
    })


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--question", required=True)
    parser.add_argument("-s", "--source", action="append", default=[])
    parser.add_argument("--lang", default="arabic")
    parser.add_argument("--mode", default="cloud")
    parser.add_argument("--verbatim", action="store_true")
    args = parser.parse_args()

    async def _main():
        result = await academic_search(
            args.question, args.source, args.lang, args.mode, args.verbatim
        )
        if result.error:
            print(f"❌ {result.error}")
        else:
            print("═" * 60)
            print(result.answer)
            if result.references:
                print("\nالمراجع:\n" + result.references)
            if result.pages_found:
                print("\nالصفحات:")
                for ref, pages in result.pages_found.items():
                    print(f"  {ref}: {pages}")

    asyncio.run(_main())
