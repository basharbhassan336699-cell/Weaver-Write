"""
UniMemory — محرك الذاكرة الموحّد لـ WeaverCode.

يجمع أفضل ميزات Zep + Cognee + mem0 + OpenMemory في محرك واحد:
  • 5 أنواع ذاكرة مع تلاشي طبيعي (OpenMemory)
  • Graph معرفي عبر الكيانات (Cognee)
  • كشف التناقضات (Cognee truth_subspace)
  • معالجة إدخال آمنة (Zep contextualizer)
  • كشف الوكلاء التلقائي (mem0)
  • LLM مزدوج: Ollama محلي + سحابي

الاستخدام:
    from unimemory import UniMemory

    mem = UniMemory("./memory.db")
    mem.add("المستخدم يفضل Python", node="observe")
    results = mem.search("ما اللغة المفضلة؟")
    mem.consolidate()  # نسيان المتلاشي
"""

from .engine import UniMemory, detect_agent_caller
from .memory_types import Memory, Sector, classify_sector
from .graph_store import GraphStore, Edge
from .truth_checker import TruthChecker, Verdict, TruthCheck
from .llm import LLMClient
from .compress import Compressor
from .distill import SessionDistiller, Lesson

__version__ = "1.0.0"

__all__ = [
    "UniMemory",
    "Memory",
    "Sector",
    "GraphStore",
    "Edge",
    "TruthChecker",
    "Verdict",
    "TruthCheck",
    "LLMClient",
    "Compressor",
    "SessionDistiller",
    "Lesson",
    "classify_sector",
    "detect_agent_caller",
]
