"""
محوّل LLM المزدوج — Ollama محلي + API سحابي.

مستوحى من:
  - Cognee (ollama_support)
  - Zep (llm/anthropic, llm/openai)
  - OpenMemory (multi-provider adapter)

يعمل أينما وُجد: يجرّب المحلي أولاً، ثم السحابي.
يُستخدم للاستخراج (extraction) والتضمين (embedding) وفحص التناقض.
"""

from __future__ import annotations
import os
import json
from typing import Optional


class LLMClient:
    """
    محوّل موحّد لأي مزود LLM.
    يكتشف المتاح تلقائياً: Ollama → Anthropic → OpenAI → DeepSeek.
    """

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider, self.model = self._resolve(provider, model)

    def _resolve(self, provider, model):
        """يحدد المزود المتاح."""
        # تفضيل صريح
        if provider:
            return provider, model or self._default_model(provider)

        # كشف تلقائي حسب التوفر
        if os.environ.get("UNIMEM_OLLAMA_URL") or self._ollama_alive():
            return "ollama", model or "llama3.2"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic", model or "claude-sonnet-4-6"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai", model or "gpt-4o-mini"
        if os.environ.get("DEEPSEEK_API_KEY"):
            return "deepseek", model or "deepseek-chat"
        # افتراضي: ollama (قد يفشل لاحقاً برسالة واضحة)
        return "ollama", model or "llama3.2"

    def _default_model(self, provider):
        return {
            "ollama": "llama3.2",
            "anthropic": "claude-sonnet-4-6",
            "openai": "gpt-4o-mini",
            "deepseek": "deepseek-chat",
        }.get(provider, "llama3.2")

    def _ollama_alive(self) -> bool:
        """فحص إن كان Ollama يعمل محلياً."""
        try:
            import urllib.request
            url = os.environ.get("UNIMEM_OLLAMA_URL", "http://localhost:11434")
            urllib.request.urlopen(f"{url}/api/tags", timeout=1)
            return True
        except Exception:
            return False

    def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        """استكمال نصي — يوجّه للمزود المناسب."""
        if self.provider == "ollama":
            return self._ollama_complete(prompt, max_tokens)
        if self.provider == "anthropic":
            return self._anthropic_complete(prompt, max_tokens)
        if self.provider in ("openai", "deepseek"):
            return self._openai_complete(prompt, max_tokens)
        raise RuntimeError(f"مزود غير مدعوم: {self.provider}")

    def embed(self, text: str) -> list[float]:
        """تضمين نصي (embedding) للبحث الدلالي."""
        if self.provider == "ollama":
            return self._ollama_embed(text)
        if self.provider == "openai":
            return self._openai_embed(text)
        # fallback: تضمين نصي بسيط (hashing) إن لا embedding API
        return self._simple_embed(text)

    # ── Ollama ──
    def _ollama_complete(self, prompt, max_tokens):
        import urllib.request
        url = os.environ.get("UNIMEM_OLLAMA_URL", "http://localhost:11434")
        data = json.dumps({
            "model": self.model, "prompt": prompt, "stream": False,
            "options": {"num_predict": max_tokens}
        }).encode()
        req = urllib.request.Request(f"{url}/api/generate", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())["response"]

    def _ollama_embed(self, text):
        import urllib.request
        url = os.environ.get("UNIMEM_OLLAMA_URL", "http://localhost:11434")
        data = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode()
        req = urllib.request.Request(f"{url}/api/embeddings", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())["embedding"]

    # ── Anthropic ──
    def _anthropic_complete(self, prompt, max_tokens):
        try:
            import anthropic
        except ImportError:
            raise ImportError("pip install anthropic")
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=self.model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text

    # ── OpenAI / DeepSeek ──
    def _openai_complete(self, prompt, max_tokens):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("pip install openai")
        base_url = None
        if self.provider == "deepseek":
            base_url = "https://api.deepseek.com"
        client = OpenAI(base_url=base_url)
        resp = client.chat.completions.create(
            model=self.model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content

    def _openai_embed(self, text):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("pip install openai")
        client = OpenAI()
        resp = client.embeddings.create(model="text-embedding-3-small", input=text)
        return resp.data[0].embedding

    # ── Fallback embedding (بلا API) ──
    def _simple_embed(self, text: str, dim: int = 256) -> list[float]:
        """
        تضمين بسيط بالـ hashing — للعمل بلا embedding API.
        ليس دقيقاً كـ neural embeddings لكنه يعمل offline بالكامل.
        """
        import hashlib
        vec = [0.0] * dim
        for token in text.lower().split():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % dim] += 1.0
        # تطبيع
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]
