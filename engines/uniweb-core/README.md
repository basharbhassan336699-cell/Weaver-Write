# UniWeb — أداة الويب الموحّدة

تجمع **خمس أدوات** في واجهة واحدة مع توجيه ذكي تلقائي — دون تعديل منطق أي أداة.

## المحركات الخمسة

| المحرك | الفئة | التخصص | المتطلبات |
|---|---|---|---|
| **curl_impersonate** | عميل HTTP | جلب مع انتحال بصمة TLS (يتجاوز مكافحة البوتات) | curl_cffi |
| **autoscraper** | scraper متعلّم | استخلاص بقواعد متعلَّمة من أمثلة | CPU (offline) |
| **firecrawl** | SDK سحابي | scraping ذكي → Markdown نظيف، crawl، map | API key |
| **browser_use** | متصفح آلي | مهام تفاعلية بالـ AI: نقر، نماذج، تنقّل | Chromium + LLM |
| **agent_reach** | موصّل منصات | 17 منصة: تويتر، لينكدإن، يوتيوب، reddit… | cookies/APIs |

## التوجيه التلقائي

```
مهمة تفاعلية (نقر/نماذج)         → browser_use   (يفوز على كل شيء)
رابط منصة معروفة (تويتر…)         → agent_reach
استخلاص بقواعد متعلَّمة            → autoscraper
Markdown نظيف / زحف متعدد         → firecrawl
جلب HTML + حماية مكافحة البوتات   → curl_impersonate
جلب HTML بسيط                     → curl_impersonate (افتراضي)
```

## التثبيت

```bash
pip install -e .                  # الأساس (توجيه)
pip install -e .[curl]            # curl_impersonate
pip install -e .[scrape]          # autoscraper
pip install -e .[firecrawl]       # firecrawl
pip install -e .[browser]         # browser_use + playwright
pip install -e .[all]             # الأدوات الخفيفة
```

## الاستخدام

### Python

```python
import uniweb

# جلب بسيط — curl_impersonate تلقائياً
html = uniweb.fetch("https://example.com")

# Markdown نظيف — firecrawl
md = uniweb.fetch("https://blog.com", clean=True)

# استخلاص بيانات — autoscraper يتعلّم من أمثلة
prices = uniweb.scrape("https://shop.com", wanted=["$29.99"])

# تطبيق قواعد محفوظة
data = uniweb.scrape("https://shop.com/page2", rules_file="rules.json")

# منصة معروفة — agent_reach تلقائياً
post = uniweb.fetch("https://twitter.com/user/status/123")

# مهمة تفاعلية — browser_use (يحتاج LLM)
from anthropic import ... # أو أي LLM
coro = uniweb.interact("https://app.com", "سجّل الدخول واستخرج لوحة التحكم", llm=my_llm)
import asyncio
result = asyncio.run(coro)

# تفاصيل كاملة
r = uniweb.fetch_detailed("https://site.com")
print(r["engine"], r["reason"], r["meta"])
```

### سطر الأوامر

```bash
python -m uniweb fetch https://example.com
python -m uniweb fetch https://blog.com --clean
python -m uniweb detect
python -m uniweb route https://twitter.com/x/status/1
```

## متغيرات البيئة

```bash
UNIWEB_CURL_PATH=<path>       # مسار curl-impersonate المبني
FIRECRAWL_API_KEY=<key>       # مفتاح firecrawl
ANTHROPIC_API_KEY=<key>       # LLM للـ browser_use
OPENAI_API_KEY=<key>          # بديل
UNIWEB_LLM_BASE=<url>         # نموذج محلي
```

## البنية

```
uniweb-core/
├── uniweb/                          ← طبقة التوحيد (جديدة)
│   ├── __init__.py                  ← fetch/scrape/crawl/interact
│   ├── router.py                    ← منطق اختيار المحرك
│   ├── capabilities.py              ← كشف الموارد
│   ├── engines.py                   ← أغلفة تستدعي الأدوات الأصلية
│   └── cli.py                       ← واجهة سطر الأوامر
├── engines_src_curl_impersonate/    ← الأصلي (بلا تعديل)
├── engines_src_autoscraper/         ← الأصلي (بلا تعديل)
├── engines_src_firecrawl/           ← الأصلي (بلا تعديل)
├── engines_src_browser_use/         ← الأصلي (بلا تعديل)
└── engines_src_agent_reach/         ← الأصلي (بلا تعديل)
```

**مبدأ التصميم:** طبقة `uniweb/` لا تعدّل منطق أي أداة — تستدعيها كما هي فقط.

## لـ WeaverCode

```python
import uniweb

# جلب صفحة محمية (curl_impersonate يتجاوز Cloudflare)
html = uniweb.fetch("https://protected-site.com")

# استخلاص أسعار متكرر (autoscraper offline)
prices = uniweb.scrape("https://exchange.com", rules_file="price_rules.json")

# قراءة منشور تويتر (agent_reach)
tweet = uniweb.fetch("https://twitter.com/trader/status/123")
```
