# UniMemory — محرك الذاكرة الموحّد

يجمع **أفضل ميزات** أربع أدوات ذاكرة في محرك واحد متماسك — يعمل على Termux والخادم.

## من أين جاءت كل ميزة

| الميزة | المصدر | الوصف |
|---|---|---|
| **5 أنواع ذاكرة + تلاشي** | OpenMemory | episodic/semantic/procedural/reflective/emotional مع decay |
| **Graph معرفي** | Cognee | علاقات بين الذكريات عبر الكيانات المشتركة |
| **Truth-checking** | Cognee | كشف التناقضات والتكرار |
| **معالجة إدخال آمنة** | Zep | تحصين ضد حقن التعليمات في النصوص |
| **كشف الوكلاء** | mem0 | يعرف Claude Code / Cursor / Codex تلقائياً |
| **LLM مزدوج** | الكل | Ollama محلي + سحابي (Claude/OpenAI/DeepSeek) |

## المميزات الأساسية

### 5 أنواع ذاكرة مع تلاشي طبيعي
```
episodic   → أحداث ("طلب المستخدم X")     — يتلاشى سريعاً
semantic   → معرفة ("WeaverCode بـ Python") — يدوم طويلاً
procedural → طرق ("كيفية إعداد Aerolink")
reflective → استنتاجات ("المستخدم خبير")
emotional  → تفضيلات ("يصحّح بحزم")
```
كل ذكرى لها **salience** (أهمية) تتناقص مع الوقت ما لم تُستدعَ.

### Graph معرفي
الذكريات المشتركة في كيانات ترتبط تلقائياً. البحث يوسّع عبر المسارات.

### Truth-checking
قبل الإضافة، يفحص التناقض/التكرار مع الموجود — يقوّي بدل التكرار، ويتجاوز المتناقض.

## التثبيت

```bash
# يعمل فوراً بلا أي تبعية (SQLite + fallback embedding)
pip install -e .

# مع LLM سحابي (اختياري)
pip install -e .[anthropic]   # Claude
pip install -e .[openai]      # GPT
pip install -e .[llm]         # الكل
```

**بلا أي تثبيت إضافي:** يعمل بـ SQLite المدمج و embedding بسيط offline.
**مع Ollama:** embedding وextraction دلالي حقيقي محلياً.
**مع API:** أعلى دقة.

## الاستخدام

### Python
```python
from unimemory import UniMemory

mem = UniMemory("./memory.db")

# إضافة (يكتشف النوع، يستخرج الكيانات، يفحص التناقض)
mem.add("المستخدم يفضل Python على JavaScript", node="observe")
mem.add("WeaverCode مبني بـ Python", node="plan")

# بحث هجين (دلالي + graph + إعادة ترتيب بالأهمية)
results = mem.search("ما اللغة المفضلة؟", limit=5)
for r in results:
    print(r.sector.value, r.current_salience(), r.content)

# صيانة (نسيان المتلاشي طبيعياً)
mem.consolidate(threshold=0.1)

# إضافة دفعية (وثيقة/محادثة → ذكريات ذرّية)
mem.add_bulk("نص طويل. عدة حقائق. تُقسّم تلقائياً.")

# ضغط الذكريات المتلاشية (بدل حذفها)
mem.compress_faded(threshold=0.3)

# استخلاص دروس من محادثة
lessons = mem.distill_session([
    {"role": "user", "content": "أفضّل دائماً الحلول الكاملة"},
])

# تصدير/استيراد
mem.export_json("backup.json")
mem.import_json("backup.json")

# إحصاءات
print(mem.stats())
```

### MCP Server (تكامل مع Claude)
```bash
# التشغيل
python -m unimemory.mcp

# في إعداد Claude:
{
  "mcpServers": {
    "unimemory": {
      "command": "python",
      "args": ["-m", "unimemory.mcp"],
      "env": { "UNIMEM_DB": "/path/to/memory.db" }
    }
  }
}
```
الأدوات المتاحة للوكيل: `unimemory_add`, `unimemory_search`, `unimemory_stats`, `unimemory_distill`, `unimemory_consolidate`.

### سطر الأوامر
```bash
python -m unimemory add "المستخدم يفضل Python" --node observe
python -m unimemory search "اللغة المفضلة" --limit 5
python -m unimemory stats
python -m unimemory consolidate
python -m unimemory list --sector semantic
```

## متغيرات البيئة

```bash
UNIMEM_OLLAMA_URL=http://localhost:11434   # Ollama محلي
ANTHROPIC_API_KEY=sk-ant-...               # Claude
OPENAI_API_KEY=sk-...                       # GPT
DEEPSEEK_API_KEY=sk-...                      # DeepSeek
```

## البنية

```
unimemory-core/
├── unimemory/                  ← المحرك الموحّد (جديد)
│   ├── __init__.py
│   ├── engine.py               ← UniMemory — المحرك الرئيسي
│   ├── memory_types.py         ← 5 أنواع + تلاشي (OpenMemory)
│   ├── graph_store.py          ← Graph معرفي (Cognee)
│   ├── truth_checker.py        ← كشف التناقضات (Cognee)
│   ├── extract.py              ← استخراج آمن (Zep)
│   ├── compress.py             ← ضغط الذكريات (OpenMemory)
│   ├── distill.py              ← استخلاص الدروس (Cognee)
│   ├── mcp.py                  ← MCP Server (OpenMemory)
│   ├── llm.py                  ← LLM مزدوج
│   └── cli.py
├── reference_zep/              ← الأصلي (مرجع، بلا تعديل)
├── reference_cognee/           ← الأصلي (مرجع، بلا تعديل)
├── reference_mem0/             ← الأصلي (مرجع، بلا تعديل)
└── reference_openmemory/       ← الأصلي (مرجع، بلا تعديل)
```

**مبدأ التصميم:** المحرك الجديد يستلهم المفاهيم من الأدوات الأربعة ويعيد بناءها
على محرك SQLite واحد متماسك — بدلاً من دمج معماريات متضاربة.
المصادر الأصلية محفوظة كمرجع.

## لماذا محرك جديد بدل دمج الأكواد

الأدوات الأربعة لها معماريات متضاربة:
- Zep يحتاج cloud
- Cognee يستخدم KuzuDB
- mem0 يحتاج SaaS
- OpenMemory بـ TypeScript

الدمج المباشر مستحيل. الحل: **محرك واحد** يأخذ أفضل مفهوم من كل أداة
ويبنيه على SQLite — خفيف لـ Termux، قوي للخادم، يعمل offline أو بـ API.
