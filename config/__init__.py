"""
config/__init__.py
==================
إعدادات Weaver Write.
"""

import os

class Config:
    # ── النظام ──
    MAX_PARALLEL_TASKS = 5
    DB_PATH = os.environ.get("WEAVER_DB", "./weaver_memory.db")

    # ── OpenSandbox ──
    SANDBOX_DOMAIN = os.environ.get("SANDBOX_DOMAIN", "localhost:8080")
    SANDBOX_KEY = os.environ.get("SANDBOX_API_KEY", "")

    # ── open-connector ──
    CONNECTOR_URL = os.environ.get("CONNECTOR_URL", "http://localhost:3000")

    # ── context-mode ──
    CONTEXT_URL = os.environ.get("CONTEXT_URL", "http://localhost:8765")

    # ── LLM ──
    LLM_PROVIDER = os.environ.get("WEAVER_LLM", "anthropic")
    LLM_MODEL = os.environ.get("WEAVER_MODEL", "claude-sonnet-4-6")
    LLM_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

    # ── firecrawl ──
    FIRECRAWL_KEY = os.environ.get("FIRECRAWL_API_KEY", "")

    # ── Extended Thinking ──
    THINKING_BUDGET = int(os.environ.get("THINKING_BUDGET", "8000"))

    # ── الإخراج ──
    OUTPUT_DIR = os.environ.get("WEAVER_OUTPUT", "./output")
