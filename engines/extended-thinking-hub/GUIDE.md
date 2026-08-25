# دليل الاستخدام الموحّد — Extended Thinking Hub

## ١. Chain-of-Thought (cot/)

**الفكرة:** توجيه النموذج لكتابة خطوات تفكيره قبل الإجابة.

### الاستخدام
```python
# المصدر: cot/notebooks/ + cot/gsm8k/
# لا يحتاج كود — prompt فقط

prompt = """
حل هذه المسألة خطوة بخطوة:
إذا كان لدى محمد 15 تفاحة وأعطى 1/3 منها لسارة، كم تفاحة تبقّت معه؟

دعني أفكر خطوة بخطوة:
"""
# النموذج يُكمّل التفكير تلقائياً
```

---

## ٢. ReAct — Reasoning + Acting (react/)

**الفكرة:** دمج التفكير مع التصرف في حلقة متكررة.

### الملفات الأساسية
```
react/
├── wikienv.py      ← بيئة Wikipedia (Search, Lookup, Finish)
├── wrappers.py     ← HotPotQA, FEVER, Logging wrappers
├── hotpotqa.ipynb  ← مثال بحث متعدد الخطوات
├── fever.ipynb     ← مثال التحقق من الحقائق
└── prompts/        ← few-shot prompts جاهزة
```

### دورة ReAct
```
Thought: أحتاج للبحث عن معلومة X
Action: search[X]
Observation: نتيجة البحث...
Thought: بناءً على النتيجة، أحتاج...
Action: lookup[keyword]
Observation: ...
Action: finish[الإجابة النهائية]
```

### الاستخدام مع أي API
```python
# مقتبس من react/hotpotqa.ipynb مع تعديل للنموذج
import anthropic

client = anthropic.Anthropic()

def react_step(history: str, tools: dict) -> str:
    """خطوة ReAct واحدة"""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": history}]
    )
    return response.content[0].text

def react_loop(question: str, env, max_steps: int = 7):
    """حلقة ReAct كاملة"""
    obs = env.reset()
    history = f"Question: {question}\n{obs}\n"

    for step in range(1, max_steps + 1):
        # Thought + Action
        action = react_step(history, env)
        history += f"Action {step}: {action}\n"

        # Observation
        obs, reward, done, info = env.step(action)
        history += f"Observation {step}: {obs}\n\n"

        if done:
            return info['answer'], reward, history

    return None, 0, history
```

---

## ٣. Tree of Thoughts — Princeton (tot-princeton/)

**الإطار الرسمي من NeurIPS 2023.**

### الملفات الأساسية
```
tot-princeton/src/tot/
├── models.py           ← gpt() wrapper
├── methods/bfs.py      ← BFS + DFS algorithms
├── tasks/game24.py     ← مهمة Game of 24
├── tasks/crosswords.py ← Mini Crosswords
├── tasks/text.py       ← Creative Writing
└── prompts/            ← prompts لكل مهمة
```

### الاستخدام
```python
# من tot-princeton/src/tot/methods/bfs.py
# الكود الأصلي محفوظ كما هو

import sys
sys.path.insert(0, 'tot-princeton/src')
from tot.methods.bfs import solve
from tot.tasks.game24 import Game24Task

# إعداد المهمة
task = Game24Task()

# إعداد المعاملات
class Args:
    backend = 'gpt-4'          # أو أي نموذج
    temperature = 0.7
    task = 'game24'
    naive_run = False
    prompt_sample = 'standard'
    method_generate = 'propose'
    method_evaluate = 'value'
    method_select = 'greedy'
    n_generate_sample = 1
    n_evaluate_sample = 3
    n_select_sample = 5

args = Args()

# تشغيل BFS
ys, info = solve(args, task, idx=0)
print("الحلول:", ys)
```

---

## ٤. Tree of Thoughts — Kyegomez (tot-kyegomez/)

**تطبيق عملي أبسط مع BFS متوازي.**

### الملفات الأساسية
```
tot-kyegomez/tree_of_thoughts/
├── agent.py  ← TotAgent class + system prompt
├── bfs.py    ← BFSWithTotAgent (متوازي)
└── dfs.py    ← DFSWithTotAgent
```

### الاستخدام
```python
# من tot-kyegomez/tree_of_thoughts/
import sys
sys.path.insert(0, 'tot-kyegomez')
from tree_of_thoughts.agent import TotAgent
from tree_of_thoughts.bfs import BFSWithTotAgent

# إنشاء agent
agent = TotAgent(max_loops=1)

# إنشاء BFS
bfs = BFSWithTotAgent(
    agent=agent,
    max_loops=3,        # عمق الشجرة
    breadth_limit=3,    # عرض كل مستوى
    number_of_agents=3  # أفكار متوازية
)

# تشغيل
result = bfs.run("كيف أحسّن أداء WeaverCode؟")
print(result)
```

---

## ٥. Claude Extended Thinking (claude-extended/)

**الأقوى والأبسط للاستخدام الفوري.**

### الملفات
```
claude-extended/
├── extended_thinking.ipynb           ← أمثلة أساسية
└── extended_thinking_with_tool_use.ipynb ← مع الأدوات
```

### الاستخدام الحديث (2026)
```python
import anthropic

client = anthropic.Anthropic()

# ── Adaptive Thinking (الموصى به لـ Claude 4.7+) ──
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=16000,
    thinking={
        "type": "enabled",
        "budget_tokens": 10000  # للنماذج 4.6 وما قبل
    },
    messages=[{
        "role": "user",
        "content": "حل هذه المشكلة المعقدة: ..."
    }]
)

# استخراج التفكير والإجابة
for block in response.content:
    if block.type == "thinking":
        print("التفكير:", block.thinking[:200], "...")
    elif block.type == "text":
        print("الإجابة:", block.text)

# ── مع الأدوات (Interleaved Thinking) ──
response2 = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=16000,
    thinking={"type": "enabled", "budget_tokens": 8000},
    tools=[{
        "name": "search",
        "description": "بحث في الويب",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    }],
    messages=[{
        "role": "user",
        "content": "ابحث عن أحدث أخبار الذكاء الاصطناعي"
    }]
)
```

---

## مقارنة عملية للاختيار

```python
def choose_framework(task_type: str) -> str:
    """
    اختيار الإطار المناسب بناءً على نوع المهمة
    """
    if task_type == "simple_reasoning":
        # CoT — prompt فقط
        return "استخدم: cot/ — أضف 'فكّر خطوة بخطوة' للـ prompt"

    elif task_type == "needs_external_tools":
        # ReAct — يحتاج أدوات خارجية
        return "استخدم: react/ — Thought→Action→Observation loop"

    elif task_type == "complex_planning":
        # ToT — استكشاف بدائل
        return "استخدم: tot-princeton/ للبحث BFS/DFS"

    elif task_type == "production_agent":
        # Claude Extended Thinking — الأسهل والأقوى
        return "استخدم: claude-extended/ — API مباشر"

    return "ابدأ بـ CoT، ثم ReAct إذا احتجت أدوات"
```

---

## متطلبات التثبيت

```bash
# ReAct
pip install openai gym requests beautifulsoup4

# ToT Princeton
cd tot-princeton && pip install -e .

# ToT Kyegomez
cd tot-kyegomez && pip install -r requirements.txt

# Claude Extended Thinking
pip install anthropic
```
