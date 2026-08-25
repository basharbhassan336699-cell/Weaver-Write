"""
core/thinking/__init__.py
=========================
Extended Thinking مدمجة كمحرك تفكير داخلي.

تُستخدم في ٣ طبقات:
  طبقة الفهم (٣)    → CoT لتحليل المهمة
  طبقة الصياغة (٦)  → ReAct + ToT لبناء البحث
  طبقة التحقق (٧)   → Extended Thinking للقرارات المعقدة
"""

from __future__ import annotations
import json
import os
import sys
from typing import Optional

THINKING_PATH = os.path.join(
    os.path.dirname(__file__), "../../engines/extended-thinking-hub"
)


class ThinkingEngine:
    """
    محرك التفكير الممتد لـ Weaver Write.

    يختار الإطار المناسب حسب المهمة:
      تحليل بسيط        → CoT
      بحث + أدوات        → ReAct
      هياكل بديلة        → ToT
      قرار معقد          → Claude Extended Thinking
    """

    def __init__(self, llm_client=None, budget_tokens: int = 8000):
        self.llm = llm_client
        self.budget_tokens = budget_tokens

    # ── CoT: تحليل المهمة ──

    def cot_prompt(self, task_description: str) -> str:
        """
        يبني prompt CoT لتحليل مهمة بحثية.
        يُستخدم في طبقة الفهم (٣).
        """
        return f"""حلّل الطلب التالي خطوة بخطوة:

الطلب: {task_description}

الخطوة ١: ما نوع المهمة؟ (بحث/تقرير/عرض/واجب/تحليل)
الخطوة ٢: ما الموضوع الرئيسي؟
الخطوة ٣: ما اللغة المطلوبة؟ (عربي/إنجليزي/كلاهما)
الخطوة ٤: ما أسلوب التوثيق المطلوب؟ (APA/MLA/Chicago/غير محدد)
الخطوة ٥: ما صيغة الإخراج؟ (Word/PPTX/Excel/PDF)
الخطوة ٦: كم الطول المطلوب؟
الخطوة ٧: ما المعلومات الناقصة؟

أخرج النتيجة كـ JSON:
{{
  "task_type": "...",
  "topic": "...",
  "language": "ar|en|both",
  "citation_style": "APA|MLA|Chicago|unspecified",
  "output_format": "DOCX|PPTX|XLSX|PDF",
  "length": "...",
  "missing_info": [...],
  "clarification_questions": [...]
}}"""

    # ── ReAct: حلقة بحث وصياغة ──

    def react_step(
        self,
        thought: str,
        available_tools: list[str],
        context: str = "",
    ) -> str:
        """
        يبني خطوة ReAct واحدة.
        يُستخدم في طبقة الصياغة (٦).
        """
        tools_str = "\n".join(f"  - {t}" for t in available_tools)
        return f"""السياق الحالي:
{context}

تفكيري: {thought}

الأدوات المتاحة:
{tools_str}

ما الإجراء التالي؟ (فكّر ثم اختر أداة أو اكتب الإجابة النهائية)
"""

    # ── ToT: استكشاف هياكل بحثية بديلة ──

    def tot_expand(self, topic: str, task_type: str, n_alternatives: int = 3) -> str:
        """
        يطلب من النموذج استكشاف هياكل بحثية متعددة.
        يُستخدم في طبقة الصياغة (٦) لاختيار أفضل هيكل.
        """
        return f"""اقترح {n_alternatives} هياكل مختلفة لـ {task_type} حول موضوع: {topic}

لكل هيكل:
١. العنوان الرئيسي
٢. الأقسام الرئيسية (٤-٦ أقسام)
٣. نقاط القوة في هذا الهيكل
٤. نقاط الضعف

ثم قيّم كل هيكل من ١-١٠ وأوصِ بالأفضل مع الأسباب.

أخرج JSON:
{{
  "structures": [
    {{
      "id": 1,
      "title": "...",
      "sections": [...],
      "strengths": [...],
      "weaknesses": [...],
      "score": 8
    }}
  ],
  "recommended": 1,
  "reason": "..."
}}"""

    # ── Claude Extended Thinking ──

    async def extended_think(
        self,
        prompt: str,
        system: str = None,
        budget: int = None,
    ) -> str:
        """
        يستخدم Claude Extended Thinking للقرارات المعقدة.
        يُستخدم في طبقة التحقق (٧) وعند الحاجة في الصياغة.
        """
        if self.llm is None:
            raise RuntimeError("Extended Thinking يحتاج llm_client (Anthropic API)")

        # استدعاء anthropic مع thinking
        try:
            import anthropic
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=16000,
                thinking={
                    "type": "enabled",
                    "budget_tokens": budget or self.budget_tokens,
                },
                system=system or "أنت نظام بحث أكاديمي متكامل. تفكّر بعمق قبل الإجابة.",
                messages=[{"role": "user", "content": prompt}],
            )

            # استخراج النتيجة
            thinking_text = ""
            answer_text = ""
            for block in response.content:
                if block.type == "thinking":
                    thinking_text = block.thinking
                elif block.type == "text":
                    answer_text = block.text

            return answer_text

        except ImportError:
            raise ImportError("pip install anthropic لاستخدام Extended Thinking")

    def select_mode(self, task_complexity: str) -> str:
        """يختار إطار التفكير المناسب."""
        modes = {
            "simple":  "cot",
            "medium":  "react",
            "complex": "tot",
            "critical": "extended",
        }
        return modes.get(task_complexity, "cot")
