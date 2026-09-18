# -*- coding: utf-8 -*-
"""الجسرُ إلى محرّك Weaver Write (openclaw مُعادَ التسمية، رخصة MIT).

نظامُك بايثون، والمحرّكُ Node. فهذا الملفُّ هو الحدُّ بينهما: يجد المحرّك،
ويُشغّله، ويُعيد ما قال. ولا يُترجم منطقه ولا يُعيد كتابته — المنطقُ يبقى
حيث هو، كما هو، فلا يتخلّف عن إصداراته ولا يُخطئ في نقلٍ.

    from pipeline.weaver_core import available, ask, version
    if available():
        print(ask("أيُّ سؤال"))

وعلى الطرفية:
    python3 -m pipeline.weaver_core --version
    python3 -m pipeline.weaver_core "أيُّ سؤال"

وغيابُ المحرّك ليس عطباً: `available()` تُعيد False، ويبقى المسارُ
البايثونيُّ (`pipeline.agent`) يعمل كما كان.
"""

import os
import signal
import subprocess
import time
import threading
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME = os.path.join(_ROOT, "engines", "weaver-core", "runtime")
ENTRY = os.path.join(RUNTIME, "openclaw.mjs")
INSTALLER = os.path.join(_ROOT, "engines", "weaver-core", "install.sh")


# ── الغلاف: حالةُ المحرّك تسكن باسم نظامنا، بلا تعديل ملفٍّ واحدٍ فيه ──
#
# فُحصت مسارات `.openclaw` في الحزمة بكيفيّة بنائها لا بعددها:
#
#   ٢٦٩ موضعاً  تمرّ بـ`resolveStateDir(env)` في dist/legacy-fR_P797G.mjs:
#                   const override = env.OPENCLAW_STATE_DIR?.trim();
#                   if (override) return resolveUserPath(override, env);
#               فمفتاحٌ واحدٌ يُحرّكها كلَّها — وهو مُتجاوِزٌ رسميٌّ يعرضه
#               المحرّكُ نفسُه، لا ثغرةٌ نستغلّها.
#
#     ٦ مواضعَ  تتجاوزها، وفُحصت واحداً واحداً:
#                 · doctor-platform-notes:20     darwin فقط  ⟶ لا أثر هنا
#                 · terminal-file-upload:31      win32  فقط  ⟶ لا أثر هنا
#                 · doctor-state-integrity:1346  للمقارنة والعرض لا للكتابة
#                 · audit:11 · install:365 · claws-cli-output:254
#                   ⟶ `os.homedir()`، و`os.homedir()` تتبع HOME.
#
# فمفتاحان يغطّيان كلَّ مسارات الكتابة: OPENCLAW_STATE_DIR للمُعلَن، وHOME
# للثلاثة الباقية. وهذا خيرٌ من إعادة تسمية ٢٤٢٢٨ اسماً: صفرُ خطرٍ لأنّ
# المحرّكَ لا يُمَسّ، ويعيش مع كلّ ترقيةٍ بلا إعادة ترقيع.
#
# ويقبل الغلافُ مفاتيحَ `WEAVER_*` ويترجمها إلى `OPENCLAW_*` قبل التشغيل:
# أنت تكتب اسمَ نظامك، والمحرّكُ يقرأ اسمَه.
STATE = os.path.join(os.path.expanduser("~"), ".weaver-write")
_ENGINE_HOME = os.path.join(STATE, "engine")
_STATE_DIR = os.path.join(STATE, "state")


# اسمُ نسختنا. المحرّكُ يستعمله لعزل الخدمة والسجلّات والمنفذ عن أيّ نسخةٍ
# أخرى على الجهاز — وهذه آليّتُه هو، لا حيلةٌ من عندنا:
#   constants-CJCmIHb-.mjs:56   normalizeGatewayProfile(env.OPENCLAW_PROFILE)
#   constants-CJCmIHb-.mjs:45   resolveGatewaySystemdServiceName(profile)
#   logger-Bf_6W09A.mjs:85      profileSuffix في اسم ملفّ السجلّ
PROFILE = "weaver"
DEFAULT_PORT = 18789        # منفذُ المحرّك الافتراضيّ (DEFAULT_GATEWAY_PORT)
OUR_PORT = 18889            # ومنفذُنا، بعيداً عنه وعن منفذ --dev (19001)


# ── مفتاحٌ واحدٌ في نظامك، يكفي المحرّكَ أيضاً ────────────────────────────
#
# السببُ الذي كشفه السجلّ:
#     "model": null, "provider": null
#     "No route-compatible authentication source is configured for openai."
#     requested=openai/gpt-5.6-sol  reason=auth  next=none
# أي أنّ المحرّكَ سقط إلى نموذجه الافتراضيّ لأنّه لا يعرف مزوّدك.
#
# ونظامُك يحمل الإعدادَ أصلاً في `WEAVER_PROVIDER/BASE_URL/API_KEY/MODEL`
# (core/llm/__init__.py:403-408). والمحرّكُ يقرأ متغيّراً لكلّ مزوّد:
#     config-provider-contract-BdOif1pq.mjs:89   openrouter: "OPENROUTER_API_KEY"
# فالوصلُ أن يُترجَم ما عندك إلى ما يفهمه — فلا تضبط مفتاحك مرّتين.
#
# ولا يُخمَّن المزوّد: يُقرأ من `WEAVER_PROVIDER` إن صُرّح به، وإلّا فمن
# اسم المضيف في `WEAVER_BASE_URL` — وهو دليلٌ لا حدس.
_PROVIDER_ENV = {
    "openrouter": "OPENROUTER_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY", "mistral": "MISTRAL_API_KEY",
    "google": "GOOGLE_API_KEY", "xai": "XAI_API_KEY",
    "cerebras": "CEREBRAS_API_KEY", "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY", "kimi": "KIMI_API_KEY",
    "minimax": "MINIMAX_API_KEY", "zai": "ZAI_API_KEY",
}


def _load_settings():
    """إعداداتُك كما يقرؤها نظامُك — من `config/.env` ثمّ البيئة.

    `--provider` قال «لا مفتاح» بينما نظامُك يعمل، والسببُ أنّ الجسرَ كان
    يقرأ البيئةَ وحدها. ومفاتيحُك ليست فيها: هي في

        config/.env        (config/keysync.py:27  _ENV_FILE)

    وهو **مصدرُ الحقيقة الذي تتشارك فيه الطرفيةُ وواجهةُ الويب**
    (keysync.py:30  SYNC_KEYS). فيُقرأ منه أوّلاً، والبيئةُ تعلو عليه —
    وهو ترتيبُ `load_env` نفسُه (setdefault: ما في البيئة يبقى).

    لا يرفع استثناءً؛ وغيابُ الملفّ يعني الاعتمادَ على البيئة كما كان."""
    out = {}
    try:
        f = os.path.join(_ROOT, "config", ".env")
        if os.path.isfile(f):
            for raw in open(f, encoding="utf-8",
                            errors="replace").read().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                if k:
                    out[k] = v
    except Exception:
        pass
    for k in ("WEAVER_API_KEY", "WEAVER_BASE_URL", "WEAVER_MODEL",
              "WEAVER_PROVIDER"):
        v = (os.environ.get(k) or "").strip()
        if v:
            out[k] = v                       # البيئةُ تعلو، كـload_env
    return out


def _setting(name):
    try:
        return (_load_settings().get(name) or "").strip()
    except Exception:
        return ""


def provider_id():
    """مزوّدُك كما يسمّيه المحرّك، أو "". لا يرفع استثناءً."""
    try:
        p = _setting("WEAVER_PROVIDER").lower()
        if p in _PROVIDER_ENV:
            return p
        host = _setting("WEAVER_BASE_URL").lower()
        for name in _PROVIDER_ENV:
            if name in host:
                return name
        if "anthropic.com" in host:
            return "anthropic"
        return ""
    except Exception:
        return ""


def model_id():
    """النموذجُ بصيغة `<مزوّد>/<نموذج>` كما يطلبها المحرّك، أو ""."""
    try:
        m = _setting("WEAVER_MODEL")
        if not m:
            return ""
        prov = provider_id()
        if not prov:
            return ""
        return m if m.startswith(prov + "/") else f"{prov}/{m}"
    except Exception:
        return ""


def credentials():
    """{اسمُ المتغيّر: المفتاح} كما يفهمها المحرّك — أو {}."""
    try:
        key = _setting("WEAVER_API_KEY")
        prov = provider_id()
        if not key or not prov:
            return {}
        return {_PROVIDER_ENV[prov]: key}
    except Exception:
        return {}


def engine_env(extra=None):
    """بيئةُ تشغيل المحرّك — معزولةٌ تماماً عن أيّ نسخةٍ أخرى على الجهاز.

    ثلاثُ عزلات، وكلُّها بآليّات المحرّك نفسِه لا بحيلٍ من عندنا:

    ١) **تنظيفُ ما وُرِث.** وهذا كان عطباً حقيقياً في أوّل كتابتي: كنتُ أنسخ
       البيئةَ كما هي ثمّ أضبط مفتاحين. فلو كان في `.bashrc` عند المستخدم
       `OPENCLAW_CONFIG_PATH` أو `OPENCLAW_HOME` أو `OPENCLAW_AGENT_DIR`
       لتركيبه القديم — وهذا شائعٌ عند من يستعمل أوبن كلاو أصلاً — لتسرّبت
       إلى محرّكنا فأعادته إلى حالته القديمة، فيكتب الاثنان في مكانٍ واحدٍ
       ويتلفان إعداداتِ بعضهما. فكلُّ `OPENCLAW_*` موروثٍ يُحذف أوّلاً، ولا
       يبقى إلا ما نضعه نحن.

    ٢) **بروفايلٌ باسمنا.** `OPENCLAW_PROFILE=weaver` يجعل المحرّكَ يعزل
       اسمَ خدمته وسجلّاته ومنفذه عن النسخة الافتراضية.

    ٣) **مسارٌ ومنفذٌ خاصّان.** الحالةُ في بيتنا، والمنفذُ 18889 بعيداً عن
       18789 (الافتراضيّ) و19001 (وضع --dev).

    والقاعدةُ واحدةٌ بلا استثناء: **كلُّ `WEAVER_X` يصير `OPENCLAW_X`**،
    ويعلو على افتراضاتنا. فلتغيير المنفذ: `WEAVER_GATEWAY_PORT`، ولتغيير
    المسار: `WEAVER_STATE_DIR` — بأسماء المحرّك نفسِها لا بأسماءٍ مخترَعة،
    كي لا يكون للشيء الواحد اسمان.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("OPENCLAW_")}      # ① لا شيءَ موروثٌ يمرّ
    # كلُّ WEAVER_X يصير OPENCLAW_X — ما عدا مفاتيحَ نظامنا البايثونيّ
    # (WEAVER_LLM، WEAVER_EXEC، WEAVER_AGENT_*) فهي ليست للمحرّك.
    _ours = ("WEAVER_LLM", "WEAVER_EXEC", "WEAVER_AGENT", "WEAVER_SCHOLAR",
             "WEAVER_SEARCH", "WEAVER_LANG", "WEAVER_MIN", "WEAVER_WORDS",
             "WEAVER_CONDENSE", "WEAVER_DECISIONS", "WEAVER_STRUCT",
             "WEAVER_FETCH", "WEAVER_MULTI", "WEAVER_OUT", "WEAVER_PAYLOAD")
    for k in list(env):
        if k.startswith("WEAVER_") and not k.startswith(_ours):
            env.setdefault("OPENCLAW_" + k[len("WEAVER_"):], env[k])
    # ثمّ افتراضاتُنا — بـsetdefault بعد الترجمة، فما صرّحتَ به يبقى فوقها.
    # (الترتيبُ مقصود: لو وُضعت الافتراضاتُ قبل الترجمة لَما نفع WEAVER_
    #  شيئاً، وهو عطبٌ وقعتُ فيه ثمّ كشفه الاختبار.)
    env.setdefault("OPENCLAW_PROFILE", PROFILE)                        # ②
    env.setdefault("OPENCLAW_STATE_DIR", _STATE_DIR)                   # ③
    env.setdefault("OPENCLAW_GATEWAY_PORT", str(OUR_PORT))
    env["HOME"] = _ENGINE_HOME
    for _k, _v in credentials().items():      # مفتاحُك، باسمٍ يفهمه المحرّك
        env.setdefault(_k, _v)
    for k, v in (extra or {}).items():
        env[str(k)] = str(v)
    try:
        os.makedirs(_ENGINE_HOME, exist_ok=True)
        os.makedirs(_STATE_DIR, exist_ok=True)
    except Exception:
        pass
    return env


def state_paths():
    """أين تسكن حالةُ المحرّك — للعرض وللحذف النظيف."""
    return {"state": _STATE_DIR, "home": _ENGINE_HOME, "root": STATE}


def isolation():
    """ما يعزلنا عن أيّ نسخةٍ أخرى — للعرض وللفحص."""
    e = engine_env()
    return {"profile": e.get("OPENCLAW_PROFILE", ""),
            "state": e.get("OPENCLAW_STATE_DIR", ""),
            "home": e.get("HOME", ""),
            "port": e.get("OPENCLAW_GATEWAY_PORT", ""),
            "inherited_openclaw_vars": sorted(
                k for k in os.environ if k.startswith("OPENCLAW_"))}


def available():
    """أمُركَّبٌ المحرّك؟ لا يرفع استثناءً أبداً."""
    try:
        return os.path.isfile(ENTRY)
    except Exception:
        return False


# ── أيُّ إصدارِ node؟ ثلاثُ درجاتٍ لا بوّابةٌ واحدة ────────────────────
#
# المحرّكُ يشترط ">=24.16.0 <25 || >=26.1.0"، وهو شرطٌ حقيقيٌّ لا شكليّ:
# يستعمل قاعدةَ بيانات node المدمجة، و22 يقصُّ النصَّ عند أوّل بايتٍ صفريّ
# (nodejs/node#61954) فتفسد البيانات **صامتةً**. فتجاوزُه بصمتٍ ليس حلّاً،
# وإغلاقُ النظام كلِّه بسببه ليس حلّاً أيضاً.
#
# فالنظامُ يتصرّف على ثلاث درجات:
#   ١) node مناسبٌ على المسار          ⟶ المحرّكُ يعمل كاملاً
#   ٢) node قديمٌ لكن ثمّة مناسبٌ آخرُ  ⟶ يُستعمل المناسبُ ولو لم يكن الافتراضيّ
#   ٣) لا مناسبَ إطلاقاً                ⟶ المسارُ البايثونيُّ يعمل كما هو،
#                                          ويُقال ما الناقصُ ولماذا بدقّة
#
# وتنزيلُ node تلقائياً غيرُ متاحٍ على أندرويد: سكربتُ المحرّك نفسُه
# (node-runtime-update.mjs:9) يشترط glibc، وتيرمكس على bionic. فلا نَعِد به.
NODE_RANGE = ">=24.16.0 <25 || >=26.1.0"


def node_ok(ver):
    """أيفي هذا الإصدارُ بشرط المحرّك؟ ver مثل "26.4.0". لا يرفع استثناءً."""
    try:
        parts = str(ver or "").strip().lstrip("v").split(".")
        a, b = int(parts[0]), int(parts[1] if len(parts) > 1 else 0)
        return (a == 24 and b >= 16) or (a == 26 and b >= 1) or a > 26
    except Exception:
        return False


def _node_version(path_):
    try:
        r = subprocess.run([path_, "-p", "process.versions.node"],
                           capture_output=True, text=True, timeout=20)
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def node_candidates():
    """كلُّ ما قد يكون node على هذا الجهاز — لا المسارُ الافتراضيُّ وحده.

    قد يكون على الجهاز أكثرُ من إصدار: واحدٌ على PATH وآخرُ تحت nvm أو
    تيرمكس. فلا يُحكَم بالأوّل وحده."""
    from shutil import which
    import glob as _g
    out, seen = [], set()

    def add(p):
        if p and p not in seen and os.path.isfile(p) and os.access(p, os.X_OK):
            seen.add(p)
            out.append(p)

    add((os.environ.get("WEAVER_NODE") or "").strip() or None)
    add(which("node"))
    pre = os.environ.get("PREFIX") or ""
    if pre:
        add(os.path.join(pre, "bin", "node"))
    for p in ("/data/data/com.termux/files/usr/bin/node",
              "/usr/local/bin/node", "/usr/bin/node"):
        add(p)
    for pat in (os.path.expanduser("~/.nvm/versions/node/*/bin/node"),
                "/opt/node*/bin/node",
                os.path.expanduser("~/.local/share/fnm/node-versions/*/installation/bin/node")):
        for p in sorted(_g.glob(pat), reverse=True):
            add(p)
    return out


def node_bin():
    """مسارُ node **صالحٍ للمحرّك**، أو None. يبحث في كلّ ما على الجهاز."""
    cached = getattr(node_bin, "_hit", None)
    if cached is not None:
        return cached or None
    hit = ""
    for p in node_candidates():
        if node_ok(_node_version(p)):
            hit = p
            break
    node_bin._hit = hit
    return hit or None


def node_report():
    """تقريرٌ صريحٌ عن كلّ node على الجهاز: أيُّها يصلح ولماذا."""
    rows = []
    for p in node_candidates():
        v = _node_version(p)
        rows.append({"path": p, "version": v, "ok": node_ok(v)})
    return rows


def why_unavailable():
    """سببُ الغياب بكلامٍ صريحٍ ومُقاس، لا «تعذّر»."""
    if not node_bin():
        rows = node_report()
        if not rows:
            return ("لا node على الجهاز — والمحرّك يعمل عليه.  "
                    "التثبيت: pkg install nodejs  ·  "
                    "ويبقى المسارُ البايثونيُّ (pipeline.agent) يعمل بدونه.")
        have = "، ".join(f"{r['version'] or '؟'}" for r in rows[:3])
        return (f"node الموجودُ ({have}) لا يفي بشرط المحرّك ({NODE_RANGE}).  "
                "والشرطُ حقيقيّ: node دون 24.16 يقصُّ النصوصَ في قاعدة "
                "بياناته المدمجة فتفسد البيانات صامتةً.  "
                "الترقية: pkg install nodejs (لا nodejs-lts)  ·  "
                "أو ضع مساراً صالحاً في WEAVER_NODE  ·  "
                "وحتى ذلك يعمل المسارُ البايثونيُّ (pipeline.agent) كما هو.")
    if not available():
        return ("المحرّك غير مركَّب بعد.  التركيب:  bash "
                + os.path.relpath(INSTALLER, _ROOT))
    return ""


LAST_LOG = os.path.join(STATE, "last-run.log")


def _record_run(args, code, out, err):
    """احفظ آخرَ نداءٍ كاملاً — بلا قصّ.

    كنتُ أعرض ١٢٠ حرفاً من الخطأ في الرسالة، فقُطع الجوابُ عند
    `lane task error: lane=` تماماً حيث يبدأ السببُ الحقيقيُّ:
        command-queue-CwgsqkaH.mjs:503
            `lane task error: lane=${lane} durationMs=${…} error="${…}"`
    أي أنّ الرسالةَ التي تُرى هي العنوانُ وحده، والسببُ محذوف. فصار الخرجُ
    كاملاً يُحفظ هنا، والرسالةُ تدلُّ عليه. لا يرفع استثناءً أبداً."""
    try:
        os.makedirs(STATE, exist_ok=True)
        import datetime as _dt
        with open(LAST_LOG, "w", encoding="utf-8") as fh:
            fh.write(f"# {_dt.datetime.now().isoformat(timespec='seconds')}\n")
            fh.write("# args: " + " ".join(str(a) for a in args) + "\n")
            fh.write(f"# exit: {code}\n\n--- stdout ---\n{out}"
                     f"\n\n--- stderr ---\n{err}\n")
    except Exception:
        pass


def _real_error(err):
    """السببُ من بين ضجيج التشخيص — لا العنوانُ وحده.

    المحرّكُ يطبع تحذيراتٍ ليست أخطاءً («slow SQLite transaction hold» هو
    `.warn` عن بطء التخزين، وهو متوقَّعٌ على الهاتف). فتُسقَط، ويُستخرَج ما
    بين `error="…"` إن وُجد، وإلّا فآخرُ سطرٍ ذي معنى."""
    import re as _re
    t = str(err or "")
    m = _re.search(r'error="([^"]{3,400})"', t)
    if m:
        return m.group(1).strip()
    _noise = ("slow SQLite transaction hold", "[diagnostic]", "npm warn",
              "ExperimentalWarning", "(node:")
    lines = [l.strip() for l in t.split("\n")
             if l.strip() and not any(n in l for n in _noise)]
    return lines[-1][:400] if lines else t.strip()[:400]


def run(args, timeout=180, input_text=None, cwd=None):
    """نادِ المحرّك بوسائطه. يُعيد (رمز_الخروج، المُخرَج، الخطأ)."""
    if not available():
        return 127, "", why_unavailable()
    nb = node_bin()
    if not nb:
        return 127, "", why_unavailable()
    try:
        p = subprocess.run([nb, ENTRY] + list(args or []),
                           capture_output=True, text=True, timeout=timeout,
                           input=input_text, cwd=cwd or _ROOT,
                           env=engine_env())
        _record_run(args, p.returncode, p.stdout or "", p.stderr or "")
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "", f"تجاوز المهلة ({timeout} ثانية)"
    except Exception as e:
        return 1, "", f"{type(e).__name__}: {str(e)[:160]}"


# ── البوّابة: خادمٌ دائمٌ لا يُقلع إلّا مرّة ─────────────────────────────────
#
# `agent exec` وصفُه بخطّ المحرّك: «Run one **isolated** headless **embedded**
# agent turn». ومعزولةٌ تعني عمليةَ node جديدة، و٥٩ إضافةً تُحمَّل، و٥٤ أداةً
# تُبنى، وقاعدةَ الحالة تُفتح — في كلِّ رسالة. مقيسٌ على خادمٍ سريع:
#
#     agent exec "مرحبا"  ⟶  8.57 ث حتى مجرّدِ فحصِ المفتاح
#     agent -m  "مرحبا"   ⟶  1.43 ث  (والبوّابةُ تردّ صحّتَها في 4ms)
#
# وعلى هاتفٍ بمعالج ARM يتضاعف ذلك أضعافاً — وهو سببُ الدقيقتين والثلاث.
#
# وليس هذا حلّاً من عندنا: `agent` وصفُه عنده «Run an agent turn **via the
# Gateway**»، و`gateway run` و`daemon install` أوامرُه هو. فمسارُه العاديُّ
# هو البوّابة، و`agent exec` هو الاستثناءُ المعزول — وأنا اخترتُ الاستثناء.
#
# وتحلّ معها مشكلةٌ ثانية: `--session-id` يمنح استمرارَ المحادثة، وهو ما لا
# يستطيعه المعزولُ أبداً.
GATEWAY_LOG = os.path.join(STATE, "gateway.log")
_GW_READY_WAIT = 90          # ثانيةً ننتظر إقلاعَ البوّابة
_gw_lock = threading.Lock()


def gateway_on():
    """أمسموحٌ باستعمال البوّابة؟ (`WEAVER_GATEWAY=0` يُطفئها)"""
    return (os.environ.get("WEAVER_GATEWAY", "1") or "1").strip() not in (
        "0", "false", "no")


def gateway_port():
    """المنفذُ الذي تسمع عليه بوّابتُنا."""
    try:
        return int(engine_env().get("OPENCLAW_GATEWAY_PORT") or OUR_PORT)
    except Exception:
        return OUR_PORT


def _gateway_lock():
    """قفلُ البوّابة كما يكتبه المحرّك — أو {}.

        paths-V8kKIUzt.mjs:261  resolveGatewayLockDir
            <stateDir>/tmp/openclaw-<uid>/gateway.state.lock

    وفيه `pid` و`port` و`stateDir`. يُقرأ ولا يُكتب."""
    try:
        uid = os.getuid() if hasattr(os, "getuid") else None
        sub = ("openclaw-%d" % uid) if uid is not None else "openclaw"
        f = os.path.join(_STATE_DIR, "tmp", sub, "gateway.state.lock")
        import json as _j
        with open(f, encoding="utf-8") as fh:
            d = _j.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def gateway_health(timeout=2):
    """أحيّةٌ البوّابةُ الآن؟ — اتّصالٌ بالمنفذ، لا نداءُ أمر.

    كان هذا `gateway health`، وهو صحيحٌ لكنّه يُقلع node في كلّ فحص (١.٤ ث)
    — ونحن نفحص قبل كلِّ رسالة، فيُلتهم بعضُ ما وفّرناه. والاتّصالُ بالمنفذ
    يقول الحقيقةَ نفسَها في أجزاءٍ من الثانية.

    ولا يرفع استثناءً."""
    import socket as _s
    sk = _s.socket()
    try:
        sk.settimeout(float(timeout))
        sk.connect(("127.0.0.1", gateway_port()))
        return True
    except Exception:
        return False
    finally:
        try:
            sk.close()
        except Exception:
            pass


def gateway_start(wait=None):
    """أقلِع البوّابةَ في الخلفية وانتظرها حتى تسمع. يعيد (نجح، سبب).

    مؤمَّنٌ بقفلٍ كي لا يُقلعها خيطان معاً، وأوّلُ ما يفعل أن يسأل: أهي حيّةٌ
    سلفاً؟ فالإقلاعُ الثاني ضياعٌ ومنفذٌ مشغول."""
    wait = int(wait or _GW_READY_WAIT)
    with _gw_lock:
        if gateway_health():
            return True, "كانت حيّةً سلفاً"
        nb = node_bin()
        if not (available() and nb):
            return False, why_unavailable()
        try:
            os.makedirs(STATE, exist_ok=True)
            _log = open(GATEWAY_LOG, "ab", buffering=0)
        except Exception:
            _log = subprocess.DEVNULL
        try:
            # مفصولةٌ عن هذه العملية: تبقى حيّةً بعد انتهاء الطلب، وتُهمل
            # إشارةَ المقاطعة التي تصل الأبَ (start_new_session).
            subprocess.Popen(
                [nb, ENTRY, "gateway", "run", "--allow-unconfigured"],
                stdout=_log, stderr=_log, stdin=subprocess.DEVNULL,
                cwd=_ROOT, env=engine_env(), start_new_session=True)
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:160]}"
        _t0 = time.time()
        while time.time() - _t0 < wait:
            if gateway_health():
                return True, f"أقلعت في {time.time() - _t0:.1f} ث"
            time.sleep(1)
        return False, f"لم تسمع خلال {wait} ث — انظر {GATEWAY_LOG}"


def gateway_stop():
    """أطفئ البوّابة — بإشارةٍ إلى العملية التي يسمّيها قفلُه هو.

    ولا `gateway stop`: هي إدارةُ خدمةٍ (systemd/launchd)، وترفض أصلاً حين
    يكون `OPENCLAW_STATE_DIR` غيرَ الافتراضيّ — وهو حالُنا دائماً:
        «service management skipped: non-default state dir or config path»

    ولا `pkill -f`: نمطُها يُطابق سطرَ الأوامر كاملاً — بما فيه سطرُ `pkill`
    نفسِه ومَن ناداه — فتقتل الصَّدفةَ التي تُشغّلها. مقيسٌ لا مُخمَّن: جرّبتُها
    فقتلت جلستي.

    والعمليةُ تُعيد تسميةَ نفسِها إلى `openclaw-gateway`، فلا يُجدي البحثُ عن
    سطر التشغيل. فيُقرأ رقمُها من القفل — وهو مصدرُ الحقيقة عند المحرّك.

    وإطفاءٌ بإشارةٍ لطيفة (SIGTERM) كي تُنظّف قفلَها بنفسها؛ فالقتلُ القاسي
    يُخلّف قفلاً بائتاً يمنع كلَّ إقلاعٍ بعده:
        «Another gateway (pid …) already owns this state directory»"""
    d = _gateway_lock()
    pid = d.get("pid")
    if not isinstance(pid, int) or pid <= 1 or pid == os.getpid():
        return (not gateway_health()), "لا قفلَ صالحاً"
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return (not gateway_health()), "لم تكن تعمل"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:120]}"
    _t0 = time.time()
    while time.time() - _t0 < 25:
        if not gateway_health():
            return True, f"أُطفئت في {time.time() - _t0:.1f} ث"
        time.sleep(1)
    return False, "لم تستجب لـSIGTERM خلال ٢٥ ث"


def gateway_state():
    """وصفٌ موجزٌ لحال البوّابة — للتشخيص."""
    return {"allowed": gateway_on(), "alive": gateway_health(),
            "port": gateway_port(), "pid": _gateway_lock().get("pid") or "—",
            "log": GATEWAY_LOG}


# ── (أ) إشعالُ ما يملكه المحرّكُ أصلاً لتخفيف الكلفة ──────────────────────
#
# نداءٌ واحدٌ كلّف ٢٣١٦٨ رمزَ مدخلاتٍ مقابل ٣٣ للجواب، لأنّ كتالوجَ الأدوات
# يُرسَل كاملاً في كلّ مرّة. وللمحرّك آليّتُه لذلك، مُطفأةٌ افتراضياً:
#
#     tools.toolSearch.enabled = true
#     tools.toolSearch.mode    = "directory"
#
# فبدل إرسال الكتالوج كلِّه، يُرسَل فهرسٌ مختصرٌ وثلاثُ أدواتِ تحكّم
# (`tool_search` · `tool_describe` · `tool_call`)، والنموذجُ يطلب تفصيلَ
# الأداة حين يحتاجها فقط.
#
# وتعليقُهم يقول لماذا الافتراضيُّ مُطفأ:
#     core-tool-factory-descriptors-DvHWmRcY.mjs:236
#     "hiding them behind search adds a lookup round-trip to nearly every
#      coding turn."
# أي: يوفّر رموزاً ويكلّف جولةً. مقايضةٌ تُشعَل وتُطفَأ.
#
# ولا يُكتب الإعدادُ بيدنا: يُضبط بأمر المحرّك `config set` — فهو الذي
# يتحقّق من المفتاح والقيمة ويرفض الخطأ. فلا نكتب إعداداً نخمّنه.
TUNING = (("tools.toolSearch.enabled", "true"),
          ("tools.toolSearch.mode", "directory"))


# ── بحثُ الويب: كتالوجُ أوبن كلاو نفسُه ──────────────────────────────────────
#
# أداتا `web_search` و`web_fetch` في المحرّك أصلاً، لكنّ المزوّدَ لا يأتي
# مُرفَقاً: أوبن كلاو يجعله إضافةً رسميّةً تُركَّب، ثمّ يختار تلقائياً بترتيبٍ
# مُعلَنٍ في كتالوجه (autoDetectOrder):
#
#     brave 10 · kimi 40 · perplexity 50 · firecrawl 60 · exa 65
#     tavily 70 · parallel 75 · duckduckgo 100 · searxng 200
#
# فهاتان من كتالوجه هو — لا اختيارَ لنا فيهما إلّا أنّهما الوحيدتان اللتان
# تعملان بما عند المستخدم: perplexity يقرأ OPENROUTER_API_KEY (مفتاحُ النظام
# أصلاً)، وduckduckgo بلا مفتاحٍ فيبقى البحثُ عاملاً على كلّ حال.
#
# وهذا لا يمسُّ قواعدَ النظام الأكاديمية بحال: تلك لأنابيب المستندات، وهذه
# أدواتُ المحرّك وحده.
WEB_SEARCH_PLUGINS = ("duckduckgo", "perplexity")
WEB_SEARCH_KEY = "tools.web.search.enabled"


def enable_web_search():
    """يُركّب مزوّدَي البحثِ الرسميّين ويُفعّل الأداة — بأوامر المحرّك نفسِه.

    يعيد قائمةَ (اسم، نجح، سطرُ السبب). لا يرفع استثناءً، ولا يُوقف شيئاً إن
    فشل: المحرّكُ يعمل بلا بحثٍ أيضاً."""
    rows = []
    have = web_search_state()["installed"]
    for pid in WEB_SEARCH_PLUGINS:
        # مُركَّبةٌ سلفاً ⟶ لا يُعاد التركيب. والمحرّكُ يرفض إعادتَه بـ"already
        # exists"، فلو عُدَّ ذلك فشلاً لأفزع المستخدمَ من حالةٍ سليمة.
        if pid in have:
            rows.append((pid, True, "مُركَّبةٌ سلفاً"))
            continue
        code, out, err = run(["plugins", "install",
                              "@openclaw/" + pid + "-plugin",
                              "--accept-capabilities"], timeout=420)
        rows.append((pid, code == 0, _real_error(err) or (err or "").strip()[:160]))
    code, out, err = run(["config", "set", WEB_SEARCH_KEY, "true"], timeout=90)
    rows.append((WEB_SEARCH_KEY, code == 0,
                 _real_error(err) or (err or "").strip()[:160]))
    return rows


def web_search_state():
    """ماذا يقول المحرّكُ عن بحث الويب الآن؟ (مُركَّب؟ مُفعَّل؟)"""
    code, out, _ = run(["config", "get", WEB_SEARCH_KEY], timeout=60)
    enabled = (code == 0 and "true" in (out or "").lower())
    code2, out2, _ = run(["plugins", "list"], timeout=180)
    have = [p for p in WEB_SEARCH_PLUGINS if code2 == 0 and p in (out2 or "")]
    return {"enabled": enabled, "installed": have}


def tune(revert=False):
    """اضبط إعداداتِ التخفيف في حالتنا المعزولة. يُعيد قائمةَ (مفتاح، نجاح، رسالة)."""
    out = []
    for key, val in TUNING:
        v = ("false" if val == "true" else "off") if revert else val
        code, so, se = run(["config", "set", key, v], timeout=120)
        msg = (se or so or "").strip().split("\n")[-1][:160]
        out.append((key, v, code == 0, msg))
    return out


def tuning_state():
    """ما هو المضبوطُ الآن فعلاً — من المحرّك لا من ظنّنا."""
    out = []
    for key, _ in TUNING:
        code, so, se = run(["config", "get", key], timeout=120)
        out.append((key, (so or se or "").strip().split("\n")[-1][:80]
                    if code == 0 else "—"))
    return out


def version():
    """إصدارُ المحرّك، أو ""."""
    code, out, _ = run(["--version"], timeout=60)
    return out.strip().split("\n")[0] if code == 0 else ""


def _from_envelope(out):
    """اقرأ جوابَ `--json` — والمُغلَّفُ مُنسَّقٌ على أسطر.

    عطبان اجتمعا فطُبع المُغلَّفُ الخامُ للمستخدم بدل الجواب:

    ١) كنتُ أمسح الأسطرَ من آخرها بحثاً عن سطرٍ يبدأ بـ`{`، ظنّاً أنّ
       المُغلَّفَ سطرٌ واحد. وهو مُنسَّقٌ فعلياً:
           {
             "ok": true,
             "final": "مرحبا!",
             …
       فالسطرُ `{` وحده ليس JSON صالحاً، وكذلك `}` — فيفشل التحليلُ كلُّه.
       والنصُّ كلُّه JSON صالحٌ من أوّله، فيُجرَّب كاملاً أوّلاً.

    ٢) وحقلُ الجواب اسمُه `final` (ومعه `payloads[].text`)، ولم يكن في
       قائمتي أصلاً — فحتى لو حُلِّل لَما وُجد. مأخوذٌ من مُغلَّفٍ حقيقيّ:
           {"ok": true, "status": "ok", "final": "…",
            "payloads": [{"text": "…", "mediaUrl": null}],
            "model": "…", "provider": "…"}

    وعند العجز يُعاد النصُّ الخام — فلا يضيع جوابٌ أبداً."""
    t = str(out or "").strip()
    if not t:
        return ""
    import json as _j

    def _parse(txt):
        try:
            return _j.loads(txt)
        except Exception:
            return None

    data = _parse(t)
    if data is None and "{" in t:                 # سجلٌّ قبل المُغلَّف
        i, jx = t.find("{"), t.rfind("}")
        if 0 <= i < jx:
            data = _parse(t[i:jx + 1])
    if data is None:                              # وربّما سطرٌ واحدٌ أخير
        for line in reversed(t.split("\n")):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                data = _parse(line)
                if data is not None:
                    break
    if not isinstance(data, dict):
        return t
    # `final` أوّلاً: هو حقلُ الجواب في مُغلَّف المحرّك
    for k in ("final", "text", "message", "answer", "output", "reply",
              "content", "result"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for k2 in ("final", "text", "content", "message"):
                if isinstance(v.get(k2), str) and v[k2].strip():
                    return v[k2].strip()
    parts = []                                    # ثمّ payloads[].text
    _pl = data.get("payloads")
    if not _pl and isinstance(data.get("result"), dict):
        # مُغلَّفُ البوّابة يضعها تحت `result`:
        #   {"status":"ok","result":{"payloads":[{"text":"…"}]}}
        _pl = data["result"].get("payloads")
    for it in (_pl or []):
        if isinstance(it, dict) and isinstance(it.get("text"), str) \
                and it["text"].strip():
            parts.append(it["text"].strip())
    if parts:
        return "\n\n".join(parts)
    if data.get("ok") is False or data.get("status") == "error":
        err = data.get("error")
        if isinstance(err, dict) and isinstance(err.get("message"), str):
            return "error: " + err["message"]
    return t


def _session_id(key):
    """مُعرِّفُ جلسةٍ ثابتٌ ونظيف من مفتاحٍ أيّاً كان شكلُه.

    يُمرَّر إلى `--session-id`، فيجب أن يبقى هو نفسَه لنفس المحادثة (وإلّا
    ضاع الاستمرار) وأن يخلو ممّا قد يُربك سطرَ الأوامر."""
    import re as _re
    k = _re.sub(r"[^A-Za-z0-9_-]", "-", str(key or "").strip())[:48]
    return ("weaver-" + k) if k else "weaver-default"


def ask(text, timeout=300, cwd=None, fallback=True, session=None):
    """اسأل — بالمحرّك إن أمكن، وإلّا بالمسار البايثونيّ.

    الدرجةُ الثالثة: **أيُّ سؤالٍ يُجاب على أيّ إصدارِ node، ولو لم يكن ثمّة
    node أصلاً.** فالمحرّكُ إضافةٌ لا شرط. وحين يتولّى البديلُ يُقال ذلك في
    `engine` لا يُخفى، كي لا تظنّ أنّك تُشغّل ما لا تُشغّله.

    والأمرُ الصحيحُ `agent exec` — «Run one isolated headless embedded agent
    turn» كما يصفه المحرّك نفسُه:
        register.agent-turn-gi9D9FTy.mjs:41   command("exec [message]")
    لقطةٌ واحدةٌ معزولةٌ بلا جسرٍ ولا واجهةٍ تفاعلية، و`--json` يُعطي مُغلَّفاً
    ثابتاً بدل نصٍّ يُقرأ بالحدس.

    وكنتُ قبله أنادي `run` ظنّاً لا تحقّقاً، فردّ المحرّكُ على المستخدم:
    «Weaver Write does not know the command "run"». التدهورُ الآمنُ أنقذ
    الموقف — تولّى المسارُ البايثونيُّ وقال السبب — لكنّ الخطأ كان خطئي:
    زعمتُ في تعليقٍ أنّه «مدخلُ الحزمة للتشغيل غير التفاعليّ» بلا دليل."""
    if available() and node_bin():
        _to = str(max(30, int(timeout) - 20))
        _via_gateway = False
        if gateway_on():
            _ok, _why = gateway_start()
            _via_gateway = bool(_ok)
            if not _ok:
                _record_run(["gateway", "start"], 1, "", str(_why))
        if _via_gateway:
            # المسارُ العاديُّ عند المحرّك: نوبةٌ عبر بوّابةٍ حيّة، بلا إقلاع.
            args = ["agent", "-m", str(text or ""), "--json",
                    "--timeout", _to]
            if session:
                # استمرارُ المحادثة — وهو ما يعجز عنه `exec` المعزول.
                args += ["--session-id", _session_id(session)]
        else:
            # ولا بوّابة: اللقطةُ المعزولة كما كانت حرفاً — أبطأ، لكنّها
            # تعمل حيث لا تقوم البوّابة.
            args = ["agent", "exec", str(text or ""), "--json",
                    "--timeout", _to]
            if cwd:
                args += ["--cwd", str(cwd)]
        if (os.environ.get("WEAVER_ENGINE_LEAN", "") or "").strip() == "1":
            # سطحٌ مُخفَّفٌ من الأدوات. مُطفأٌ افتراضياً لأنّه قد يحجب أداةً
            # تلزم المهمّة — والتوفيرُ الأكبرُ في toolSearch لا فيه.
            args.append("--local-model-lean")
        _m = model_id()
        if _m:
            # بلا هذا يسقط المحرّكُ إلى نموذجه الافتراضيّ (openai/…) ثمّ
            # يفشل بـauth — وهو بالضبط ما رآه المستخدم.
            args += ["--model", _m]
        code, out, err = run(args, timeout=timeout, cwd=cwd)
        if code == 0 and out.strip():
            return {"answer": _from_envelope(out), "engine": "weaver-core",
                    "note": ""}
        if not fallback:
            return {"answer": "", "engine": "weaver-core",
                    "note": (err or out).strip()[:400]}
        _note = ("المحرّك لم يُجب [رمز " + str(code) + "]: "
                 + (_real_error(err) or "بلا سبب معلوم")
                 + "  ·  الخرجُ كاملاً: python3 -m pipeline.weaver_core --last"
                 + "  ·  فتولّى المسارُ البايثونيّ")
    else:
        _note = why_unavailable()
        if not fallback:
            return {"answer": "", "engine": "", "note": _note}
    try:
        from pipeline.agent import ask as _pyask
        r = _pyask(str(text or ""))
        return {"answer": r.get("answer", ""), "engine": "python",
                "note": _note}
    except Exception as e:
        return {"answer": "", "engine": "",
                "note": f"{_note} | {type(e).__name__}: {str(e)[:120]}"}


def _cli():
    argv = sys.argv[1:]
    # التشخيصُ يعمل دائماً — وهو أنفعُ ما يكون حين لا يعمل شيءٌ آخر.
    if argv == ["--nodes"]:
        rows = node_report()
        if not rows:
            print("  لا node على الجهاز")
        for r in rows:
            print(f"  {'صالح ' if r['ok'] else 'قديم '} v{r['version'] or '؟':<10} {r['path']}")
        print(f"\n  شرطُ المحرّك: {NODE_RANGE}")
        sel = node_bin()
        print("  المختار   : " + (sel if sel else "لا شيء — "
                                  + why_unavailable().split(".")[0]))
        return
    if argv == ["--where"]:
        for k, v in state_paths().items():
            print(f"  {k:6s} {v}")
        return
    if argv in (["--tune"], ["--tune", "--revert"]):
        if not available():
            print("المحرّك غير مركَّب بعد.", file=sys.stderr)
            sys.exit(2)
        _rev = "--revert" in argv
        print("  إطفاءُ التخفيف…" if _rev else "  إشعالُ التخفيف…")
        _bad = 0
        for k, v, okk, msg in tune(revert=_rev):
            print(f"    {'✓' if okk else '✗'} {k} = {v}"
                  + ("" if okk else f"   — {msg}"))
            _bad += 0 if okk else 1
        print()
        print("  الحالةُ الآن (من المحرّك):")
        for k, v in tuning_state():
            print(f"    {k} = {v}")
        sys.exit(1 if _bad else 0)
    if argv == ["--provider"]:
        _p, _m, _c = provider_id(), model_id(), credentials()
        print(f"  المزوّد   : {_p or '— غير معروف'}")
        print(f"  النموذج   : {_m or '— غير محدَّد (سيسقط المحرّكُ لافتراضيّه)'}")
        print("  المفتاح   : " + (", ".join(
            f"{k}=…{v[-4:]}" for k, v in _c.items())
            if _c else "— لا مفتاح (WEAVER_API_KEY فارغ)"))
        if not _c:
            print()
            _envf = os.path.join(_ROOT, "config", ".env")
            print(f"  مصدرُ الحقيقة: {_envf}"
                  + ("" if os.path.isfile(_envf) else "   ⟵ غير موجود"))
            print("  (وهو نفسُه الذي تتشارك فيه الطرفيةُ وواجهةُ الويب)")
            print()
            print("  اضبطه من الواجهة، أو بالسطر:")
            print("     python3 -c \"import sys;sys.path.insert(0,'.');"
                  "from config.keysync import set_api_key;"
                  "set_api_key('مفتاحك')\"")
        return
    if argv == ["--last"]:
        if os.path.isfile(LAST_LOG):
            sys.stdout.write(open(LAST_LOG, encoding="utf-8",
                                  errors="replace").read())
        else:
            print("لا سجلَّ بعد — شغّل سؤالاً أوّلاً.")
        return
    if argv == ["--repair"]:
        # يُصلح تركيباً قائماً بلا إعادة جلبٍ ولا إعادة تسمية.
        # ولا يحتاج node: إنّما يُعدّل ملفّات. فالشرطُ وجودُ المحرّك وحده،
        # لا صلاحيةُ node — وخلطُهما كان يطبع سببَ غيابٍ لا علاقةَ له.
        if not available():
            print("المحرّك غير مركَّب بعد.  التركيب:  bash "
                  + os.path.relpath(INSTALLER, _ROOT), file=sys.stderr)
            sys.exit(2)
        import subprocess as _sp
        _script = os.path.join(_ROOT, "engines", "weaver-core",
                               "patch_portability.py")
        _r = _sp.run([sys.executable, _script, RUNTIME])
        sys.exit(_r.returncode)
    if argv[:1] == ["--gateway"]:
        sub = argv[1] if len(argv) > 1 else "status"
        if sub == "start":
            ok, why = gateway_start()
            print(("  ✓ البوّابة حيّة — " if ok else "  ⚠ لم تقم — ") + str(why))
            return
        if sub == "stop":
            ok, why = gateway_stop()
            print(("  ✓ أُطفئت" if ok else "  ⚠ ما زالت حيّة — " + str(why)))
            return
        st = gateway_state()
        print(f"  مسموحة : {'نعم' if st['allowed'] else 'لا (WEAVER_GATEWAY=0)'}")
        print(f"  حيّة    : {'نعم' if st['alive'] else 'لا'}")
        print(f"  المنفذ  : {st['port']}   ·   pid: {st['pid']}")
        print(f"  السجلّ  : {st['log']}")
        return
    if argv == ["--web-search"]:
        if not (available() and node_bin()):
            print(why_unavailable(), file=sys.stderr)
            sys.exit(2)
        print("  تركيبُ مزوّدَي البحثِ من كتالوج أوبن كلاو…")
        for name, ok, why in enable_web_search():
            print(f"    {'✓' if ok else '⚠'} {name}"
                  + ("" if ok else "   " + (why or "تعذّر")))
        st = web_search_state()
        print(f"\n  مُفعَّل: {'نعم' if st['enabled'] else 'لا'}"
              f"   ·   مُركَّب: {', '.join(st['installed']) or 'لا شيء'}")
        return
    if argv == ["--isolation"]:
        iso = isolation()
        print(f"  البروفايل : {iso['profile']}")
        print(f"  الحالة    : {iso['state']}")
        print(f"  البيت     : {iso['home']}")
        print(f"  المنفذ    : {iso['port']}   (الافتراضيُّ {DEFAULT_PORT})")
        inh = iso["inherited_openclaw_vars"]
        print("  موروثٌ من بيئتك: "
              + (", ".join(inh) if inh else "لا شيء")
              + ("  ⟵ كلُّها تُحذف قبل التشغيل" if inh else ""))
        return
    if argv == ["--doctor"]:
        print(f"  المحرّك مركَّب : {'نعم' if available() else 'لا'}")
        print(f"  node صالح     : {node_bin() or 'لا'}")
        _w = why_unavailable()
        print("  " + (_w if _w else "جاهز ✅"))
        return
    if not available() or not node_bin():
        print(why_unavailable(), file=sys.stderr)
        sys.exit(2)
    if not argv or argv == ["--version"]:
        print(version() or "(بلا جواب)")
        return
    if argv[0].startswith("-") or argv[0] in (
            "run", "gateway", "onboard", "config", "doctor", "help"):
        code, out, err = run(argv, timeout=900)
        sys.stdout.write(out)
        sys.stderr.write(err)
        sys.exit(code)
    r = ask(" ".join(argv))
    if r.get("note"):
        print("  ⓘ " + r["note"][:200], file=sys.stderr)
    print(r.get("answer") or "(بلا جواب)")


if __name__ == "__main__":
    _cli()
