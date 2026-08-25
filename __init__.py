"""
Weaver Write — النظام الرئيسي
================================
نظام بحث أكاديمي متكامل يُشغّل ٥ مهام متوازية.

البنية:
  weaver_write/
  ├── core/           ← الأنظمة الجوهرية (مدمجة ليست أدوات)
  │   ├── memory/     ← UniMemory
  │   ├── browser/    ← UniWeb
  │   ├── ocr/        ← UniDoc
  │   ├── sandbox/    ← OpenSandbox
  │   ├── connector/  ← open-connector
  │   ├── context/    ← context-mode
  │   └── thinking/   ← Extended Thinking
  ├── pipeline/       ← طبقات المعالجة
  │   ├── layers/     ← الطبقات ٠-٨
  │   ├── prompts/    ← كل الـ Prompts
  │   ├── skills/     ← المهارات الجاهزة
  │   └── protocols/  ← البروتوكولات
  ├── config/         ← الإعدادات
  └── tests/          ← الاختبارات
"""

from __future__ import annotations
import asyncio
import os
from typing import Optional

# الإصدار
__version__ = "1.0.0"
__name_ar__ = "Weaver Write"

# الحد الأقصى للمهام المتوازية
MAX_PARALLEL_TASKS = 5
