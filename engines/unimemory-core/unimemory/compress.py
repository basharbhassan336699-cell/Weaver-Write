"""
ضغط الذكريات — مستوحى من OpenMemory MemoryCompressionEngine.

يقلّص طول الذكريات القديمة دون فقد المعنى:
  - إزالة الحشو (fillers)
  - اختصار العبارات الطويلة
  - تقلّصات نحوية
  - إزالة الجمل المكررة

يُستخدم على الذكريات المتلاشية بدل حذفها — يحفظ الجوهر ويوفّر المساحة.
"""

from __future__ import annotations
import re
import time


# عبارات حشو تُحذف (عربي + إنجليزي)
_FILLERS = [
    r"\b(just|really|very|quite|rather|somewhat|somehow)\b",
    r"\b(actually|basically|essentially|literally)\b",
    r"\b(I think that|I believe that|It seems that|It appears that)\b",
    r"\b(in order to)\b",
    r"\b(في الواقع|بشكل أساسي|في الحقيقة|نوعاً ما)\b",
    r"\b(أعتقد أن|أظن أن|يبدو أن)\b",
]

# اختصارات العبارات الطويلة
_REPLACEMENTS = [
    (r"\bat this point in time\b", "now"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bin the event that\b", "if"),
    (r"\bfor the purpose of\b", "to"),
    (r"\bin the near future\b", "soon"),
    (r"\ba number of\b", "several"),
    (r"\bprior to\b", "before"),
    (r"\bsubsequent to\b", "after"),
    (r"\bمن أجل أن\b", "لـ"),
    (r"\bبسبب حقيقة أن\b", "لأن"),
    (r"\bفي حالة أن\b", "إذا"),
]

# تقلّصات نحوية إنجليزية
_CONTRACTIONS = [
    (r"\bdo not\b", "don't"), (r"\bcannot\b", "can't"),
    (r"\bwill not\b", "won't"), (r"\bit is\b", "it's"),
    (r"\bthat is\b", "that's"), (r"\bwhat is\b", "what's"),
    (r"\bthere is\b", "there's"),
]


class Compressor:
    """محرك ضغط الذكريات — بلا LLM، سريع، آمن."""

    def __init__(self):
        self.stats = {"compressed": 0, "original_chars": 0, "compressed_chars": 0}

    @staticmethod
    def tokens(text: str) -> int:
        """تقدير عدد الـ tokens."""
        if not text:
            return 0
        words = len(re.split(r"\s+", text.strip()))
        return int(len(text) / 4 + words / 2) + 1

    def _dedupe_sentences(self, text: str) -> str:
        """إزالة الجمل المكررة المتتالية."""
        parts = re.split(r"([.!?؟]+\s+)", text)
        seen_prev = ""
        result = []
        for part in parts:
            norm = part.lower().strip()
            if norm and norm == seen_prev:
                continue
            result.append(part)
            if norm:
                seen_prev = norm
        return "".join(result)

    def compress(self, text: str, aggressive: bool = False) -> str:
        """
        يضغط نصاً مع الحفاظ على المعنى.

        Args:
            text: النص الأصلي
            aggressive: ضغط أقوى (تقلّصات + حذف أدوات التعريف الزائدة)
        """
        if not text or len(text) < 50:
            return text  # النصوص القصيرة لا تُضغط

        c = text

        # إزالة الجمل المكررة
        c = self._dedupe_sentences(c)

        # إزالة الحشو
        for pattern in _FILLERS:
            c = re.sub(pattern, "", c, flags=re.IGNORECASE)

        # اختصار العبارات
        for pattern, repl in _REPLACEMENTS:
            c = re.sub(pattern, repl, c, flags=re.IGNORECASE)

        # ضغط قوي
        if aggressive:
            for pattern, repl in _CONTRACTIONS:
                c = re.sub(pattern, repl, c, flags=re.IGNORECASE)

        # تنظيف المسافات
        c = re.sub(r"\s+", " ", c).strip()
        c = re.sub(r"\s+([.!?،؟])", r"\1", c)  # مسافة قبل الترقيم

        # تسجيل الإحصاء
        self.stats["compressed"] += 1
        self.stats["original_chars"] += len(text)
        self.stats["compressed_chars"] += len(c)

        return c

    def ratio(self) -> float:
        """نسبة الضغط المحققة."""
        orig = self.stats["original_chars"]
        comp = self.stats["compressed_chars"]
        return (1 - comp / orig) if orig else 0.0
