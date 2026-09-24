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
# خريطةٌ احتياطيّةٌ صغيرة — تُقرأ من المحرّك أوّلاً (`key_env_name`)،
# وهذه تُستعمل فقط حين يتعذّر النداء.
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
        # أيُّ منصّةٍ لا مزوّدَ لها مدمجاً في المحرّك ⟶ مزوّدُنا المخصَّص.
        # (`engine_route` وتعليلُها أسفل، عند `model_ref`.)
        _r = engine_route()
        if _r.get("mode") in ("custom", "bundled"):
            return _r.get("ref", "")
        m = _setting("WEAVER_MODEL")
        if not m:
            return ""
        prov = provider_id()
        if not prov:
            return ""
        return m if m.startswith(prov + "/") else f"{prov}/{m}"
    except Exception:
        return ""


def key_env_name(provider=None):
    """اسمُ متغيّرِ المفتاح لمزوّدك — بسؤال المحرّك أوّلاً.

        config-provider-contract-BdOif1pq.mjs  resolveHermesProviderApiKeyEnv
    يعرفها للمزوّدين كلِّهم ويشتقُّ ما لا يُسمّيه صراحةً. وخريطتُنا اليدويّةُ
    احتياطٌ حين يتعذّر النداء."""
    prov = (provider or provider_id() or "").lower()
    if not prov:
        return ""
    for r in auth_catalog():
        if str(r.get("providerId", "")).lower() == prov and r.get("envVar"):
            return str(r["envVar"])
    return _PROVIDER_ENV.get(prov, "")


def credentials():
    """{اسمُ المتغيّر: المفتاح} كما يفهمها المحرّك — أو {}."""
    try:
        key = _setting("WEAVER_API_KEY")
        # منصّةٌ مخصَّصة: مفتاحُها باسمنا، ويُشار إليه من إعداد المحرّك بـ
        # `${WEAVER_PLATFORM_API_KEY}` — لا باسم مزوّدٍ لم يُركَّب.
        _r = engine_route() if key else {}
        if _r.get("mode") == "custom":
            return {CUSTOM_KEY_ENV: key}
        # مزوّدٌ مدمج: باسمِ المزوّد الذي يملك رابطَك (رابطُ Gemini المتوافقُ
        # `…/v1beta/openai` كان يُنسَب إلى openai لأنّ الكلمةَ في مساره).
        if _r.get("mode") == "bundled":
            _n = key_env_name(_r.get("provider"))
            if _n:
                return {_n: key}
        name = key_env_name()
        if not (key and name):
            return {}
        return {name: key}
    except Exception:
        return {}


def engine_env(extra=None, no_credentials=False):
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
    for _k, _v in ({} if no_credentials else credentials()).items():
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
    """السببُ من بين ضجيج التشخيص — لا العنوانُ ولا آخرُ سطر.

    عطبٌ كشفته بطاقةُ الفشل على جهاز المستخدم: ظهر فيها
        [31m[sqlite/transaction][39m … [openclaw] The CLI command failed. …
    أي ضجيجٌ ورموزُ ألوانٍ وعنوانٌ بلا سبب. وسببُه أمران:

    ① رموزُ ANSI لم تُنزَع. المحرّكُ يلوّن خرجَه، فتدخل `[31m` و`[39m`
       في النصّ وتُفسده.
    ② كنتُ أبحث عن `error="…"` — وهو شكلُ `agent exec` وحده. أمّا مسارُ
       البوّابة فيطبع:
           [openclaw] The CLI command failed.
           [openclaw] Reason: <السببُ الحقيقيّ>
           [openclaw] Debug: set OPENCLAW_DEBUG=1 …
           [openclaw] Try: …      [openclaw] Help: …
       فآخرُ سطرٍ ذي معنى هو «Help:» — لا قيمةَ له. والسببُ في `Reason:`.

    فصار يُنزع اللونُ أوّلاً، ثمّ يُلتقط `Reason:`، ثمّ `error="…"`، ثمّ
    آخرُ سطرٍ بعد إسقاط الصفيح."""
    import re as _re
    t = str(err or "")
    # ① نزعُ ANSI: CSI وOSC معاً
    t = _re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", t)
    t = _re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", t)
    # وبعضُ السجلّات تصل بالرموز حرفيّةً بلا ESC («[31m» نصّاً)
    t = _re.sub(r"\[(?:\d{1,3}(?:;\d{1,3})*)m", "", t)

    # ② السببُ كما يسمّيه المحرّكُ نفسُه
    m = _re.search(r"Reason:\s*(.+)", t)
    if m:
        _r = m.group(1).strip()
        if _r:
            return _r[:400]
    m = _re.search(r'error="([^"]{3,400})"', t)
    if m:
        return m.group(1).strip()

    # ③ وإلّا: آخرُ سطرٍ بعد إسقاط الصفيح — والصفيحُ يشمل سطورَ الإرشاد
    #    التي تلي السبب، فهي آخرُ ما يُطبع وأقلُّ ما يُفيد.
    _noise = ("slow SQLite transaction hold", "[diagnostic]", "npm warn",
              "ExperimentalWarning", "(node:", "The CLI command failed",
              "Debug: set", "Try: ", "Help: ", "--help", "doctor")
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
# مهلةُ إقلاع البوّابة. كانت ٩٠ ثانية، فلم تكفِ على هاتف المستخدم:
#     ⚠ لم تسمع خلال 90 ث
# والإقلاعُ عندي على خادمٍ سريعٍ ٥ ثوانٍ فقط — والهاتفُ أبطأ أضعافاً:
# معالجُ ARM، وتخزينٌ أبطأ، و٥٩ إضافةً تُحمَّل، وقاعدةُ حالةٍ تُفتح (وسجلُّه
# يشكو «slow SQLite transaction hold» أصلاً). فرُفعت، وتُضبَط بـ
# `WEAVER_GATEWAY_WAIT` لمن أراد.
try:
    _GW_READY_WAIT = int(os.environ.get("WEAVER_GATEWAY_WAIT", "300") or 300)
except Exception:
    _GW_READY_WAIT = 300
_gw_lock = threading.Lock()

# ── مهلةُ نوبة الوكيل: قيمةُ المحرّك، لا قيمةٌ من عندنا ────────────────────
#
# هذا كان العطبَ الذي أعمانا. كنّا نقصُّ مهلةَ النوبة إلى ٢٢٠ ثانية:
#
#     _to = str(max(30, int(timeout) - 20))        ⟵ مع timeout=240
#
# والمحرّكُ نفسُه مهلتُه الافتراضيّةُ **٦٠٠** ثانية، مكتوبةً في تسجيل أمرِه:
#
#     register.agent-turn-gi9D9FTy.mjs:41
#       .option("--timeout <seconds>", "Agent deadline in seconds", "600")
#     register.agent-turn-gi9D9FTy.mjs:14   (المسارُ عبر البوّابة)
#       "Override agent command timeout (seconds, default 600 or config value)"
#
# و«قيمةُ الإعداد» مفتاحُها عنده:
#
#     builtin-openclaw-B-H-7lKk.mjs:14983
#       const agentTimeoutSeconds = params?.cfg?.agents?.defaults?.timeoutSeconds
#
# ونوباتُ المستخدم المقيسةُ على هاتفه: ٧ دقائق، ودقيقتان، و٦ دقائق —
# أي ٤٢٠ و١٢٠ و٣٦٠ ثانية. فنوبتان من ثلاثٍ تتجاوزان ٢٢٠، فتُقتلان:
#
#     run() ⟶ subprocess.TimeoutExpired ⟶ رمز 124
#          ⟶ ask() تعيد خطأً
#          ⟶ _chat_via_engine تعيد None
#          ⟶ _chat_direct: نداءٌ واحدٌ **بلا أدوات** ⟶ بلا إنترنت
#
# فالنتيجةُ التي يراها المستخدم: جوابٌ واثقٌ لا يعرف شيئاً عن اليوم. لا
# لأنّ البحثَ معطوب — بل لأنّنا نقتل النوبةَ قبل أن يبحث.
_AGENT_GRACE = 90          # إقلاعُ البوّابة وفتحُ العملية على هاتف
_AGENT_DEADLINE_DEFAULT = 600


def agent_deadline():
    """مهلةُ نوبة الوكيل بالثواني — ٦٠٠ كما عند المحرّك، وتُضبَط بالبيئة."""
    try:
        v = int(os.environ.get("WEAVER_AGENT_DEADLINE", "")
                or _AGENT_DEADLINE_DEFAULT)
        return v if v >= 60 else _AGENT_DEADLINE_DEFAULT
    except Exception:
        return _AGENT_DEADLINE_DEFAULT


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


def _log_reason(lines=400):
    """السببُ من ذيل سجلِّ البوّابة — لا إحالةٌ إلى ملفٍّ يبحث فيه.

    يُنقَّى كما يُنقَّى خرجُ الأوامر (ألوانٌ وضجيج)، ويُفضَّل سطرُ خطأٍ صريح."""
    try:
        with open(GATEWAY_LOG, encoding="utf-8", errors="replace") as fh:
            tail = fh.readlines()[-int(lines):]
    except Exception:
        return ""
    import re as _re
    txt = _real_error("".join(tail))
    # سطرٌ يحمل خطأً صريحاً أولى من آخر سطر
    for ln in reversed(tail):
        c = _real_error(ln)
        if _re.search(r"(?i)\b(error|fatal|EADDRINUSE|EACCES|ECONNREFUSED|"
                      r"refusing|failed|cannot|denied)\b", c):
            return c[:300]
    return txt[:300]


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


def gateway_start(wait=None, say=None):
    """أقلِع البوّابةَ في الخلفية وانتظرها حتى تسمع. يعيد (نجح، سبب).

    مؤمَّنٌ بقفلٍ كي لا يُقلعها خيطان معاً، وأوّلُ ما يفعل أن يسأل: أهي حيّةٌ
    سلفاً؟ فالإقلاعُ الثاني ضياعٌ ومنفذٌ مشغول.

    و`say` دالّةُ طباعةٍ اختياريّة. وبلا نبضِ حياةٍ ظنّ المستخدمُ أنّ الأمرَ
    علّق ثمانيَ دقائق، وهو يُقلع بوّابةً ثمّ يكتب إعداداً — في صمتٍ تامّ.
    فالصمتُ نفسُه كان العطب."""
    wait = int(wait or _GW_READY_WAIT)

    def _say(t):
        if say:
            try:
                say(str(t))
            except Exception:
                pass
    with _gw_lock:
        if gateway_health():
            return True, "كانت حيّةً سلفاً"
        nb = node_bin()
        if not (available() and nb):
            return False, why_unavailable()
        # قفلٌ بائتٌ يمنع كلَّ إقلاعٍ بعده. المحرّكُ يقولها ويقف:
        #   «Another gateway (pid …) already owns this state directory;
        #    refusing to run … Stop it with "openclaw gateway stop"»
        # والمنفذُ مغلقٌ ولا عمليةَ حيّة — فالقفلُ يكذب. يُنظَّف.
        if not _gateway_pids():
            try:
                uid = os.getuid() if hasattr(os, "getuid") else None
                sub = ("openclaw-%d" % uid) if uid is not None else "openclaw"
                d = os.path.join(_STATE_DIR, "tmp", sub)
                for f in os.listdir(d):
                    if f.startswith("gateway.") and ".lock" in f:
                        try:
                            os.remove(os.path.join(d, f))
                        except Exception:
                            pass
            except Exception:
                pass
        # منصّةٌ تغيّرت منذ آخر كتابة ⟶ تُكتب **قبل** الإقلاع: المزوّدُ
        # المخصَّصُ لا تراه بوّابةٌ حيّة («Restart the gateway to apply»)،
        # فلو كُتب بعدها لفشلت أوّلُ نوبة. وإن لم تتغيّر: قراءةُ ملفّ.
        try:
            if _applied_fingerprint() != _model_fingerprint():
                _say("… كتابةُ منصّتِك في المحرّك قبل الإقلاع")
                configure_model()
        except Exception:
            pass
        try:
            os.makedirs(STATE, exist_ok=True)
            _log = open(GATEWAY_LOG, "ab", buffering=0)
        except Exception:
            _log = subprocess.DEVNULL
        try:
            # مفصولةٌ عن هذه العملية: تبقى حيّةً بعد انتهاء الطلب، وتُهمل
            # إشارةَ المقاطعة التي تصل الأبَ (start_new_session).
            # `--allow-unconfigured` تُقلعها بلا إنفاذ `gateway.mode=local`،
            # فتُولّد رمزاً لحظياً وتتجاهل المحفوظ، فيُرفض كلُّ أمرٍ بعدها:
            #   «unauthorized: gateway token mismatch»
            # فلا تُستعمل إلّا إن لم يكن الوضعُ مضبوطاً بعد.
            _args = [nb, ENTRY, "gateway", "run"]
            try:
                _c, _o, _ = run(["config", "get", "gateway.mode"], timeout=60)
                if not (_c == 0 and "local" in (_o or "")):
                    _args.append("--allow-unconfigured")
            except Exception:
                _args.append("--allow-unconfigured")
            subprocess.Popen(
                _args,
                stdout=_log, stderr=_log, stdin=subprocess.DEVNULL,
                cwd=_ROOT, env=engine_env(), start_new_session=True)
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:160]}"
        _t0 = time.time()
        _say("… البوّابةُ تُقلع (حتى %d ث)" % wait)
        _beat = 0.0
        while time.time() - _t0 < wait:
            _el = time.time() - _t0
            if _el - _beat >= 15:
                _beat = _el
                _say("  … %d ث" % int(_el))
            if gateway_health():
                _say("✓ أقلعت في %.1f ث" % _el)
                # إقلاعةٌ جديدة ⟶ تُضمَن صلاحيةُ البحث مرّةً واحدة. والبوّابةُ
                # تحمل بيئتَها من لحظة إقلاعها، فهذا أوانُه الصحيح.
                try:
                    # ضبطُ النموذج أوّلاً: بلا `agents.defaults.model.primary`
                    # يسقط المحرّكُ إلى `openai/gpt-5.6-sol` فتفشل كلُّ نوبة.
                    _say("… بذرُ مساحة العمل (ملفّاتُ التمهيد)")
                    ensure_workspace(say=_say)
                    _say("… كتابةُ إعدادِ التشغيل (كتابةٌ واحدة)")
                    configure_runtime()
                    _say("… كتابةُ النموذجِ والمفتاح")
                    configure_model()
                    _say("✓ الإعدادُ مكتوب")
                except Exception as _e:
                    _say("⚠ تعذّرت كتابةُ الإعداد: " + str(_e)[:120])
                try:
                    # ولا يُمَسُّ اختيارٌ صريحٌ للمستخدم بحال: لو اختار
                    # مزوّداً بمعالج `configure --section web` ثمّ فشل نداءٌ
                    # واحدٌ لانقطاعِ شبكةٍ عابر، لكان تلقائيُّنا يدوس اختيارَه
                    # بلا أن يخبره. فالتلقائيُّ لمن لم يختر فقط.
                    if not chosen_provider():
                        _st = probe_search("اختبار")
                        if not _st.get("ok"):
                            run(["config", "set",
                                 "tools.web.search.enabled", "true"],
                                timeout=60)
                            run(["config", "set",
                                 "tools.web.search.provider",
                                 WEB_SEARCH_FREE[0]], timeout=60)
                except Exception:
                    pass
                return True, f"أقلعت في {time.time() - _t0:.1f} ث"
            time.sleep(1)
        # ولا يُقال «انظر السجلّ» ويُترك المستخدمُ يبحث: يُقرأ السببُ منه.
        return False, (f"لم تسمع خلال {wait} ث"
                       + (" — " + _log_reason()) if _log_reason()
                       else f"لم تسمع خلال {wait} ث — انظر {GATEWAY_LOG}")


def _gateway_pids():
    """أرقامُ عمليّاتِ البوّابة الحيّة — بالقفلِ وبالاسمِ معاً.

    القفلُ وحده لا يكفي: قيس أنّه يقول `pid 1688` والعمليةُ الحيّةُ `2712`،
    فإطفاءٌ بالقفلِ يقتل ميتاً ويترك الحيّ. والعمليةُ تُعيد تسميةَ نفسِها
    `openclaw-gateway`، فيُبحَث بالاسم أيضاً. وتُستثنى عمليتُنا."""
    out, me = [], os.getpid()
    d = _gateway_lock()
    pid = d.get("pid")
    if isinstance(pid, int) and pid > 1 and pid != me:
        try:
            os.kill(pid, 0)          # أحيّةٌ؟ لا تُقتل
            out.append(pid)
        except Exception:
            pass
    try:
        ps = subprocess.run(["ps", "-eo", "pid=,comm="], capture_output=True,
                            text=True, timeout=30)
        for ln in (ps.stdout or "").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            _p, _, _c = ln.partition(" ")
            # `comm` مقطوعٌ عند ١٥ حرفاً في لينكس، فاسمُ العملية يصل
            # «openclaw-gatewa» — بلا الياء والهاء. مقيسٌ لا مُخمَّن:
            #   $ ps -eo pid=,comm=  ⟶  2712 openclaw-gatewa
            # فكانت مطابقتي تطلب «gateway» كاملةً فلا تجد شيئاً، ويبقى
            # الحيُّ يعمل بينما أقتل ما في القفلِ الميت.
            _cl = _c.lower()
            if "openclaw" not in _cl or "gatew" not in _cl:
                continue
            try:
                n = int(_p)
            except ValueError:
                continue
            if n != me and n not in out:
                out.append(n)
    except Exception:
        pass
    return out


def gateway_stop():
    """أطفئ البوّابة — كلَّ عمليّاتها، لا ما يقوله قفلٌ قد يكون بائتاً.

    ولا `gateway stop`: هي إدارةُ خدمةٍ (systemd/launchd)، وترفض أصلاً حين
    يكون `OPENCLAW_STATE_DIR` غيرَ الافتراضيّ — وهو حالُنا دائماً:
        «service management skipped: non-default state dir or config path»

    ولا `pkill -f`: نمطُها يُطابق سطرَ الأوامر كاملاً — بما فيه سطرُ `pkill`
    نفسِه — فتقتل الصَّدفةَ التي تُشغّلها. مقيسٌ: جرّبتُها فقتلت جلستي.

    وإطفاءٌ بإشارةٍ لطيفة (SIGTERM) كي تُنظّف قفلَها بنفسها."""
    pids = _gateway_pids()
    if not pids:
        return (not gateway_health()), "لم تكن تعمل"
    for n in pids:
        try:
            os.kill(n, signal.SIGTERM)
        except Exception:
            pass
    _t0 = time.time()
    while time.time() - _t0 < 25:
        if not gateway_health():
            return True, f"أُطفئت ({len(pids)} عملية) في {time.time()-_t0:.1f} ث"
        time.sleep(1)
    # عنيدةٌ: إشارةٌ حاسمة، ثمّ يُنظَّف القفلُ البائتُ كي لا يمنع الإقلاع
    for n in _gateway_pids():
        try:
            os.kill(n, signal.SIGKILL)
        except Exception:
            pass
    time.sleep(2)
    return (not gateway_health()), "أُطفئت قسراً" if not gateway_health() \
        else "لم تستجب"


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
# مأخوذةٌ من توثيق الحزمة نفسِها: docs/tools/web.md و docs/tools/*-search.md
#
#   • perplexity — يقرأ OPENROUTER_API_KEY، ورتبتُه ٥٠ في الاكتشاف التلقائيّ
#   • parallel   — وفيه مزوّدان: `parallel` مدفوع، و`parallel-free` بلا مفتاح
#                  «dense excerpts ranked for LLM context» (docs/tools/web.md)
#   • duckduckgo — بلا مفتاح أيضاً، لكنّ توثيقَه يحذّر:
#                  «experimental, unofficial … scrapes DuckDuckGo's
#                   non-JavaScript HTML search pages … Bot-challenge risk»
WEB_SEARCH_PLUGINS = ("perplexity", "parallel", "duckduckgo")

# ترتيبُ الاحتياط حين يفشل المدفوع أو لا يوجد مفتاح. وهو ترتيبُ التوثيق:
# parallel-free أوّلاً (واجهةٌ رسميّةٌ مرتّبةٌ للنموذج)، ثمّ duckduckgo
# (كاشطُ HTML تجريبيّ). والتوثيق نفسُه يقول إنّ المجّانيَّ **لا يُكتشَف
# تلقائياً أبداً**: «Key-free providers … never win auto-detection … used
# only when you select them explicitly with tools.web.search.provider».
WEB_SEARCH_FREE = ("parallel-free", "duckduckgo")
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
    # التوثيقُ يشترطها بعد كلِّ تركيب، وكنتُ أُغفلها:
    #   docs/tools/duckduckgo-search.md
    #     openclaw plugins install @openclaw/duckduckgo-plugin
    #     openclaw gateway restart          ← هذه
    # والبوّابةُ تُحمّل الإضافاتِ عند إقلاعها، فما رُكّب بعدها لا تعرفه.
    if gateway_health():
        gateway_stop()
        _ok, _why = gateway_start()
        rows.append(("إعادةُ تشغيل البوّابة (شرطُ التوثيق بعد التركيب)",
                     _ok, "" if _ok else str(_why)[:160]))
    code, out, err = run(["config", "set", WEB_SEARCH_KEY, "true"], timeout=90)
    rows.append((WEB_SEARCH_KEY, code == 0,
                 _real_error(err) or (err or "").strip()[:160]))

    # ── وضمانُ مزوّدٍ صالح ────────────────────────────────────────────────
    #
    # التركيبُ وحده لا يكفي. المحرّكُ يختار المزوّدَ **بإشارةِ اعتماد** —
    # أي بمفتاحٍ موجود:
    #     runtime-CFtRzJUE.mjs:101  resolveWebSearchProviderId
    #     └─ hasImplicitProviderSelectionSignal(provider, …)
    # وduckduckgo بلا مفتاح، فلا إشارةَ له، فلا يُكتشَف تلقائياً أبداً مهما
    # رُكّب. مقيسٌ بدوالّ المحرّك: chosen="" و usable=false.
    #
    # فإن لم يُحَلّ مزوّدٌ — لا من مفتاحك ولا من تعيينٍ سابق — يُعيَّن
    # duckduckgo صراحةً، فيعمل البحثُ بلا مفتاحٍ ولا سؤال. وإن كان مفتاحُك
    # موجوداً فُضِّل مزوّدُه (perplexity برتبة ٥٠ قبل ddg برتبة ١٠٠) ولا
    # نلمس شيئاً.
    st = probe_search("اختبار")
    _mine = chosen_provider()
    if _mine and st.get("ok"):
        rows.append(("اختيارُك محفوظ: " + _mine, True, ""))
        return rows
    if _mine and not st.get("ok"):
        # اختيارُه قائمٌ لكنّه لا يعمل: يُقال له، ولا يُبدَّل من ورائه.
        rows.append(("اختيارُك (" + _mine + ") لا يعمل الآن", False,
                     (st.get("error") or "")[:160]
                     + "  ·  للتبديل: --web-search choose"))
        return rows
    if not st.get("chosen") or not st.get("ok"):
        # وحُلولُ المزوّدِ لا يكفي: قد يُحَلّ ثمّ يفشل. مقيسٌ على جهاز
        # المستخدم — perplexity حُلّ من مفتاح OpenRouter ثمّ ردّ:
        #   402 weight_exceeds_budget: "This request's maximum cost exceeds
        #        your available credits."
        # فالمزوّدُ المدفوعُ يُحجز له أقصى كلفةٍ مقدّماً، ورصيدُه لا يحتمل.
        # وduckduckgo مجّانيٌّ بلا مفتاح، فهو الأمانُ حين يفشل المدفوع.
        _why = st.get("error", "")
        for _free in WEB_SEARCH_FREE:
            if st.get("chosen") == _free and st.get("ok"):
                break
            code2, _o2, err2 = run(["config", "set",
                                    "tools.web.search.provider", _free],
                                   timeout=90)
            rows.append(("tools.web.search.provider = " + _free, code2 == 0,
                         _real_error(err2)
                         or (("السابقُ فشل: " + _why[:100]) if _why
                             else "لا مفتاحَ يُكتشَف — عُيِّن صراحةً")))
            st = probe_search("اختبار")
            if st.get("ok"):
                break
            _why = st.get("error", "")
    rows.append(("المزوّدُ المختار: " + (st.get("chosen") or "لا شيء"),
                 bool(st.get("ok")), st.get("error", "")))
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


def ask(text, timeout=None, cwd=None, fallback=True, session=None):
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
        # قبل أيِّ نوبة: مساحةُ العمل مبذورة. وإلّا مات التمهيدُ بـEACCES
        # على `link()` فلم يُنادَ النموذجُ أصلاً (التعليلُ عند `seed_workspace`).
        # وكلفتُها حين لا تلزم: فحصُ وجودِ ملفٍّ واحد.
        ensure_workspace()
        # منصّتُك كما هي الآن في config/.env — تُكتب في المحرّك إن تغيّرت
        # (مفتاحٌ جديد، منصّةٌ أخرى، نموذجٌ آخر). وإن لم تتغيّر: قراءةُ ملفّ.
        model_sync()
        # المهلةُ من المحرّك لا من عندنا — `agent_deadline()` وتعليلُها فوق.
        # وساعةُ الحائط عندنا أوسعُ من مهلته بفسحةٍ، وإلّا قتلناه قبل أن
        # يبلغ مهلتَه هو.
        #
        # و`timeout=None` تعني «مهلةَ المحرّك» — وهي الحالُ الافتراضيّة.
        # ومن نادى بمهلةٍ صريحةٍ فهي ساعتُه، فتُحترم ولا تُرفَع فوقها: كان
        # الافتراضيُّ ٣٠٠ فصار ٦٩٠ صامتاً، فعلّق فحصٌ كان ينتهي في دقائق.
        if timeout is None:
            _deadline = agent_deadline()
            _wall = _deadline + _AGENT_GRACE
        else:
            try:
                _wall = max(60, int(timeout))
            except Exception:
                _wall = agent_deadline() + _AGENT_GRACE
            _deadline = max(30, _wall - _AGENT_GRACE)
        _to = str(_deadline)
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
        code, out, err = run(args, timeout=_wall, cwd=cwd)
        if code == 0 and out.strip():
            return {"answer": _from_envelope(out), "engine": "weaver-core",
                    "note": ""}
        if not fallback:
            # كان يُعاد الخرجُ خاماً هنا — بألوانه وضجيجه — فتظهر بطاقةُ
            # الفشل في الويب هكذا:
            #   [31m[sqlite/transaction][39m … The CLI command failed. Re…
            # عنوانٌ بلا سبب. فيُنقّى كما يُنقّى في المسار الآخر سواءً.
            return {"answer": "", "engine": "weaver-core",
                    "note": (_real_error(err) or _real_error(out)
                             or "المحرّك لم يُجب بلا سببٍ معلوم")[:400]}
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


# ── مسارُ النوبة: ما فعله الوكيلُ فعلاً ────────────────────────────────────
#
# مُغلَّفُ `--json` يحمل الجوابَ فقط: `final` و`payloads` و`model`. أمّا ما
# استدعاه الوكيلُ من أدواتٍ في الطريق فلا يظهر فيه — ولهذا لم يكن المستخدمُ
# يرى إلّا «التفكير» بينما الوكيلُ يبحث ويكتب.
#
# وللمحرّك سجلٌّ لذلك، وأمرُه هو:
#     sessions export-trajectory --session-key <key> --json
# يُخرج `events.jsonl` فيه أحداثُ النوبة، ومنها أنواعُ الأدوات كما يسمّيها:
#     tool.call · tool.result · tool.execution.started/completed/error · session.tool
#
# ويُصدَّر إلى مجلّدنا (`--workspace`) لا إلى مستودعك، فلا يُلوَّث بشيء.
TRAJ_DIR = os.path.join(STATE, "trajectory")


def session_key(session, agent="main"):
    """مفتاحُ الجلسة كما يخزّنه المحرّك: agent:<id>:explicit:<session-id>.

    مقروءٌ من خرج `sessions list --json` على جلسةٍ حقيقيّة:
        "key": "agent:main:explicit:weaver-chat-42"
    """
    return "agent:%s:explicit:%s" % (agent, _session_id(session))


def _tool_events(obj):
    """التقط استدعاءاتِ الأدوات من حدثٍ واحدٍ في `events.jsonl`.

    مكتوبةٌ متسامحةً عمداً: تُفتَّش عدّةُ أشكالٍ محتملة، لأنّ الشكلَ الدقيقَ
    لحدثِ الأداة لم أره بعينـي (لا مفتاحَ نموذجٍ في بيئتي)، وإنّما أخذتُ
    أسماءَ الأنواع من المحرّك نفسِه. فما لا يُطابق يُترك ولا يُختلق."""
    out = []
    if not isinstance(obj, dict):
        return out
    typ = str(obj.get("type") or "")
    data = obj.get("data") if isinstance(obj.get("data"), dict) else {}

    def _add(name, req, res, status):
        name = str(name or "").strip()
        if not name:
            return
        out.append({"name": name, "request": req, "response": res,
                    "status": status})

    # ① حدثٌ نوعُه أداة
    if "tool" in typ.lower():
        nm = (data.get("toolName") or data.get("name") or data.get("tool")
              or obj.get("toolName") or obj.get("name") or "")
        req = (data.get("input") if data.get("input") is not None
               else data.get("arguments") if data.get("arguments") is not None
               else data.get("args"))
        res = (data.get("output") if data.get("output") is not None
               else data.get("result") if data.get("result") is not None
               else data.get("content"))
        st = "err" if ("error" in typ.lower() or data.get("isError")) else "ok"
        _add(nm, req, res, st)

    # ② مدخلةُ نصٍّ فيها محتوىً بأجزاء، وفيها toolCall/toolResult
    for item in (data.get("content") or obj.get("content") or []):
        if not isinstance(item, dict):
            continue
        it = str(item.get("type") or "")
        if it in ("toolCall", "tool_call", "tool_use"):
            _add(item.get("name") or item.get("toolName"),
                 item.get("input") if item.get("input") is not None
                 else item.get("arguments"), None, "ok")
        elif it in ("toolResult", "tool_result"):
            # نتيجةٌ تُلحَق بآخرِ نداءٍ بلا نتيجة
            for prev in reversed(out):
                if prev["response"] is None:
                    prev["response"] = (item.get("output")
                                        if item.get("output") is not None
                                        else item.get("content"))
                    if item.get("isError"):
                        prev["status"] = "err"
                    break
    return out


def trajectory(session, agent="main", timeout=90):
    """استدعاءاتُ الأدوات في نوبةِ هذه الجلسة. قائمةٌ (قد تكون فارغة).

    لا ترفع استثناءً، ولا تُبطئ الجواب: تُنادى **بعد** أن يُسلَّم الردّ."""
    try:
        os.makedirs(TRAJ_DIR, exist_ok=True)
        code, out, err = run(["sessions", "export-trajectory",
                              "--session-key", session_key(session, agent),
                              "--json", "--workspace", TRAJ_DIR],
                             timeout=timeout)
        if code != 0 or not out.strip():
            return []
        import json as _j
        d = _j.loads(out[out.find("{"):out.rfind("}") + 1])
        if not isinstance(d, dict) or d.get("ok") is False:
            return []
        ev = os.path.join(d.get("outputDir") or "", "events.jsonl")
        if not os.path.isfile(ev):
            return []
        calls = []
        with open(ev, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    calls.extend(_tool_events(_j.loads(line)))
                except Exception:
                    continue
        return calls
    except Exception:
        return []


PROBE_SEARCH = os.path.join(_ROOT, "engines", "weaver-core", "probe_search.mjs")
PROBE_TOOLS = os.path.join(_ROOT, "engines", "weaver-core", "probe_tools.mjs")
SEED_WS = os.path.join(_ROOT, "engines", "weaver-core", "seed_workspace.mjs")
PROBE_BOOT = os.path.join(_ROOT, "engines", "weaver-core",
                          "probe_bootstrap.mjs")
PROBE_EXEC = os.path.join(_ROOT, "engines", "weaver-core",
                          "probe_exec.mjs")
SOUL_SRC = os.path.join(_ROOT, "capabilities", "prompts", "soul",
                        "SOUL.weaver.md")
SKILLS_SRC = os.path.join(_ROOT, "capabilities", "prompts", "skills")


def run_tty(args, timeout=None):
    """نادِ المحرّكَ **بطرفيّةٍ موروثة** — لا يُلتقط خرجُه ولا دخلُه.

    `run()` العاديّةُ تلتقط الخرج (`capture_output=True`)، وذلك يقتل TTY.
    ومعالجُ الإعداد عند المحرّك يشترطها صراحةً، وهذا نصُّه حين تغيب:
        «Interactive configuration requires an interactive terminal (TTY).»
        docs/cli/configure.md:40

    فهذه تُمرّر الطرفيّةَ كما هي، فيرسم المحرّكُ قائمتَه ويقرأ اختيارَك.
    تعيد رمزَ الخروج."""
    if not (available() and node_bin()):
        print(why_unavailable(), file=sys.stderr)
        return 127
    try:
        return subprocess.call([node_bin(), ENTRY] + list(args or []),
                               cwd=_ROOT, env=engine_env(), timeout=timeout)
    except Exception as e:
        print(f"{type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        return 1


# ── التهيئة الكاملة: أمرُ أوبن كلاو نفسُه ────────────────────────────────
#
# «openclaw onboard — Guided setup for auth, models, Gateway, workspace,
#  channels, and skills»
#
# أمرٌ واحدٌ يفعل كلَّ ما كنتُ أبنيه قطعةً قطعة. وما يكتبه — مقيسٌ على
# تشغيلةٍ حقيقيّةٍ في مجلّدٍ معزول:
#
#   auth.profiles.<مزوّد>:default.{provider,mode}   ← نظامُ اعتمادِه هو
#   agents.defaults.model.primary                   ← النموذج
#   agents.defaults.models.<ref>.alias              ← اسمٌ مقروء
#   agents.entries.main.{name,workspace,agentDir,identity}
#   plugins.entries.<مزوّد>.enabled = true
#   gateway.{mode,auth.mode,auth.token,port,bind}
#   tools.profile = coding
#   skills.install.nodeManager = npm
#   wizard.lastRun*                                 ← فلا يُعاد بلا داع
#
# وكنتُ أكتب المفتاحَ في `env.vars` — تعمل، لكنّها ليست معماريّتَه.
# معماريّتُه `auth.profiles`.
#
# وأسماءُ الاختيار والأعلام مقروءةٌ من `onboard --help` لا مُخمَّنة.
PROBE_AUTH = os.path.join(_ROOT, "engines", "weaver-core", "probe_auth.mjs")


_AUTH_CACHE = {"rows": None}


def auth_catalog(refresh=False):
    """كتالوجُ مزوّدي الاعتماد — من المحرّك، لا من قائمةٍ عندنا.

    المحرّكُ يبنيها من بيانات إضافاته:
        auth-choice-options-tnlfLecZ.mjs → buildAuthChoiceGroups
    فمن رُكّبت إضافتُه ظهر، ومن جاء بترقيةٍ ظهر — بلا أن نلمس سطراً.
    مقيس: ٨٣ خياراً لـ٥٧ مزوّداً، مقابل ١٤ كنتُ أكتبها يدوياً.

    يعيد [{choice,label,providerId,group,hint}] أو []."""
    # يُقلع node في كلِّ نداء (~٢ ث)، و`auth_choice` و`key_env_name` تُناديانه
    # مراراً. فيُقرأ مرّةً ويُحفَظ في الذاكرة — والكتالوجُ لا يتغيّر إلّا
    # بتركيب إضافةٍ أو ترقيةٍ، وعندها `--providers refresh`.
    if _AUTH_CACHE["rows"] is not None and not refresh:
        return _AUTH_CACHE["rows"]
    nb = node_bin()
    if not (nb and os.path.isfile(PROBE_AUTH)):
        return []
    try:
        # بيئةٌ بلا اعتماد: `engine_env()` تنادي `credentials()` التي تنادي
        # `key_env_name()` التي تنادي هذه الدالّة — دورةٌ لا تنتهي، أدخلتُها
        # للتوّ وكشفها تعليقُ الأمر. وقراءةُ الكتالوج لا تحتاج مفتاحاً أصلاً.
        _e = engine_env(no_credentials=True)
        p = subprocess.run([nb, PROBE_AUTH], capture_output=True, text=True,
                           timeout=180, cwd=_ROOT, env=_e)
        out = (p.stdout or "").strip()
        i, j = out.find("["), out.rfind("]")
        if i < 0 or j < i:
            return []
        import json as _j
        d = _j.loads(out[i:j + 1])
        _AUTH_CACHE["rows"] = d if isinstance(d, list) else []
        return _AUTH_CACHE["rows"]
    except Exception:
        return []


def auth_choice(provider=None):
    """خيارُ الاعتماد الذي يناسب مزوّدَك — بسؤال المحرّك أوّلاً.

    الترتيب: كتالوجُ المحرّك (وفيه ٥٧ مزوّداً) ثمّ الخريطةُ اليدويّةُ
    احتياطاً حين يتعذّر النداء. ويُفضَّل ما كان بمفتاحٍ (`*-api-key`) لأنّه
    ما نملكه — لا OAuth الذي يحتاج متصفّحاً."""
    prov = (provider or provider_id() or "").lower()
    if not prov:
        return ""
    rows = [r for r in auth_catalog()
            if str(r.get("providerId", "")).lower() == prov]
    if rows:
        keyed = [r for r in rows if "api-key" in str(r.get("choice", ""))
                 or str(r.get("choice", "")) == "apiKey"]
        pick = (keyed or rows)[0]
        return str(pick.get("choice") or "")
    return _AUTH_CHOICE.get(prov, "")


def auth_flag(choice):
    """عَلَمُ سطر الأوامر لخيارِ اعتماد: `--<choice>` — كما في `onboard --help`.

    مقيس: `openrouter-api-key` ⟶ `--openrouter-api-key`، و`apiKey`
    (أنثروبيك) ⟶ `--anthropic-api-key` لأنّ الخيارَ عامٌّ والعَلَمَ باسم
    المزوّد."""
    c = str(choice or "")
    if not c:
        return ""
    if c in ("apiKey", "token", "setup-token"):
        return ""          # عامٌّ: يحتاج --token-provider، لا عَلَماً باسمه
    return "--" + c


# خريطةٌ احتياطيّةٌ صغيرة — تُستعمل فقط حين يتعذّر نداءُ المحرّك.
_AUTH_CHOICE = {
    "openrouter": "openrouter-api-key", "deepseek": "deepseek-api-key",
    "openai": "openai-api-key", "anthropic": "anthropic-api-key",
    "groq": "groq-api-key", "mistral": "mistral-api-key",
    "google": "gemini-api-key", "xai": "xai-api-key",
    "cerebras": "cerebras-api-key", "together": "together-api-key",
    "fireworks": "fireworks-api-key", "kimi": "moonshot-api-key",
    "minimax": "minimax-api-key", "zai": "zai-api-key",
}


def onboarded():
    """أسبق أن جرى المعالجُ الكامل؟ (`wizard.lastRunAt` يكتبه هو)"""
    try:
        code, out, _ = run(["config", "get", "wizard.lastRunAt"], timeout=60)
        return code == 0 and len((out or "").strip().strip('"')) > 8
    except Exception:
        return False


def onboard(force=False):
    """شغّل تهيئةَ أوبن كلاو الكاملة بمفتاحك — بلا أسئلة.

    `--non-interactive` يشترط `--accept-risk` (يقوله الأمرُ نفسُه: «required
    for --non-interactive»). و`--skip-daemon` لأنّ تثبيتَ الخدمة يحتاج
    systemd/launchd ولا وجودَ لهما على Termux — والبوّابةُ نُديرها نحن.

    يعيد (نجح، سبب). لا يرفع استثناءً."""
    prov = provider_id()
    key = _setting("WEAVER_API_KEY")
    choice = auth_choice(prov)
    flag = auth_flag(choice)
    if not (prov and key):
        return False, "لا مزوّدَ/مفتاحَ في config/.env"
    if not (choice and flag):
        _known = sorted({r.get("providerId") for r in auth_catalog()
                         if r.get("providerId")})
        return False, ("مزوّدٌ لا يعرفه المحرّك: " + prov
                       + ("  ·  يعرف " + str(len(_known)) + " مزوّداً"
                          if _known else ""))
    if onboarded() and not force:
        return True, "سبق أن جرى (wizard.lastRunAt)"
    args = ["onboard", "--non-interactive", "--accept-risk",
            "--auth-choice", choice, flag, key,
            "--gateway-port", str(OUR_PORT),
            "--skip-channels", "--skip-daemon", "--skip-health",
            "--skip-hooks", "--no-install-daemon"]
    code, out, err = run(args, timeout=600)
    if code != 0:
        return False, _real_error(err) or _real_error(out) or "تعذّرت التهيئة"
    return True, "تمّت"


def model_ref():
    """مرجعُ النموذج كما يكتبه المحرّك: `<مزوّد>/<نموذج>`.

    docs/providers/openrouter.md: «Model refs follow the pattern
    `openrouter/<provider>/<model>`». فنموذجُك `deepseek/deepseek-v4-flash`
    على OpenRouter يصير `openrouter/deepseek/deepseek-v4-flash`."""
    _r = engine_route()
    if _r.get("mode") in ("custom", "bundled"):
        return _r.get("ref", "")
    prov, m = provider_id(), _setting("WEAVER_MODEL")
    if not (prov and m):
        return ""
    return m if m.startswith(prov + "/") else prov + "/" + m


# ── أيُّ منصّةٍ وأيُّ نموذج: كما يفعلها المحرّكُ نفسُه ─────────────────────
#
# العطبُ الذي رآه المستخدمُ بعد تغيير مفتاحه:
#
#     Unknown model: deepseek/deepseek-v4-pro
#
# والمحرّكُ يكتبها `Unknown model: ${provider}/${modelId}`
# (embedded-agent-CE9KzQvy.mjs:5479) — أي أنّه طُلب منه مزوّدٌ اسمُه
# `deepseek`، وليس في المحرّك مزوّدٌ بهذا الاسم. المزوّداتُ المدمجةُ فيه هي ما
# في `dist/extensions/*/openclaw.plugin.json` تحت `providers` — عشرون: منها
# openrouter وopenai وanthropic وgoogle وxai. أمّا deepseek وgroq وmistral
# وغيرُها فـ«مزوّداتٌ خارجيّة» تحتاج تركيبَ حزمة
# (official-external-provider-catalog: `@openclaw/deepseek-provider`).
# وكانت خريطتُنا `_PROVIDER_ENV` تعِد بأربعةَ عشرَ، نصفُها غيرُ مركَّب.
#
# والمحرّكُ نفسُه يحلّها بلا إضافة: **المزوّدُ المخصَّص**.
# docs/gateway/config-tools/custom-providers.md:
#
#     models.providers.<id> = { baseUrl, apiKey, api: "openai-completions",
#                               models: [{ id }] }
#
# وهو ما يكتبه معالجُه لمن اختار «Custom Provider»
# (onboard-custom-config-CeY5_6A1.mjs  applyCustomApiConfig) — فنكتب مثله:
#
#   ١) منصّةٌ لها مزوّدٌ مدمج، ورابطُك رابطُها  ⟶ كما كان حرفاً (لا يتغيّر
#      شيءٌ ممّا يعمل؛ وOpenRouter منها، وله معالجاتٌ خاصّةٌ لـDeepSeek V4).
#   ٢) أيُّ منصّةٍ أخرى برابطٍ ومفتاح         ⟶ مزوّدٌ مخصَّصٌ اسمُه `weaver`
#      يحمل رابطَك ونموذجَك، والمفتاحُ `${WEAVER_PLATFORM_API_KEY}` من
#      `env.vars` — فلا يُكتب في موضعين.
#
# مقيسٌ على خادمٍ وهميٍّ متوافقٍ مع OpenAI، عبر المحرّك نفسِه:
#   قبل:  «Unknown model: deepseek/deepseek-v4-pro»  (نفسُ ما رآه المستخدم)
#   بعد:  وصل الطلبُ إلى الرابط بـ`Bearer …ABCD` و١٤ أداة، وجاء الجواب.
#   ونموذجٌ غيرُ مُدرَجٍ في `models` (`weaver/any-model-x`) قُبِل أيضاً —
#   فتغييرُ النموذج من الواجهة لا يحتاج إعادةَ ضبط.
CUSTOM_PROVIDER = "weaver"
CUSTOM_KEY_ENV = "WEAVER_PLATFORM_API_KEY"
_BUNDLED = {"map": None}
_MODEL_APPLIED = os.path.join(STATE, "model.applied.json")


def _host(url):
    """اسمُ المضيف من رابط، بأحرفٍ صغيرة — أو ""."""
    try:
        from urllib.parse import urlparse
        return (urlparse(str(url or "").strip()).hostname or "").lower()
    except Exception:
        return ""


def bundled_providers(refresh=False):
    """{مزوّد: {hosts, suffixes}} — المزوّداتُ المدمجةُ في المحرّك فعلاً.

    تُقرأ من بيانات الإضافات نفسِها (`openclaw.plugin.json`)، لا من قائمةٍ
    عندنا: `providers` والمضيفاتُ من `providerEndpoints` ومن روابطِ
    `modelCatalog`. قراءةُ ملفّات، بلا node. لا يرفع استثناءً."""
    if _BUNDLED["map"] is not None and not refresh:
        return _BUNDLED["map"]
    out = {}
    import json as _j
    base = os.path.join(RUNTIME, "dist", "extensions")
    try:
        names = sorted(os.listdir(base))
    except Exception:
        names = []
    for d in names:
        try:
            with open(os.path.join(base, d, "openclaw.plugin.json"),
                      encoding="utf-8") as fh:
                man = _j.load(fh)
        except Exception:
            continue
        pids = [str(p).lower() for p in (man.get("providers") or []) if p]
        if not pids:
            continue
        hosts, suffixes = set(), []
        for ep in man.get("providerEndpoints") or []:
            for h in ep.get("hosts") or []:
                hosts.add(str(h).lower())
            for s in ep.get("hostSuffixes") or []:
                suffixes.append(str(s).lower())
            for u in ep.get("baseUrls") or []:
                if _host(u):
                    hosts.add(_host(u))
        cat = ((man.get("modelCatalog") or {}).get("providers") or {})
        for _k, v in cat.items():
            if isinstance(v, dict) and _host(v.get("baseUrl")):
                hosts.add(_host(v.get("baseUrl")))
        for p in pids:
            e = out.setdefault(p, {"hosts": set(), "suffixes": []})
            e["hosts"] |= hosts
            e["suffixes"] += suffixes
    _BUNDLED["map"] = out
    return out


def _bundled_owns(pid, host):
    """أهذا المضيفُ لهذا المزوّد المدمج؟ (بلا مضيفٍ = نعم: رابطُه الافتراضيّ)"""
    if not host:
        return True
    e = bundled_providers().get(pid) or {}
    if host in e.get("hosts", ()):
        return True
    if any(host == s.lstrip(".") or host.endswith(s if s.startswith(".")
                                                  else "." + s)
           for s in e.get("suffixes", ())):
        return True
    # مزوّدٌ أعلن مضيفاتِه ⟶ هي وحدها له. فـ`openai.proxy.example` ليس
    # openai. والاسمُ داخل المضيف دليلٌ فقط لمن لم يُعلن شيئاً.
    if e.get("hosts") or e.get("suffixes"):
        return False
    return pid in host


def _custom_api(base):
    """محوِّلُ الطلب لمنصّةٍ مخصَّصة — كما يختاره معالجُ المحرّك.

    `openai-completions` لكلِّ متوافقٍ مع OpenAI (وهو افتراضُ المحرّك لمزوّدٍ
    مخصَّصٍ بلا `api`)، و`anthropic-messages` لرابطٍ متوافقٍ مع أنثروبيك.
    و`WEAVER_ENGINE_API` تفرض غيرَه لمن احتاج."""
    forced = (os.environ.get("WEAVER_ENGINE_API", "") or "").strip()
    if forced:
        return forced
    b = str(base or "").lower().rstrip("/")
    if "anthropic" in _host(b) or b.endswith("/anthropic") \
            or "/anthropic/" in b:
        return "anthropic-messages"
    return "openai-completions"


def engine_route():
    """كيف يصل المحرّكُ إلى منصّتك. لا يرفع استثناءً، ولا يُقلع node.

    يعيد {mode, provider, model, ref, base_url, api, why}:
      mode = "bundled"  مزوّدٌ مدمجٌ في المحرّك يملك رابطَك
             "custom"   أيُّ منصّةٍ أخرى: تُسجَّل مزوّداً مخصَّصاً `weaver`
             ""         لا نموذجَ، أو لا مزوّدَ ولا رابط

    و`WEAVER_ENGINE_ROUTE=custom|bundled` تفرض أحدَهما."""
    try:
        m = _setting("WEAVER_MODEL")
        base = _setting("WEAVER_BASE_URL").rstrip("/")
        host = _host(base)
        raw = _setting("WEAVER_PROVIDER").lower()
        bmap = bundled_providers()
        cand = raw if raw in bmap else ""
        if not cand and host:
            cand = next((p for p in sorted(bmap)
                         if _bundled_owns(p, host)), "")
        if not cand:
            _p = provider_id()
            cand = _p if _p in bmap else ""
        forced = (os.environ.get("WEAVER_ENGINE_ROUTE", "") or "").strip()
        if not m:
            return {"mode": "", "why": "لا WEAVER_MODEL في config/.env"}
        if forced != "custom" and cand and (
                forced == "bundled" or _bundled_owns(cand, host)):
            return {"mode": "bundled", "provider": cand, "model": m,
                    "ref": m if m.startswith(cand + "/") else cand + "/" + m,
                    "base_url": base, "api": "",
                    "why": "مزوّدٌ مدمجٌ في المحرّك"}
        if base:
            mm = m[len(CUSTOM_PROVIDER) + 1:] \
                if m.startswith(CUSTOM_PROVIDER + "/") else m
            return {"mode": "custom", "provider": CUSTOM_PROVIDER,
                    "model": mm, "ref": CUSTOM_PROVIDER + "/" + mm,
                    "base_url": base, "api": _custom_api(base),
                    "why": ("المنصّةُ «%s» بلا مزوّدٍ مدمج ⟶ مزوّدٌ مخصَّص"
                            % (raw or host or "?"))}
        return {"mode": "", "why": "لا مزوّدَ يعرفه المحرّك ولا WEAVER_BASE_URL"}
    except Exception as e:
        return {"mode": "", "why": "%s: %s" % (type(e).__name__, str(e)[:120])}


def custom_provider_tree(route=None, key_present=True):
    """شجرةُ `models.providers.weaver` — بشكل ما يكتبه معالجُ المحرّك.

    applyCustomApiConfig: `{baseUrl, api, apiKey, models:[{id, name, …}]}`.
    والمفتاحُ إشارةٌ `${WEAVER_PLATFORM_API_KEY}` تُحَلّ من `env.vars`.
    ولغير OpenAI يُرسَل `max_tokens` لا `max_completion_tokens` (مقيس: المحرّكُ
    يرسل الثاني افتراضاً)، لأنّ الأوّلَ ما تفهمه المنصّاتُ المتوافقةُ كلُّها."""
    r = route or engine_route()
    if r.get("mode") != "custom":
        return {}
    mid = r["model"]
    model = {"id": mid, "name": mid + " (Weaver Write)",
             "input": ["text"], "reasoning": False,
             "cost": {"input": 0, "output": 0, "cacheRead": 0,
                      "cacheWrite": 0},
             "contextWindow": 128000}
    try:
        mx = int(_setting("WEAVER_MAX_TOKENS") or 0)
        if mx > 0:
            model["maxTokens"] = mx
    except Exception:
        pass
    if r.get("api") == "openai-completions":
        model["compat"] = {"maxTokensField": "max_tokens"}
    prov = {"baseUrl": r["base_url"], "api": r["api"], "models": [model]}
    if key_present:
        prov["apiKey"] = "${" + CUSTOM_KEY_ENV + "}"
    return {"models": {"mode": "merge",
                       "providers": {CUSTOM_PROVIDER: prov}}}


def _model_fingerprint():
    """بصمةُ ما كُتب في المحرّك: (ما يستلزم إعادةَ إقلاع البوّابة، والنموذج).

    المفتاحُ لا يُحفظ — بصمتُه فقط (sha256)."""
    import hashlib
    r = engine_route()
    key = _setting("WEAVER_API_KEY")
    boot = "|".join([r.get("mode", ""), r.get("provider", ""),
                     r.get("base_url", ""), r.get("api", ""),
                     hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
                     if key else ""])
    return {"boot": boot, "model": r.get("ref", "")}


def _applied_fingerprint():
    try:
        import json as _j
        with open(_MODEL_APPLIED, encoding="utf-8") as fh:
            d = _j.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_fingerprint(fp):
    try:
        import json as _j
        os.makedirs(STATE, exist_ok=True)
        with open(_MODEL_APPLIED, "w", encoding="utf-8") as fh:
            _j.dump(fp, fh)
    except Exception:
        pass


def model_sync(say=None):
    """اجعل المحرّكَ على منصّتك الحاليّة — قبل كلِّ نوبة، بلا كلفةٍ إن لم تتغيّر.

    غيّرتَ المفتاحَ أو المنصّةَ أو النموذجَ من الواجهة ⟶ تُكتب في المحرّك
    كتابةً واحدة. وإن تغيّر ما تحمله البوّابةُ منذ إقلاعها (المفتاحُ في
    بيئتها، والمزوّدُ المخصَّص — «Restart the gateway to apply») أُطفئت،
    فيُقلعها النداءُ التالي على الإعداد الجديد.

    يعيد (تغيّر؟، سبب). لا يرفع استثناءً."""
    try:
        if not available():
            return False, "المحرّك غير مركَّب"
        fp = _model_fingerprint()
        old = _applied_fingerprint()
        if old == fp:
            return False, "لم يتغيّر شيء"
        if not fp["model"]:
            return False, engine_route().get("why", "")
        if say:
            try:
                say("… منصّتُك تغيّرت — كتابتُها في المحرّك")
            except Exception:
                pass
        rows = configure_model()
        if not all(ok for _n, ok, _w in rows):
            # لا يُبتلَع: فشلُ الكتابة يعني أنّ المحرّكَ ما زال على منصّتك
            # القديمة — فيُسجَّل ليظهر في `--last`.
            _why = next((str(w) for _n, ok, w in rows if not ok), "")
            _record_run(["model-sync"], 1, "", _why)
            return False, _why
        if old.get("boot") != fp["boot"] and gateway_health():
            gateway_stop()
        return True, "كُتبت: " + fp["model"]
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:160])


# ── كتابةُ الإعداد: كتابةٌ واحدةٌ لا عشر ──────────────────────────────────
#
# كلُّ `config set` عمليةُ node كاملة: تُحمَّل الحزمةُ، وتُفتح قاعدةُ الحالة،
# ويُقرأ الإعدادُ ويُكتب. على خادمٍ سريعٍ ٥ ثوانٍ، وعلى هاتفٍ أضعافُها.
# وكنّا نكتب عشرةَ مفاتيحَ بعشرِ عمليّات — فذهبت دقائقُ في الصمت، وظنّ
# المستخدمُ أنّ الأمرَ علّق. وهو لم يُعلّق، بل كان يُقلع node عشرَ مرّات.
#
# وللمحرّك آليّتُه لذلك، موثّقةً في دليل أمرِه:
#
#     config patch — «Patch config from a JSON5 object in **one validated
#     write**. Objects merge recursively, arrays/scalars replace, and null
#     deletes a path.»        openclaw config patch --stdin
#
# مقيس: أربعةُ مفاتيحَ في نداءٍ واحدٍ ٥٫٤ ث، مقابل أربع عمليّاتٍ منفصلة.
# وجوابُه: «Applied 4 config update(s). Change will apply without
# restarting the gateway.»
def config_patch(tree, timeout=180, replace_paths=()):
    """اكتب شجرةَ إعدادٍ كاملةً في نداءٍ واحد. يعيد (نجح، سبب).

    `replace_paths`: مساراتٌ تُستبدَل كاملةً بدل الدمج. فالمحرّكُ يرفض
    استبدالَ مصفوفةٍ تُسقط عناصرَ قائمة («Refusing to replace
    models.providers.weaver.models; it would remove existing entries») إلا
    بـ`--replace-path` — وهو خيارُه الموثَّق في `config patch --help`."""
    if not tree:
        return True, "لا شيءَ يُكتب"
    nb = node_bin()
    if not (available() and nb):
        return False, why_unavailable()
    import json as _j
    _rp = []
    for _p in replace_paths or ():
        _rp += ["--replace-path", str(_p)]
    try:
        p = subprocess.run([nb, ENTRY, "config", "patch", "--stdin"] + _rp,
                           input=_j.dumps(tree, ensure_ascii=False),
                           capture_output=True, text=True, timeout=timeout,
                           cwd=_ROOT, env=engine_env())
        _record_run(["config", "patch", "--stdin"], p.returncode,
                    p.stdout or "", p.stderr or "")
        if p.returncode == 0:
            return True, (p.stdout or "").strip().split("\n")[0][:160]
        return False, (_real_error(p.stderr) or _real_error(p.stdout)
                       or "تعذّرت الكتابة")[:200]
    except subprocess.TimeoutExpired:
        return False, "تجاوز المهلة (%d ث)" % timeout
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:160])


def _nest(path, value):
    """`a.b.c`, v  ⟶  {"a": {"b": {"c": v}}} — لتُدمَج في شجرةِ الترقيع."""
    out = value
    for part in reversed(str(path).split(".")):
        out = {part: out}
    return out


def _merge(dst, src):
    """دمجٌ عميق — نفسُ سلوكِ `config patch` (الكائناتُ تُدمج)."""
    for k, v in (src or {}).items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v
    return dst


# ── سياسةُ الأدوات: ٢٤ ألفَ رمزٍ في كلِّ رسالة ────────────────────────────
#
# شكوى المستخدم: «من ٢ إلى ٣ دقائق في الرد على أسئلة سخيفة». والقياسُ
# بدوالّ المحرّك نفسِها على إعداده:
#
#   profile = full     48 أداة   88,195 حرفاً  ≈ 24,499 رمزاً
#   profile = coding   33 أداة   53,379 حرفاً  ≈ 14,828 رمزاً
#   minimal + المطلوب  13 أداة   17,581 حرفاً  ≈  4,884 رمزاً
#
# مخطَّطُ كلِّ أداةٍ يُرسَل كاملاً مع **كلِّ** رسالة. فسؤالٌ من أربع كلمات
# يرفع ٨٨ كيلوبايت من هاتفٍ قبل أن يبدأ النموذجُ التفكير. وأوبن كلاو يقولها
# بنفسه في docs/tools/tool-search.md:
#
#   «Large catalogs are useful but expensive. Sending every tool schema to
#    the model makes the request larger, slows planning, and increases
#    accidental tool selection.»
#
# وآليّتُه لذلك موثّقةٌ في docs/gateway/config-tools/tool-policy.md:
#
#   tools.profile     قاعدةٌ قبل allow/deny: minimal · coding · messaging · full
#   tools.alsoAllow   توسيعُ ملفٍّ محدودٍ بمجموعاتٍ أو أدواتٍ بعينها
#   group:web         web_search · x_search · web_fetch
#   group:fs          read · write · edit · apply_patch
#   group:runtime     exec · process · code_execution
#
# و«full» ليس اختياراً منّا: «Local onboarding sets tools.profile: "full"
# when no profile is configured» — أي أنّه ما كتبه `onboard` تلقائياً.
#
# فيُضبَط على ما يحتاجه نظامُك فعلاً: بحثٌ، وملفّات، وتنفيذ، ومتصفّح،
# وذاكرة. ويُستعاد الكاملُ بكلمةٍ واحدة (`--tools-profile full`) لمن أراد.
TOOLS_LEAN_ALLOW = ("group:web", "group:fs", "group:runtime",
                    "browser", "memory_search", "memory_get")


def tools_policy():
    """(ملفُّ الأدوات، قائمةُ التوسيع) — الرشيقةُ افتراضاً، وتُضبَط بالبيئة.

    `WEAVER_TOOL_PROFILE=full` تُعيد الكاملَ كما كان بلا تعديلِ كود."""
    want = (os.environ.get("WEAVER_TOOL_PROFILE", "") or "lean").strip().lower()
    if want in ("full", "coding", "messaging"):
        return want, []
    return "minimal", list(TOOLS_LEAN_ALLOW)


def configure_model():
    """اكتب نموذجَك ومفتاحَك في إعداد المحرّك — بمفاتيحه هو.

    الجذرُ الذي أتعبَ المستخدم: `models` و`agents` غيرُ مضبوطَين، فيسقط
    المحرّكُ إلى افتراضيّه:
        [gateway] agent model: openai/gpt-5.6-sol
    ولا مفتاحَ لـopenai، فتفشل كلُّ نوبةٍ بـ:
        «No route-compatible authentication source is configured for openai.»

    وكنتُ أمرّر `--model` في كلِّ نداء — رقعةٌ لا ضبط. والضبطُ الصحيحُ
    موثَّقٌ في docs/providers/openrouter.md:

        { env: { vars: { OPENROUTER_API_KEY: "sk-or-…" } },
          agents: { defaults: { model: { primary: "openrouter/…" } } } }

    فيُكتب مرّةً، ويعمّ البوّابةَ وكلَّ نوبة، ولا يحتاج علَماً في كلِّ نداء.

    يعيد قائمةَ (اسم، نجح، سبب). لا يرفع استثناءً."""
    rows = []
    ref = model_ref()
    creds = credentials()
    if not ref:
        rows.append(("نموذجُك", False,
                     "لا WEAVER_MODEL/WEAVER_PROVIDER في config/.env"))
        return rows
    # كتابةٌ واحدة: المفتاحُ يُكتب في `env.vars` كما يوثّقه المحرّك، فتراه
    # البوّابةُ وكلُّ نوبةٍ بلا أن نحقنه في بيئةِ كلِّ نداء.
    tree = {"agents": {"defaults": {"model": {"primary": ref}}}}
    names = ["agents.defaults.model.primary = " + ref]
    _route = engine_route()
    if _route.get("mode") == "custom":
        # أيُّ منصّة: مزوّدٌ مخصَّصٌ في الكتابة نفسِها — فيتحقّق المحرّكُ من
        # `primary` وهو يرى مزوّدَه (مقيس: «Applied 6 config update(s)»).
        _merge(tree, custom_provider_tree(_route, key_present=bool(creds)))
        names.append("models.providers.%s = %s  (%s)" % (
            CUSTOM_PROVIDER, _route.get("base_url", ""), _route.get("api", "")))
    for env_name, key in (creds or {}).items():
        _merge(tree, _nest("env.vars." + env_name, key))
        names.append("env.vars." + env_name + " = ***" + key[-4:])
    # مزوّدُنا يُستبدَل كاملاً: منصّةٌ جديدةٌ لا تَرِث رابطَ السابقة ولا نماذجَها.
    _rep = (["models.providers." + CUSTOM_PROVIDER]
            if _route.get("mode") == "custom" else [])
    # ولا يُمرَّر إلا حين يلزم: فالمدمجُ يُنادى كما كان حرفاً.
    okp, why = (config_patch(tree, replace_paths=_rep) if _rep
                else config_patch(tree))
    for n in names:
        rows.append((n, okp, "" if okp else why))
    if okp:
        _save_fingerprint(_model_fingerprint())
    return rows


def configure_runtime():
    """ضبطُ ما يجب أن يتّفق عليه الإعدادُ والبيئة — لا أن يختلفا.

    عطبٌ كشفه `browser doctor`: `gateway.port` غيرُ مضبوطٍ في الإعداد،
    فالمحرّكُ يشتقُّ منفذاً افتراضياً للبروفايل (٢١٣٤١ عندنا)، بينما بيئتُنا
    تُشغّل البوّابةَ على ١٨٨٨٩. فكلُّ أمرٍ يقرأ الإعدادَ يقصد منفذاً خاوياً:
        FAIL gateway: Gateway not reachable at ws://127.0.0.1:21341
    فيُكتب المنفذُ في الإعداد أيضاً، فيتّفقان.

    والمتصفّحُ: docs/tools/browser/setup.md يشترط **الاثنين معاً**:
        «Defaults need both `plugins.entries.browser.enabled` **and**
         `browser.enabled=true`»
    وهو متصفّحٌ معزولٌ للوكيل، لا متصفّحُك (docs/tools/browser.md)."""
    rows = []
    # رمزُ البوّابة: بلا رمزٍ محفوظٍ تُولّد البوّابةُ رمزاً لحظياً عند كلِّ
    # إقلاع — ويقولها سجلُّها حرفاً:
    #   «auth token was missing. Generated a runtime token for this startup
    #    without changing config; restart will generate a different token.
    #    Persist one with `openclaw config set gateway.auth.token <token>`.»
    # فكلُّ أمرٍ يتّصل بها بعد ذلك يُرفَض:
    #   «unauthorized: device token mismatch»
    # فيُولَّد مرّةً ويُحفَظ. ولا يُطبع.
    _tok_new = ""
    try:
        _c, _o, _ = run(["config", "get", "gateway.auth.token"], timeout=90)
        _tok = (_o or "").strip().strip('"')
        if not _tok or _tok in ("null", "undefined"):
            import secrets as _s
            _tok_new = _s.token_hex(24)     # يُكتب مع البقيّة، لا وحده
    except Exception:
        pass
    _tp, _ta = tools_policy()
    # وكانت هذه ثمانيَ عمليّاتِ node منفصلة — ثمانِ إقلاعاتٍ كاملةٍ للحزمة
    # في صمت. صارت كتابةً واحدةً بآليّة المحرّك نفسِه (`config patch`).
    # والقيمُ هنا أنواعُها الحقيقيّة (عدد · نصّ · منطقيّ) لا نصوصاً، لأنّ
    # الترقيعةَ JSON5 تُتحقَّق من المخطَّط قبل الكتابة.
    spec = (
        # مهلةُ النوبة في إعداد المحرّك نفسِه — وهي «قيمةُ الإعداد» التي
        # يذكرها وصفُ علمه: «default 600 or config value».
        #   builtin-openclaw-B-H-7lKk.mjs:14983
        #     cfg?.agents?.defaults?.timeoutSeconds
        # فلا نعتمد على علمٍ نمرّره في كلِّ نداء، بل على إعدادِه هو —
        # فيصحُّ حتى حين يُنادى المحرّكُ من غير طريقنا.
        ("agents.defaults.timeoutSeconds", agent_deadline(),
         "مهلةُ نوبة الوكيل (ثانية)"),
        ("gateway.port", OUR_PORT, "منفذُ البوّابة"),
        ("gateway.mode", "local", "وضعُ البوّابة"),
        ("gateway.auth.mode", "token", "وضعُ اعتماد البوّابة"),
        ("plugins.entries.browser.enabled", True, "إضافةُ المتصفّح"),
        ("browser.enabled", True, "المتصفّح"),
        # بلا هذا يرفض كروم الإقلاعَ في بيئةٍ محدودة الصلاحيات — وهي
        # حالُ Termux وحالُ الجذر. والمحرّكُ نفسُه يقولها عند الفشل:
        #   «If running in a container or as root, try setting
        #    browser.noSandbox: true»
        ("browser.noSandbox", True, "كروم بلا صندوقٍ رمليّ"),
        # لا يُرسَل شيءٌ عنك إلى الشبكة بلا علمك. مقيس: المحرّكُ حاول
        # بلوغَ telemetry.openclaw.ai في تشغيلةٍ عادية.
        ("telemetry.enabled", False, "التتبّعُ الخارجيّ (مُطفأ)"),
    ) + ((("tools.profile", _tp, "ملفُّ الأدوات"),)
         + ((("tools.alsoAllow", _ta, "توسيعُ الأدوات"),) if _ta else ()))
    tree = {}
    for path, val, _what in spec:
        _merge(tree, _nest(path, val))
    if _tok_new:
        _merge(tree, _nest("gateway.auth.token", _tok_new))
    okp, why = config_patch(tree)
    if _tok_new:
        rows.append(("رمزُ البوّابة — gateway.auth.token (مُولَّدٌ ومحفوظ)",
                     okp, "" if okp else why))
    for path, val, what in spec:
        rows.append((what + " — " + path + " = "
                     + ("true" if val is True else
                        "false" if val is False else
                        ", ".join(val) if isinstance(val, list) else str(val)),
                     okp, "" if okp else why))
    return rows


def chosen_provider():
    """المزوّدُ الذي **عيّنه المستخدمُ صراحةً**، أو "" إن لم يُعيّن.

    فرقٌ جوهريّ: `resolveWebSearchProviderId` قد تُعيد مزوّداً اكتُشف
    تلقائياً من مفتاح، وذاك ليس اختياراً. وهذه تقرأ المفتاحَ المكتوبَ في
    الإعداد — وهو ما يكتبه معالجُ `configure --section web` حين تختار."""
    try:
        code, out, _ = run(["config", "get", "tools.web.search.provider"],
                           timeout=60)
        if code != 0:
            return ""
        v = (out or "").strip().strip('"').strip()
        return "" if v in ("", "null", "undefined", "auto") else v
    except Exception:
        return ""


def configure_web():
    """معالجُ اختيار محرّك البحث — معالجُ أوبن كلاو نفسُه، بلا واسطة.

        docs/cli/configure.md:74
        «openclaw configure --section web picks a web-search provider and
         configures its credentials.»

    يعرض المزوّدين (المجّانيَّ والمدفوع)، ويأخذ المفتاحَ إن لزم، ويكتب
    `tools.web.search.provider`. ونحن لا نعيد بناءَ شيءٍ منه — نناديه.

    والبوّابةُ تُحمّل الإضافاتِ عند إقلاعها، فتُعاد بعده إن كانت حيّة
    (docs/tools/duckduckgo-search.md: «openclaw gateway restart»)."""
    code = run_tty(["configure", "--section", "web"])
    if code == 0 and gateway_health():
        gateway_stop()
        gateway_start()
    return code


def probe_search(query="اختبار البحث"):
    """أيعمل البحثُ فعلاً؟ — بدوالّ المحرّك نفسِه.

    قراءةُ `tools.web.search.enabled` تقول إنّ المفتاحَ مرفوع، لا إنّ البحثَ
    يعمل. فهذا يسأل المحرّكَ: مَن المزوّدون؟ ومَن المختار؟ وأصالحٌ؟ ثمّ
    ينفّذ `runWebSearch` فعلاً.

    ويُشغَّل ببيئة المحرّك (`engine_env`) كي تصله المفاتيحُ كما تصل البوّابة.

    يعيد dict: providers · configured · chosen · usable · ok · count ·
    first · error."""
    _bad = {"providers": [], "configured": [], "chosen": "", "usable": False,
            "ok": False, "count": 0, "first": "", "error": ""}
    nb = node_bin()
    if not nb:
        _bad["error"] = why_unavailable()
        return _bad
    if not os.path.isfile(PROBE_SEARCH):
        _bad["error"] = "probe_search.mjs مفقود"
        return _bad
    try:
        p = subprocess.run([nb, PROBE_SEARCH, str(query or "")],
                           capture_output=True, text=True, timeout=180,
                           cwd=_ROOT, env=engine_env())
        out = (p.stdout or "").strip()
        import json as _j
        i, j = out.find("{"), out.rfind("}")
        if i < 0 or j < i:
            _bad["error"] = (_real_error(p.stderr) or out or "بلا خرج")[:250]
            return _bad
        d = _j.loads(out[i:j + 1])
        return d if isinstance(d, dict) else _bad
    except Exception as e:
        _bad["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        return _bad


# ── بذرُ مساحة العمل: العطبُ الذي كان يقتل كلَّ نوبة ──────────────────────
#
# على جهاز المستخدم (Termux/Android) كانت كلُّ نوبةٍ تموت قبل أن يُنادى
# النموذجُ أصلاً — ورآها `--net-doctor live` بعينها:
#
#   ✗ 8) نوبة حقيقيّة — لم يجب
#     EACCES: permission denied, link
#       '…/state/workspace/openclaw-bootstrap-IWLWOR/AGENTS.md'
#       -> '…/state/workspace/AGENTS.md'
#
# المحرّكُ ينشر ملفّاتِ التمهيد بوصلةٍ صلبةٍ ذرّيّة (`fs.linkSync`)، وأندرويد
# يردّ EACCES على `link()`. ومصنّفُ المحرّك لا يعدُّ EACCES من أخطاء السقوط:
#
#   @openclaw/fs-safe/dist/publish-file.js:14
#     HARDLINK_FALLBACK_CODES = { EPERM, EXDEV, ENOTSUP, EOPNOTSUPP, ENOSYS }
#
# فلا نسخةَ احتياطيّة، ويُرمى الخطأُ خاماً فيسقط التمهيدُ ومعه النوبة.
#
# والعلاجُ من معماريّته هو، لا من عندنا — سطرٌ في دالّته نفسِها:
#
#   workspace-YW5Pl2cf.mjs:231   if (existing) return false;
#
# «الموجودُ لا يُنشر». فتكفي أن تكون الملفّاتُ موجودةً قبلَه، فلا يُنادى
# `linkSync` أبداً. وتُكتب بقوالبه هو من مجلّداتِه هو بعد نزعِ الواجهة كما
# ينزعها هو — فالمحتوى مطابقٌ لما كان سيكتبه، والفرقُ الوحيدُ `write` بدل
# `link`. والتفصيلُ كلُّه في رأس `seed_workspace.mjs`.
_WS_SEEDED = {"done": False}


def workspace_dir():
    """مجلّدُ عمل الوكيل كما يشتقُّه المحرّك — بلا إقلاع node.

    فحصٌ رخيصٌ يُنادى قبل كلِّ نوبة، فلا يجوز أن يُقلع عملية. والمسارُ
    مقيسٌ من رسالة الخطأ على الجهاز: `<state>/workspace`."""
    return os.path.join(_STATE_DIR, "workspace")


def workspace_seeded():
    """أموجودٌ ملفُّ التمهيد الأساسيُّ؟ — فحصُ ملفٍّ لا أكثر."""
    try:
        return os.path.isfile(os.path.join(workspace_dir(), "AGENTS.md"))
    except Exception:
        return False


def seed_workspace(timeout=180):
    """ابذر ملفّاتِ التمهيد بقوالب المحرّك. يعيد dict ولا يرفع استثناءً."""
    _bad = {"ok": False, "workspace": "", "files": [], "created": 0,
            "existed": 0, "error": ""}
    nb = node_bin()
    if not nb:
        _bad["error"] = why_unavailable()
        return _bad
    if not os.path.isfile(SEED_WS):
        _bad["error"] = "seed_workspace.mjs مفقود"
        return _bad
    try:
        p = subprocess.run([nb, SEED_WS], capture_output=True, text=True,
                           timeout=timeout, cwd=_ROOT, env=engine_env())
        out = (p.stdout or "").strip()
        import json as _j
        i, j = out.find("{"), out.rfind("}")
        if i < 0 or j < i:
            _bad["error"] = (_real_error(p.stderr) or out or "بلا خرج")[:250]
            return _bad
        d = _j.loads(out[i:j + 1])
        return d if isinstance(d, dict) else _bad
    except Exception as e:
        _bad["error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        return _bad


def ensure_workspace(say=None):
    """ابذر مرّةً واحدةً إن لزم. رخيصةٌ حين لا يلزم: فحصُ ملفٍّ لا غير."""
    if _WS_SEEDED["done"] or workspace_seeded():
        _WS_SEEDED["done"] = True
        return True, "مبذورة"
    r = seed_workspace()
    _WS_SEEDED["done"] = bool(r.get("ok"))
    # والدستورُ يُركَّب بعد البذر مباشرةً: ملفّاتُ التمهيد صارت موجودةً الآن،
    # و`soul_apply` لا يدهس تحريرَك ولا يُركّب مرّتين.
    if r.get("ok") and soul_on():
        _ok2, _why2 = soul_apply()
        if say:
            try:
                say(("… دستورُ الكتابة: " + str(_why2)) if _ok2
                    else ("⚠ الدستور: " + str(_why2)[:120]))
            except Exception:
                pass
    if r.get("ok") and skills_on():
        _ok3, _rows3 = skills_apply()
        if say:
            try:
                say("… المهارات: %d/%d"
                    % (sum(1 for _, o, _w in _rows3 if o), len(_rows3)))
            except Exception:
                pass
    if say:
        try:
            say("… بذرُ مساحة العمل: %d ملفّاً" % (r.get("created") or 0)
                if r.get("ok") else "⚠ تعذّر بذرُ مساحة العمل: "
                + str(r.get("error"))[:120])
        except Exception:
            pass
    return bool(r.get("ok")), (r.get("error") or "%d ملفّاً" % (r.get("created") or 0))


# ── دستورُ الكتابة: SOUL.md ──────────────────────────────────────────────
#
# أين يُوضَع نصٌّ يقرؤه النموذجُ في كلِّ نوبة؟ سؤالٌ لم أُجب عنه بظنّ، بل قِسته
# بدوالّ المحرّك (`probe_bootstrap.mjs`)، والنتيجةُ على مجلّد العمل نفسِه:
#
#   AGENTS.md     6309 حرفاً  ≈ 1753 رمزاً
#   BOOTSTRAP.md  4891       ≈ 1359
#   SOUL.md       1561       ≈  434      ⟵ يصل كاملاً، غيرَ مقصوص
#   IDENTITY.md   1398       ≈  388
#   USER.md       1136       ≈  316
#   ─────────────────────────────────────
#   المجموع      15295       ≈ 4249 رمزاً  تُدفَع في **كلِّ** رسالة
#
# والآليّةُ من كود المحرّك:
#   workspace-YW5Pl2cf.mjs:743  loadWorkspaceBootstrapFiles(dir)
#   bootstrap-DYYMCrXY.mjs:236  buildBootstrapContextFiles(files, opts)
#   :53  DEFAULT_BOOTSTRAP_MAX_CHARS       = 20000   لكلِّ ملفّ
#   :54  DEFAULT_BOOTSTRAP_TOTAL_MAX_CHARS = 60000   للمجموع
#
# فـ`SOUL.md` هو رفُّ الصوت والأسلوب عند أوبن كلاو، ويُحقَن كاملاً. وما فيه
# افتراضياً قالبٌ عامٌّ ينصح بألّا يقول «Great question!» — لا علاقةَ له
# بنظام بحثٍ عربيّ. فيُبدَّل محتواه، ولا يُضاف ملفٌّ جديد: الزيادةُ الصافية
# ‎+1165 حرفاً ≈ ‎+380 رمزاً، لا 1265.
#
# ولا يُدهَس شيءٌ بحال: القديمُ يُحفَظ في `SOUL.md.openclaw` مرّةً واحدة،
# و`--soul restore` يُرجعه، و`WEAVER_SOUL=off` تمنع التركيبَ التلقائيّ.
# وإن حرّرتَ الملفَّ بنفسك فلن يُمَسّ — يُقال لك ولا يُكتَب فوقه.
SOUL_NAME = "SOUL.md"
SOUL_BACKUP = "SOUL.md.openclaw"
_SOUL_MARK = "# SOUL.md — أسلوبُ الكتابة"


def soul_path():
    return os.path.join(workspace_dir(), SOUL_NAME)


def soul_on():
    """أمسموحٌ التركيبُ التلقائيّ؟ `WEAVER_SOUL=off` تمنعه."""
    return (os.environ.get("WEAVER_SOUL", "on") or "on").strip().lower() \
        not in ("0", "off", "false", "no")


def _read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


def soul_state():
    """مَن المُركَّبُ الآن؟ يعيد dict ولا يرفع استثناءً.

    which: weaver (دستورُنا) · openclaw (قالبُ المحرّك) · custom (حرّرتَه
    أنت) · missing (لا ملفّ)."""
    cur = _read(soul_path())
    src = _read(SOUL_SRC)
    # القالبُ على القرص تُنزَع واجهتُه قبل الكتابة، تماماً كما يفعل المحرّك:
    #   workspace-YW5Pl2cf.mjs:168  stripFrontMatter(content)
    # فمقارنةُ المكتوبِ بالخامِ تفشل دائماً، فيُحسَب قالبُ المحرّك «تحريراً
    # منك» ويُرفض التركيب. قِيس: قال «مُحرَّرٌ بيدك» وهو قالبُه بعينه.
    tpl = ""
    try:
        _d = os.path.join(RUNTIME, "docs", "reference", "templates", SOUL_NAME)
        tpl = _read(_d)
        if tpl.lstrip().startswith("---"):
            _t = tpl.lstrip()
            _end = _t.find("\n---", 3)
            if _end > 0:
                tpl = _t[_end + 4:].lstrip()
    except Exception:
        pass
    if not cur.strip():
        which = "missing"
    elif _SOUL_MARK in cur:
        # دستورُنا — لكن هل أضفتَ إليه؟ قولُ «مُركَّبٌ سلفاً» لمن حرّره
        # يُضلّل: يظنّ أنّ ترقيةً جرت ولم تجرِ.
        which = "weaver" if cur.strip() == src.strip() else "weaver-edited"
    elif tpl and cur.strip() == tpl.strip():
        which = "openclaw"
    else:
        which = "custom"
    return {"which": which, "path": soul_path(),
            "chars": len(cur), "src_chars": len(src),
            "backup": os.path.isfile(
                os.path.join(workspace_dir(), SOUL_BACKUP)),
            "src_ok": bool(src.strip())}


def soul_apply(force=False):
    """ركّب الدستور. يعيد (نجح، سبب). لا يدهس تحريرَك ولا يرفع استثناءً."""
    st = soul_state()
    if not st["src_ok"]:
        return False, "الدستورُ مفقود: " + SOUL_SRC
    if st["which"] == "weaver" and not force:
        return True, "مُركَّبٌ سلفاً (%d حرفاً)" % st["chars"]
    if st["which"] == "weaver-edited" and not force:
        return False, ("الدستورُ مُركَّبٌ ومُضافٌ إليه بيدك (%d حرفاً مقابل %d) "
                       "— لن يُدهَس. أضف --force للاستبدال"
                       % (st["chars"], st["src_chars"]))
    if st["which"] == "custom" and not force:
        return False, ("SOUL.md مُحرَّرٌ بيدك — لن يُدهَس. "
                       "أضف --force إن أردتَ استبداله")
    try:
        os.makedirs(workspace_dir(), exist_ok=True)
        # نسخةٌ احتياطيّةٌ مرّةً واحدة: لا تُدهَس بنسخةٍ أحدث، فالأصلُ هو
        # قالبُ المحرّك لا ما سبقه.
        bak = os.path.join(workspace_dir(), SOUL_BACKUP)
        cur = _read(soul_path())
        if cur.strip() and not os.path.isfile(bak):
            with open(bak, "w", encoding="utf-8") as fh:
                fh.write(cur)
        with open(soul_path(), "w", encoding="utf-8") as fh:
            fh.write(_read(SOUL_SRC))
        return True, "رُكِّب (%d حرفاً)" % len(_read(SOUL_SRC))
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:160])


def soul_restore():
    """أرجِع قالبَ المحرّك من النسخة الاحتياطيّة. يعيد (نجح، سبب)."""
    bak = os.path.join(workspace_dir(), SOUL_BACKUP)
    if not os.path.isfile(bak):
        return False, "لا نسخةَ احتياطيّة: " + bak
    try:
        with open(soul_path(), "w", encoding="utf-8") as fh:
            fh.write(_read(bak))
        return True, "أُرجع قالبُ المحرّك"
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:160])


# ── المهاراتُ: ما بعد التوليد ────────────────────────────────────────────
#
# المبدأ الذي قسّمنا عليه: ما يمنع البصمةَ قبل ولادتها في `SOUL.md`؛ وما
# يصلحها بعدها مهارةٌ **يستدعيها النموذجُ حين يقرّر**. لا ترتيبَ مُثبَّت.
#
# وموضعُها من وثيقة المحرّك — الأولويّةُ الأولى، تعلو على مهاراته المرفقة:
#     docs/tools/skills.md:41   1 — highest   <workspace>/skills
#
# وكلفتُها في البرومبت الاسمُ والوصفُ فقط؛ الجسمُ يُقرأ بأداة `read` إن قرّر:
#     docs/tools/skills.md:796  «~97 characters … ≈ 24 tokens per skill»
#
# والثلاثُ المُركَّبةُ هي الآمنة: قياسٌ (detect-ai)، وفقرةٌ واحدة
# (fix-conclusion)، وسكربتٌ مُختبَرٌ بحارسِ استشهادات (humanize-ar).
# و`rewrite-from-ideas` مؤجَّلةٌ عمداً: «انسَ الصياغةَ الأصليّة» يُزحزح
# الاستشهادَ عن جملته، والعدُّ يقول «سليم» والمعنى مزوَّر.
#
# ولا يُدهَس تحريرُك: مهارةٌ غيّرتَها تُترك ويُقال لك.
SKILLS_DIRNAME = "skills"
_SKILLS_MARK = "{{WEAVER}}"


def skills_dir():
    return os.path.join(workspace_dir(), SKILLS_DIRNAME)


def skills_on():
    """أمسموحٌ التركيبُ التلقائيّ؟ `WEAVER_SKILLS=off` تمنعه."""
    return (os.environ.get("WEAVER_SKILLS", "on") or "on").strip().lower() \
        not in ("0", "off", "false", "no")


def _skill_names():
    try:
        return sorted(d for d in os.listdir(SKILLS_SRC)
                      if os.path.isfile(os.path.join(SKILLS_SRC, d,
                                                     "SKILL.md")))
    except Exception:
        return []


def _skill_body(name):
    """نصُّ المهارة بعد حلِّ المسارات. `{{WEAVER}}` ⟶ جذرُ المشروع."""
    t = _read(os.path.join(SKILLS_SRC, name, "SKILL.md"))
    return t.replace(_SKILLS_MARK, _ROOT)


def skills_state():
    """حالُ كلِّ مهارة: missing · ours · edited. dict، ولا يرفع استثناءً."""
    rows = []
    for n in _skill_names():
        dst = os.path.join(skills_dir(), n, "SKILL.md")
        cur = _read(dst)
        want = _skill_body(n)
        if not cur.strip():
            st = "missing"
        elif cur.strip() == want.strip():
            st = "ours"
        else:
            st = "edited"
        rows.append({"name": n, "state": st, "path": dst,
                     "chars": len(cur), "src_chars": len(want)})
    return {"dir": skills_dir(), "skills": rows,
            "src_ok": bool(rows)}


def skills_apply(force=False):
    """ركّب المهارات. يعيد (نجح، قائمةُ (اسم، نجح، سبب)). لا يدهس تحريرَك."""
    st = skills_state()
    if not st["src_ok"]:
        return False, [("—", False, "لا مهاراتِ مصدرٍ في " + SKILLS_SRC)]
    out, bad = [], 0
    for row in st["skills"]:
        n = row["name"]
        if row["state"] == "ours" and not force:
            out.append((n, True, "مُركَّبةٌ سلفاً"))
            continue
        if row["state"] == "edited" and not force:
            out.append((n, False, "مُحرَّرةٌ بيدك — لن تُدهَس (--force)"))
            bad += 1
            continue
        try:
            os.makedirs(os.path.dirname(row["path"]), exist_ok=True)
            with open(row["path"], "w", encoding="utf-8") as fh:
                fh.write(_skill_body(n))
            out.append((n, True, "رُكِّبت (%d حرفاً)" % row["src_chars"]))
        except Exception as e:
            out.append((n, False, "%s: %s" % (type(e).__name__, str(e)[:120])))
            bad += 1
    return bad == 0, out


def skills_remove():
    """احذف ما ركّبناه وحدَه — لا يُمَسّ ما ليس لنا. يعيد (نجح، سبب)."""
    n_del = 0
    try:
        for row in skills_state()["skills"]:
            if row["state"] in ("ours", "edited") and os.path.isfile(row["path"]):
                import shutil
                shutil.rmtree(os.path.dirname(row["path"]), ignore_errors=True)
                n_del += 1
        return True, "حُذفت %d مهارة" % n_del
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:160])


def skills_seen(timeout=240):
    """أرآها المحرّكُ فعلاً؟ — بأمرِه هو `skills --json`، لا بظنٍّ منّا.

    الدرسُ من SOUL.md: كتابةُ ملفٍّ لا تعني أنّه وصل النموذج. يعيد
    [{name, eligible, modelVisible, source}] أو []."""
    try:
        code, out, _ = run(["skills", "--json"], timeout=timeout)
        if code != 0 or not out.strip():
            return []
        import json as _j
        i, j = out.find("{"), out.rfind("}")
        if i < 0:
            i, j = out.find("["), out.rfind("]")
        if i < 0 or j < i:
            return []
        d = _j.loads(out[i:j + 1])
        rows = d if isinstance(d, list) else (d.get("skills") or [])
        mine = set(_skill_names())
        return [{"name": r.get("name"),
                 "eligible": bool(r.get("eligible")),
                 "modelVisible": bool(r.get("modelVisible")),
                 "source": str(r.get("source") or "")}
                for r in rows if isinstance(r, dict) and r.get("name") in mine]
    except Exception:
        return []


def skills_test(timeout=240):
    """أيعمل القاموسُ فعلاً **بأداةِ المحرّك** لا بصدفتنا؟

    الفرقُ ليس شكلياً: المهارةُ تُملي أمراً، والنموذجُ ينفّذه بـ`exec`.
    وبين الاثنين أسئلةٌ لا تُجاب بالظنّ — أمسموحٌ مسارٌ خارج مساحة العمل؟
    أيوجد `python3` في بيئة المحرّك؟ فيُنفَّذ الأمرُ كما هو ويُقرأ جوابُه.

    يعيد dict: ok · exitCode · text · cwd · intact · changed · error."""
    _bad = {"ok": False, "found": False, "exitCode": None, "cwd": "",
            "text": "", "intact": None, "changed": False, "error": ""}
    nb = node_bin()
    if not nb:
        _bad["error"] = why_unavailable()
        return _bad
    if not os.path.isfile(PROBE_EXEC):
        _bad["error"] = "probe_exec.mjs مفقود"
        return _bad
    # نصُّ اختبارٍ فيه أربعُ عباراتٍ موسومةٍ واستشهادٌ واحد — فيُقاس
    # الاستبدالُ وحمايةُ الاستشهاد معاً.
    _rw = os.path.join(_ROOT, "capabilities", "skills", "arabic_rewriter",
                       "scripts", "rewrite_ar.py")
    _txt = ("يُعدّ التعليمُ ركيزةً أساسيّةً في المنظومة التنمويّة "
            "(الفهري، 2020، ص. 45)، وهو أمرٌ بالغ الأهمية يستدعي جهداً.")
    cmd = ("python3 %s --action humanize --general 0 --text %s"
           % (_rw, "'" + _txt.replace("'", "'\\''") + "'"))
    try:
        p = subprocess.run([nb, PROBE_EXEC, cmd], capture_output=True,
                           text=True, timeout=timeout, cwd=_ROOT,
                           env=engine_env())
        out = (p.stdout or "").strip()
        import json as _j
        i, j = out.find("{"), out.rfind("}")
        if i < 0 or j < i:
            _bad["error"] = (_real_error(p.stderr) or out or "بلا خرج")[:250]
            return _bad
        d = _j.loads(out[i:j + 1])
        if not isinstance(d, dict):
            return _bad
        t = str(d.get("text") or "")
        d["intact"] = ("intact: True" in t) if "intact:" in t else None
        # أبُدّلت العباراتُ الموسومةُ فعلاً؟ قياسٌ لا ثقة.
        d["changed"] = all(w not in t for w in
                           ("يُعدّ", "المنظومة", "بالغ الأهمية", "يستدعي"))
        return d
    except Exception as e:
        _bad["error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        return _bad


# ── هل يُتَّبع الدستور؟ ──────────────────────────────────────────────────
#
# `--soul` يُثبت أنّه مُركَّب، و`--bootstrap` أنّه يصل البرومبت. ولا شيءَ كان
# يُثبت أنّه **يُتَّبع** — والدليلُ الوحيد عينُ المستخدم، وهي التي كشفت فشلَ
# الخاتمة ثمّ فشلَ الشرطة. فصار ما تفعله العينُ أمراً يُعاد بعد كلِّ تعديل.
#
# والفاحصُ يستخرج القائمةَ من الدستور نفسِه (`pipeline/soul_check.py`)، فلا
# تنحرف نسخةٌ ثانيةٌ عن أصلها فتقيس دستوراً لم يعد موجوداً.
_SOUL_PROBE = ("اكتب فقرتين عن أثر التقنية في التعليم، ثمّ خاتمةً لهما. "
               "بالعربيّة الفصحى، وبلا عناوينَ ولا نقاط.")


def soul_check(text):
    """افحص نصّاً على الدستور — حتميّاً وبلا نداءِ نموذج. dict."""
    try:
        from pipeline.soul_check import check as _c
        return _c(text)
    except Exception as e:
        return {"ok": False, "score": 0, "stats": {},
                "violations": [{"rule": "تعذّر الفحص",
                                "term": type(e).__name__,
                                "where": str(e)[:120]}], "warnings": []}


def soul_test(prompt=None, timeout=None):
    """نوبةٌ حقيقيّةٌ ثمّ فحصٌ حتميٌّ لناتجها. dict، ولا يرفع استثناءً.

    الكلفة: نداءُ نموذجٍ واحد. والفحصُ بعده صفرُ نداءات."""
    r = ask(prompt or _SOUL_PROBE, timeout=timeout, fallback=False,
            session="soultest-" + str(int(time.time())))
    ans = (r or {}).get("answer") or ""
    if not ans.strip():
        # لم يُقَس شيءٌ فلا حكم. وكان يُعيد «مخالف 0/100» — حكماً على نصٍّ لم
        # يُكتب. قِيس على جهاز المستخدم: رصيدُ المزوّد نفد، فقالت الأداةُ إنّ
        # النموذجَ خالف الدستور. والصحيح: «لم يُقَس» مع السبب كاملاً.
        return {"ok": False, "measured": False, "score": None, "text": "",
                "stats": {}, "violations": [], "warnings": [],
                "reason": (r or {}).get("note", "") or "النموذجُ لم يُجب"}
    out = soul_check(ans)
    out["text"] = ans
    out["measured"] = True
    return out


# ── وهل يستدعي النموذجُ المهارةَ حين يجب؟ ────────────────────────────────
#
# `--skills seen` يُثبت أنّه **يراها**، و`--skills test` أنّ السكربتَ **يعمل**.
# وبينهما سؤالٌ ثالثٌ لا يُجيبه أيٌّ منهما: أيختارها؟ وهو أخطرُ ما في نظام
# المهارات — وصفٌ غامضٌ يجعلها ميّتةً **بلا رسالةِ خطأ**.
#
# والدليلُ من مسار النوبة عند المحرّك (`sessions export-trajectory`): إن
# قرأ `SKILL.md` أو نفّذ سكربتَها فقد اختارها.
_SKILL_PROBE = ("هذا نصٌّ كتبه نموذجٌ آخر، نظّفه من بصمة الذكاء الاصطناعيّ:\n\n"
                "«يُعدّ التعليمُ ركيزةً أساسيّةً في المنظومة التنمويّة، "
                "وعلاوة على ذلك فهو أمرٌ بالغ الأهمية يستدعي تضافر الجهود.»")


# طلبٌ طبيعيٌّ لكلِّ مهارة — **لا يذكر اسمَها**، ولا يأمر النموذجَ بشيء.
# النموذجُ يقرّر وحده؛ والاختبارُ يقرأ مسارَ النوبة من سجلّ المحرّك بعدها
# (`trajectory`) ليقول: أفتح ملفَّ المهارة أم لا. كاميرا لا شرطيّ — ولا
# يعمل إلا حين تكتب الأمرَ في الطرفيّة، فلا يمسّ محادثةً ولا جواباً.
_FIX_FIRST = ("التقنيةُ غيّرت طريقةَ التعلّم في المدارس، وصار الطالبُ يصل إلى "
              "المعلومة في ثوانٍ، لكنّ المعلّمَ ما زال يقرّر ما يستحقّ القراءة.")
_SKILL_PROBES = {
    "humanize-ar": _SKILL_PROBE,
    "detect-ai": (
        "وصلني هذا النصُّ من شخصٍ آخر. هل كتبه ذكاءٌ اصطناعيّ؟ "
        "أريد تقييماً فقط:\n\n"
        "«يُعدّ التعليمُ ركيزةً أساسيّةً في المنظومة التنمويّة، وعلاوة على "
        "ذلك فهو أمرٌ بالغ الأهمية يستدعي تضافر الجهود. وفي الختام، يتضح أنّ "
        "الاستثمارَ في التعليم هو السبيلُ الأمثلُ لبناء مستقبلٍ مشرق.»"),
    "fix-conclusion": (
        "أصلح خاتمةَ هذا المقال:\n\n«" + _FIX_FIRST + "\n\n"
        "وفي الختام، يتضح أنّ التقنيةَ ركيزةُ المستقبل، ومن هنا فإنّ تضافرَ "
        "الجهود أمرٌ لا غنى عنه لبناء تعليمٍ أفضل.»"),
}


def skills_invoke_test(prompt=None, timeout=None, target=None):
    """أيستدعي النموذجُ مهارةً حين يجب؟ — من مسار النوبة، لا من الجواب.

    `target`: مهارةٌ بعينها — فيُعطى النموذجُ طلباً طبيعياً يناسبها
    (`_SKILL_PROBES`)، والنجاحُ أن يفتحها **هي**. وبلا `target`: كما كان
    حرفاً (طلبُ humanize-ar، والنجاحُ أيُّ مهارة).

    يعيد {ok, measured, target, called:[], answer, trajectory:[], note,
    extra:{}}. و`extra` معلوماتٌ للعرض لا تدخل في الحكم."""
    sk = "skillinvoke-" + str(int(time.time()))
    prompt = prompt or _SKILL_PROBES.get(target or "") or _SKILL_PROBE
    r = ask(prompt, timeout=timeout, fallback=False,
            session=sk)
    ans = (r or {}).get("answer") or ""
    calls = trajectory(sk) or []
    names = set(_skill_names())
    hit = []
    for c in calls:
        blob = "%s %s" % (c.get("name") or "", c.get("request") or "")
        for n in names:
            if n in str(blob) and n not in hit:
                hit.append(n)
        if "rewrite_ar" in str(blob) and "humanize-ar" not in hit:
            hit.append("humanize-ar")
    # لا جوابَ ولا مسار ⟶ النموذجُ لم يعمل، فلا دليلَ على شيء. وكان يُقال
    # «لم يستدعِ شيئاً — راجع وصفَ المهارة» فيُوجَّه المستخدمُ إلى إصلاح وصفٍ
    # سليم، والسببُ الحقيقيُّ رصيدٌ نفد. التشخيصُ الخاطئ أسوأُ من لا تشخيص.
    _ran = bool(ans.strip()) or bool(calls)
    extra = {}
    if target == "detect-ai" and ans:
        # المهارةُ تُخرج JSON بهذه الحقول، ولا تُعيد صياغةَ شيء.
        extra["تقريرٌ بحقول المهارة"] = ("next_skills" in ans
                                         or "recommendation" in ans)
    if target == "fix-conclusion" and ans:
        extra["الفقرةُ الأولى لم تُمَسّ"] = _FIX_FIRST in ans
        import re as _re
        _paras = [x for x in _re.split(r"\n\s*\n", ans.strip()) if x.strip()]
        if _paras:
            _sc = soul_check(_paras[-1])
            extra["فاحصُ الدستور على آخر فقرة"] = (
                "%s/100" % _sc.get("score") if isinstance(_sc, dict) else "—")
    return {"ok": (target in hit) if target else bool(hit),
            "measured": _ran, "target": target or "",
            "called": hit, "answer": ans,
            "trajectory": [c.get("name") for c in calls if c.get("name")],
            "note": (r or {}).get("note", ""), "extra": extra}


def bootstrap_report(timeout=180):
    """ماذا يدخل البرومبتَ من ملفّات التمهيد؟ — بدوالّ المحرّك. dict."""
    _bad = {"ok": False, "workspace": "", "files": [], "totalChars": 0,
            "totalTokens": 0, "warnings": [], "error": ""}
    nb = node_bin()
    if not nb:
        _bad["error"] = why_unavailable()
        return _bad
    if not os.path.isfile(PROBE_BOOT):
        _bad["error"] = "probe_bootstrap.mjs مفقود"
        return _bad
    try:
        p = subprocess.run([nb, PROBE_BOOT], capture_output=True, text=True,
                           timeout=timeout, cwd=_ROOT, env=engine_env())
        out = (p.stdout or "").strip()
        import json as _j
        i, j = out.find("{"), out.rfind("}")
        if i < 0 or j < i:
            _bad["error"] = (_real_error(p.stderr) or out or "بلا خرج")[:250]
            return _bad
        d = _j.loads(out[i:j + 1])
        return d if isinstance(d, dict) else _bad
    except Exception as e:
        _bad["error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        return _bad


def tool_inventory():
    """أيُّ أدواتٍ يراها النموذجُ فعلاً؟ — بحساب المحرّك نفسِه.

    الجردُ يُحسب بـ`resolveEffectiveToolInventory` — نفسُ الدالّة التي يُجيب
    بها أمرُ المحرّك `/tools` — أي **بعد** كلِّ المصافي: سياسةُ المزوّد،
    وحذفُ `web_search` حين يكون بحثُ Codex الأصليُّ فعّالاً، وملفُّ الأدوات.

    يعيد dict: ok · profile · tools · web_search · web_fetch · browser ·
    suppressed · suppressReason · error."""
    _bad = {"ok": False, "profile": "", "agentId": "", "groups": [],
            "tools": [], "web_search": False, "web_fetch": False,
            "browser": False, "suppressed": False, "suppressReason": "",
            "error": ""}
    nb = node_bin()
    if not nb:
        _bad["error"] = why_unavailable()
        return _bad
    if not os.path.isfile(PROBE_TOOLS):
        _bad["error"] = "probe_tools.mjs مفقود"
        return _bad
    try:
        p = subprocess.run([nb, PROBE_TOOLS, provider_id() or "",
                            model_id() or ""],
                           capture_output=True, text=True, timeout=180,
                           cwd=_ROOT, env=engine_env())
        out = (p.stdout or "").strip()
        import json as _j
        i, j = out.find("{"), out.rfind("}")
        if i < 0 or j < i:
            _bad["error"] = (_real_error(p.stderr) or out or "بلا خرج")[:250]
            return _bad
        d = _j.loads(out[i:j + 1])
        return d if isinstance(d, dict) else _bad
    except Exception as e:
        _bad["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        return _bad


# ── تشخيصُ الاتصال: محطّةً محطّة، بالدليل ───────────────────────────────
#
# «لا يملك إتصال بالإنترنت» عَرَضٌ واحد، ومساره ثمانُ محطّات، وأيُّ واحدةٍ
# تسقط تُنتج العَرَضَ نفسَه بلا أن تقول أيُّها سقطت. وثلاثةُ أيّامٍ ضاعت في
# التخمين لأنّ المسارَ لم يكن مقروءاً. فهذا يقرؤه.
#
# وكلُّ محطّةٍ تُقاس بدالّة المحرّك نفسِه حيث وُجدت، لا بحيلةٍ من عندنا.
NET_HOPS = ("المحرّك", "البوّابة", "جاهزيّةُ المحادثة", "النموذجُ والمفتاح",
            "أدواتُ النموذج", "مزوّدُ البحث", "مهلةُ النوبة",
            "مساحةُ العمل", "نوبةٌ حقيقيّة")


def net_doctor(live=False, query=None, out=None):
    """افحص مسارَ الاتصال كلَّه. يعيد قائمةَ محطّاتٍ ولا يرفع استثناءً.

    كلُّ محطّة: {n, name, ok, say, why}. و`live=True` تُضيف نوبةً حقيقيّةً
    تُنادي النموذجَ وتقرأ مسارَه (`sessions export-trajectory`) لترى هل
    استدعى `web_search` فعلاً — وهو الدليلُ الوحيدُ القاطع.

    و`out` دالّةُ طباعة: تُطبع كلُّ محطّةٍ **فور انتهائها** لا عند النهاية.
    فكلُّ محطّةٍ تُقلع node مرّةً على الأقلّ (٥ ث على خادم، أضعافُها على
    هاتف)، وجمعُ الكلِّ ثمّ طبعُه يعني صمتاً طويلاً يبدو عُطلاً."""
    rows = []
    _t_all = time.time()

    def add(n, ok, say, why=""):
        row = {"n": n, "name": NET_HOPS[n - 1], "ok": bool(ok),
               "say": str(say), "why": str(why),
               "sec": round(time.time() - _t_all, 1)}
        rows.append(row)
        if out:
            try:
                out(row)
            except Exception:
                pass

    # ① المحرّك
    _av, _nb = available(), node_bin()
    add(1, _av and _nb,
        (("مركَّب · " + (version() or "إصدارٌ غيرُ معروف")) if (_av and _nb)
         else "غيرُ صالحٍ للتشغيل"),
        "" if (_av and _nb) else why_unavailable())

    # ② البوّابة
    st = gateway_state()
    if not st["allowed"]:
        add(2, True, "مُعطَّلةٌ باختيارك (WEAVER_GATEWAY=0) — يُستعمل "
                     "`agent exec` المعزول", "")
    else:
        add(2, st["alive"],
            ("حيّة · منفذ %s · pid %s" % (st["port"], st["pid"]))
            if st["alive"] else "لا تردّ على المنفذ %s" % st["port"],
            "" if st["alive"] else "السجلّ: " + st["log"])

    # ③ جاهزيّةُ المحادثة — نفسُ الشرط الذي تفحصه واجهةُ الويب حرفاً.
    _ready = bool(_av and _nb)
    add(3, _ready,
        "المحادثةُ تمرّ بالمحرّك (وفيه الأدوات)" if _ready
        else "المحادثةُ تسقط إلى النداء المباشر — **بلا أدوات، فبلا إنترنت**",
        "" if _ready else why_unavailable())

    # ④ النموذجُ والمفتاح
    _p, _m, _c = provider_id(), model_id(), credentials()
    _okm = bool(_m and _c)
    add(4, _okm,
        ((_m or "—") + " · مفتاح " + ", ".join(
            "%s=…%s" % (k, v[-4:]) for k, v in _c.items()))
        if _okm else ("النموذج: " + (_m or "غيرُ محدَّد")
                      + " · المفتاح: " + ("موجود" if _c else "غائب")),
        "" if _okm else "بلا نموذجٍ محدَّدٍ يسقط المحرّكُ إلى افتراضيّه فيفشل "
                        "بالاعتماد")

    # ⑤ أدواتُ النموذج — الدليلُ على وصول `web_search` إليه
    if out:
        try:
            out({"n": 5, "name": NET_HOPS[4], "busy": True})
        except Exception:
            pass
    inv = tool_inventory()
    _okt = bool(inv.get("ok") and inv.get("web_search"))
    if inv.get("error"):
        add(5, False, "تعذّر حسابُ الجرد", inv["error"])
    else:
        add(5, _okt,
            "%d أداة · %s رمزاً/رسالة · ملفّ «%s» · web_search %s · web_fetch %s"
            " · browser %s"
            % (len(inv.get("tools") or []),
               ("≈" + str(inv.get("tokens"))) if inv.get("tokens") else "؟",
               inv.get("profile") or "?",
               "حاضرة" if inv.get("web_search") else "غائبة ✗",
               "حاضرة" if inv.get("web_fetch") else "غائبة",
               "حاضر" if inv.get("browser") else "غائب"),
            "" if _okt else ("سببُ الحذف عند المحرّك: "
                             + (inv.get("suppressReason") or "غيرُ معروف")))

    # ⑥ مزوّدُ البحث — نداءُ بحثٍ حقيقيّ
    if out:
        try:
            out({"n": 6, "name": NET_HOPS[5], "busy": True})
        except Exception:
            pass
    sr = probe_search(query or "أخبار اليوم")
    if sr.get("ok"):
        _ms = sr.get("tookMs") or 0
        _say6 = "%s · %d نتيجة%s" % (
            sr.get("provider") or sr.get("chosen") or "?",
            sr.get("count") or 0,
            ("  (%.1f ث)" % (_ms / 1000.0)) if _ms else "")
    else:
        _say6 = ("المختار: " + (sr.get("chosen") or "لا شيء")
                 + " · صالح: " + ("نعم" if sr.get("usable") else "لا"))
    add(6, sr.get("ok"), _say6,
        "" if sr.get("ok") else (sr.get("error") or ""))

    # ⑦ مهلةُ النوبة — العطبُ الذي أعمانا: كنّا نقتلها عند ٢٢٠ ث
    _dl = agent_deadline()
    _cfg = ""
    try:
        _c2, _o2, _ = run(["config", "get", "agents.defaults.timeoutSeconds"],
                          timeout=60)
        _cfg = (_o2 or "").strip().strip('"') if _c2 == 0 else ""
    except Exception:
        pass
    _okd = _dl >= 600
    add(7, _okd,
        "%d ث · ساعةُ الحائط %d ث · في إعداد المحرّك: %s"
        % (_dl, _dl + _AGENT_GRACE, _cfg or "غيرُ مضبوطة"),
        "" if _okd else "أقصرُ من مهلة المحرّك نفسِه (٦٠٠) — النوبةُ تُقتل "
                        "وهي تبحث")

    # ⑧ مساحةُ العمل — التمهيدُ يموت بـEACCES على `link()` في أندرويد،
    #    فلا يُنادى النموذجُ أصلاً. وهذه المحطّةُ تسمّيه باسمه قبل النوبة.
    _wsd = workspace_dir()
    _wsok = workspace_seeded()
    add(8, _wsok,
        ("ملفّاتُ التمهيد موجودة · " + _wsd) if _wsok
        else ("AGENTS.md غائبٌ في " + _wsd),
        "" if _wsok else "التمهيدُ سيُنشئه بوصلةٍ صلبة، وأندرويد يردّ EACCES "
                         "على link() — فتموت النوبةُ قبل النموذج. "
                         "العلاج: --seed-workspace")

    # ⑨ نوبةٌ حقيقيّة — لا تُشغَّل إلّا بطلبك: تكلّف رموزاً ووقتاً.
    if not live:
        add(9, True, "لم تُشغَّل (أضف `live` لتشغيلها)", "")
        return rows
    if out:
        try:
            out({"n": 9, "name": NET_HOPS[8], "busy": True})
        except Exception:
            pass
    _sk = "netdoctor-" + str(int(time.time()))
    _q = (query or "ابحث في الويب عن آخر خبرٍ منشورٍ اليوم، "
                   "واذكر عنوانَه ورابطَه وتاريخَه.")
    r = ask(_q, timeout=_dl + _AGENT_GRACE, fallback=False, session=_sk)
    _ans = (r or {}).get("answer") or ""
    calls = trajectory(_sk)
    _names = [c.get("name") for c in calls if c.get("name")]
    _searched = any("search" in str(n) or "fetch" in str(n) or "browser"
                    in str(n) for n in _names)
    add(9, bool(_ans.strip()) and _searched,
        ("استدعى: " + ", ".join(_names[:8])) if _names
        else ("أجاب بلا استدعاء أيّ أداة" if _ans.strip()
              else "لم يُجب"),
        "" if _searched else ((r or {}).get("note") or
                              "الأدواتُ حاضرةٌ والنموذجُ لم يستدعِها"))
    return rows


def _unknown_sub(flag, sub, valid):
    """أمرٌ فرعيٌّ مجهول: خطأٌ صريح، لا شاشةُ حالةٍ صامتة.

    كان المجهولُ يسقط إلى `show` فيعرض الحالةَ ويخرج بـ0 — فبدا للمستخدم
    أنّ `--soul test` اشتغل، والحقيقةُ أنّ نسختَه لم تكن تعرفه بعد (لم
    يسحب الالتزامَ الذي أضافه). الصمتُ أخفى السببَ كلَّه."""
    print("  ✗ أمرٌ فرعيٌّ غيرُ معروف: %s %s" % (flag, sub), file=sys.stderr)
    print("    المعروف: " + " · ".join(valid), file=sys.stderr)
    print("\n    إن كان أمراً جديداً فنسختُك أقدمُ منه — اسحب أوّلاً:"
          "\n      git pull origin claude/extract-compressed-folders-51v4ib",
          file=sys.stderr)
    sys.exit(2)


def _print_soul_report(r):
    """تقريرُ فحصِ الدستور — مشترَكٌ بين `--soul check` و`--soul test`."""
    st = r.get("stats") or {}
    if st:
        print("  %d كلمة · %d فقرة · %d جملة · فُحص %d مصطلحاً"
              % (st.get("words", 0), st.get("paragraphs", 0),
                 st.get("sentences", 0), st.get("banned_checked", 0)))
    for v in r.get("violations") or []:
        print("  ✗ %-34s «%s» %s"
              % (v.get("rule", ""), v.get("term", ""), v.get("where", "")))
    for w in r.get("warnings") or []:
        print("  ⚠ %-34s %s %s"
              % (w.get("rule", ""), w.get("term", ""), w.get("where", "")))
    print()
    print("  %s   ·   الدرجة %d/100"
          % ("✓ مطابقٌ للدستور" if r.get("ok") else "✗ مخالف",
             r.get("score", 0)))


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
    if argv[:1] == ["--net-doctor"]:
        _live = "live" in argv[1:]
        _q = None
        for a in argv[1:]:
            if a != "live":
                _q = a
        print("  الاتصالُ بالإنترنت — المسارُ كلُّه، محطّةً محطّة"
              + ("  (ومعه نوبةٌ حقيقيّة)" if _live else ""))
        print("  (كلُّ محطّةٍ تُقلع node مرّةً — فالانتظارُ عملٌ لا عُطل)\n")

        # سطرُ «جارٍ» يُمسح ويُستبدل — لكن المحوَ رموزُ طرفيّة، فإن أُعيد
        # التوجيهُ إلى ملفٍّ ظهرت خاماً (`[2K`). فلا تُكتب إلّا على طرفيّة.
        _tty = sys.stdout.isatty()

        def _emit(r):
            if r.get("busy"):
                if _tty:
                    sys.stdout.write("  … %d) %s" % (r["n"], r["name"]))
                    sys.stdout.flush()
                return
            if _tty:
                sys.stdout.write("\r\033[2K")   # امسح سطرَ «جارٍ»
            print("  %s %d) %-18s %s   [%.0f ث]"
                  % ("✓" if r["ok"] else "✗", r["n"], r["name"], r["say"],
                     r.get("sec") or 0))
            if r["why"]:
                print("        └─ " + r["why"][:300])
            sys.stdout.flush()

        rows = net_doctor(live=_live, query=_q, out=_emit)
        _first_bad = None
        for r in rows:
            if not r["ok"] and _first_bad is None:
                _first_bad = r
        print()
        if _first_bad is None:
            print("  كلُّ المحطّات سليمة.")
            if not _live:
                print("  والدليلُ القاطعُ نوبةٌ حقيقيّة:"
                      "\n     python3 -m pipeline.weaver_core --net-doctor live")
        else:
            print("  ✗ العطبُ في المحطّة %d — %s"
                  % (_first_bad["n"], _first_bad["name"]))
            if _first_bad["why"]:
                print("    " + _first_bad["why"][:300])
        sys.exit(0 if _first_bad is None else 1)
    if argv[:1] == ["--skills"]:
        sub = argv[1] if len(argv) > 1 else "show"
        _valid = ("show", "apply", "remove", "seen", "test", "invoke")
        if sub not in _valid and not sub.startswith("-"):
            _unknown_sub("--skills", sub, _valid)
        if sub == "apply":
            ok2, rows = skills_apply(force=("--force" in argv))
            for n, o, why in rows:
                print(("  ✓ " if o else "  ✗ ") + "%-16s %s" % (n, why))
            print("\n  المجلّد: " + skills_dir())
            if ok2:
                print("\n  وللتحقّق أنّ المحرّكَ رآها:"
                      "\n     python3 -m pipeline.weaver_core --skills seen")
            sys.exit(0 if ok2 else 1)
        if sub == "remove":
            ok2, why2 = skills_remove()
            print(("  ✓ " if ok2 else "  ✗ ") + str(why2))
            sys.exit(0 if ok2 else 1)
        if sub == "test":
            print("  تشغيلُ القاموس بأداةِ `exec` الحقيقيّة للمحرّك\n")
            r = skills_test()
            if r.get("error"):
                print("  ✗ " + str(r["error"])[:300], file=sys.stderr)
                sys.exit(1)
            print("  أداةُ exec متاحة : "
                  + ("نعم" if r.get("found") else "لا ✗"))
            print("  رمزُ الخروج      : " + str(r.get("exitCode")))
            print("  مجلّدُ التنفيذ    : " + str(r.get("cwd") or "—"))
            print("  الاستشهادُ سليم  : "
                  + {True: "نعم", False: "لا ✗", None: "—"}[r.get("intact")])
            print("  العباراتُ بُدّلت  : "
                  + ("نعم" if r.get("changed") else "لا ✗"))
            print("\n  الناتج:\n    " + str(r.get("text") or "—")[:600]
                  .replace("\n", "\n    "))
            _good = (r.get("ok") and r.get("intact") is not False
                     and r.get("changed"))
            print("\n  " + ("✓ القاموسُ يعمل من داخل المحرّك"
                            if _good else "✗ لا يعمل كما ينبغي"))
            sys.exit(0 if _good else 1)
        if sub == "invoke":
            # `--skills invoke <مهارة>`: والاسمُ المجهولُ خطأٌ صريح — كان
            # يُتجاهَل بصمت، فشُغّل اختبارُ humanize-ar مرّتين وبدا أنّه
            # اختبارُ detect-ai وfix-conclusion.
            _tgt = next((a for a in argv[2:] if not a.startswith("-")), None)
            if _tgt and _tgt not in _SKILL_PROBES:
                _unknown_sub("--skills invoke", _tgt, tuple(_SKILL_PROBES))
            print("  أيستدعي النموذجُ " + (("«%s»" % _tgt) if _tgt
                                         else "مهارةً")
                  + " حين يجب؟   (نداءُ نموذجٍ واحد)\n")
            _r = skills_invoke_test(target=_tgt)
            if _r.get("measured") is False:
                print("  ⚠ لم يُقَس — النموذجُ لم يعمل، فلا دليلَ على المهارة.\n")
                print("  السبب:")
                for _ln in str(_r.get("note") or "النموذجُ لم يُجب").split("\n"):
                    print("    " + _ln)
                _why = str(_r.get("note") or "").lower()
                if "billing" in _why or "credit" in _why or "balance" in _why:
                    print("\n  ⟵ رصيدُ المزوّد نفد. اشحنه ثمّ أعِد:"
                          "\n     https://openrouter.ai/credits")
                print("\n  (وصفُ المهارة ليس السبب — لم يُختبَر أصلاً)")
                sys.exit(3)
            print("  استدعى      : "
                  + (", ".join(_r["called"]) if _r["called"] else "لا شيء ✗"))
            print("  مسارُ النوبة : "
                  + (", ".join(_r["trajectory"][:10]) or "—"))
            if _r.get("answer"):
                print("\n  ── الجواب ──")
                for _ln in str(_r["answer"])[:900].split("\n"):
                    print("  " + _ln)
            if _r.get("note"):
                print("\n  ⓘ " + str(_r["note"]))
            for _k, _v in (_r.get("extra") or {}).items():
                print("  ⓘ %s: %s" % (_k, {True: "نعم", False: "لا"}.get(_v, _v)))
            if _tgt:
                print("\n  " + ("✓ اختار «%s» بنفسه" % _tgt if _r["ok"] else
                                 "✗ لم يستدعِ «%s»" % _tgt
                                 + (" (استدعى غيرَها)" if _r["called"]
                                    else "")
                                 + " — النموذجُ لا يثبت دائماً؛ أعِد مرّةً"
                                   " قبل الحكم على وصفها"))
            else:
                print("\n  " + ("✓ اختارها بنفسه" if _r["ok"] else
                                 "✗ لم يستدعِ شيئاً — راجع وصفَ المهارة"))
            sys.exit(0 if _r["ok"] else 1)
        if sub == "seen":
            rows = skills_seen()
            if not rows:
                print("  لم يُرجع المحرّكُ شيئاً — أمُركَّبةٌ؟ "
                      "(--skills apply)", file=sys.stderr)
                sys.exit(1)
            print("  ما يراه المحرّكُ — بأمرِه `skills --json`\n")
            _bad = 0
            for r in rows:
                _v = r["eligible"] and r["modelVisible"]
                _bad += 0 if _v else 1
                print("  %s %-16s صالحة: %-4s  يراها النموذج: %-4s  المصدر: %s"
                      % ("✓" if _v else "✗", r["name"],
                         "نعم" if r["eligible"] else "لا",
                         "نعم" if r["modelVisible"] else "لا", r["source"]))
            print()
            print("  %d/%d وصلت النموذج" % (len(rows) - _bad, len(rows)))
            sys.exit(1 if _bad else 0)
        st = skills_state()
        _lbl = {"ours": "مُركَّبة", "edited": "مُحرَّرةٌ بيدك",
                "missing": "غيرُ مُركَّبة"}
        print("  المجلّد : " + st["dir"])
        print("  المصدر  : " + SKILLS_SRC)
        print("  تلقائيّاً: " + ("نعم" if skills_on()
                                 else "لا (WEAVER_SKILLS=off)"))
        print()
        for r in st["skills"]:
            print("  %-16s %-14s %s"
                  % (r["name"], _lbl.get(r["state"], r["state"]),
                     ("%d حرفاً" % r["chars"]) if r["chars"] else ""))
        if any(r["state"] == "missing" for r in st["skills"]):
            print("\n  للتركيب: python3 -m pipeline.weaver_core --skills apply")
        return
    if argv[:1] == ["--soul"]:
        sub = argv[1] if len(argv) > 1 else "show"
        _valid = ("show", "apply", "restore", "check", "test")
        if sub not in _valid and not sub.startswith("-"):
            _unknown_sub("--soul", sub, _valid)
        if sub == "apply":
            ok2, why2 = soul_apply(force=("--force" in argv))
            print(("  ✓ " if ok2 else "  ✗ ") + str(why2))
            if ok2:
                print("  المسار: " + soul_path())
                print("\n  ولمعاينة ما يصل البرومبتَ فعلاً:"
                      "\n     python3 -m pipeline.weaver_core --bootstrap")
            sys.exit(0 if ok2 else 1)
        if sub == "restore":
            ok2, why2 = soul_restore()
            print(("  ✓ " if ok2 else "  ✗ ") + str(why2))
            sys.exit(0 if ok2 else 1)
        if sub == "check":
            _src_t = ""
            _f = next((a for a in argv[2:] if not a.startswith("-")), "")
            if _f == "-" or not _f:
                _src_t = sys.stdin.read() if not sys.stdin.isatty() else ""
            elif os.path.isfile(_f):
                _src_t = _read(_f)
            else:
                _src_t = _f
            if not _src_t.strip():
                print("  الاستعمال: --soul check <ملفّ|نصّ>   أو  ... | "
                      "--soul check -", file=sys.stderr)
                sys.exit(2)
            _r = soul_check(_src_t)
            _print_soul_report(_r)
            sys.exit(0 if _r.get("ok") else 1)
        if sub == "test":
            print("  نوبةٌ حقيقيّةٌ ثمّ فحصٌ حتميٌّ لناتجها"
                  "   (نداءُ نموذجٍ واحد)\n")
            _q = next((a for a in argv[2:] if not a.startswith("-")), None)
            _r = soul_test(_q)
            if _r.get("measured") is False:
                print("  ⚠ لم يُقَس — النموذجُ لم يُجب، فلا حكمَ على شيء.\n")
                print("  السبب:")
                for _ln in str(_r.get("reason") or "").split("\n"):
                    print("    " + _ln)
                _why = str(_r.get("reason") or "").lower()
                if "billing" in _why or "credit" in _why or "balance" in _why:
                    print("\n  ⟵ رصيدُ المزوّد نفد. اشحنه ثمّ أعِد:"
                          "\n     https://openrouter.ai/credits")
                sys.exit(3)
            if _r.get("text"):
                print("  ── الناتج ──")
                for _ln in str(_r["text"])[:1400].split("\n"):
                    print("  " + _ln)
                print()
            _print_soul_report(_r)
            sys.exit(0 if _r.get("ok") else 1)
        st = soul_state()
        _lbl = {"weaver": "دستورُ Weaver Write", "openclaw": "قالبُ المحرّك",
                "weaver-edited": "دستورُنا + إضافاتُك",
                "custom": "مُحرَّرٌ بيدك", "missing": "غيرُ موجود"}
        print("  المُركَّب  : " + _lbl.get(st["which"], st["which"])
              + "   (%d حرفاً)" % st["chars"])
        print("  المسار   : " + st["path"])
        print("  المصدر   : " + SOUL_SRC
              + ("   (%d حرفاً)" % st["src_chars"] if st["src_ok"]
                 else "   ⚠ مفقود"))
        print("  احتياطيّة: " + ("موجودة" if st["backup"] else "لا"))
        print("  تلقائيّاً : " + ("نعم" if soul_on()
                                  else "لا (WEAVER_SOUL=off)"))
        if st["which"] != "weaver":
            print("\n  للتركيب:  python3 -m pipeline.weaver_core --soul apply")
        return
    if argv == ["--bootstrap"]:
        r = bootstrap_report()
        if r.get("error"):
            print("  تعذّر: " + str(r["error"])[:250], file=sys.stderr)
            sys.exit(1)
        print("  ما يدخل البرومبتَ في **كلِّ** نوبة — بدوالّ المحرّك\n")
        print("  المجلّد: " + str(r.get("workspace") or "—") + "\n")
        for f in r.get("files") or []:
            print("  %-14s %6d حرفاً  ≈%5d رمزاً   %s"
                  % (f.get("name"), f.get("injected") or 0,
                     f.get("tokens") or 0,
                     "مقصوص ⚠" if f.get("truncated") else ""))
        print("  " + "─" * 48)
        print("  %-14s %6d        ≈%5d رمزاً"
              % ("المجموع", r.get("totalChars") or 0,
                 r.get("totalTokens") or 0))
        for w in r.get("warnings") or []:
            print("  ⚠ " + str(w)[:200])
        return
    if argv[:1] == ["--seed-workspace"]:
        print("  بذرُ ملفّاتِ التمهيد بقوالب المحرّك نفسِه\n")
        r = seed_workspace()
        if r.get("error"):
            print("  ✗ " + str(r["error"])[:250], file=sys.stderr)
            sys.exit(1)
        print("  المجلّد : " + str(r.get("workspace") or "—"))
        for d in r.get("templateDirs") or []:
            print("  القوالب: " + str(d))
        print()
        for f in r.get("files") or []:
            _st = str(f.get("state") or "")
            print("  %-14s %s%s" % (f.get("name"), _st,
                                    ("  (%d بايت)" % f["bytes"])
                                    if f.get("bytes") else ""))
        print("\n  كُتب %d · موجودٌ سلفاً %d"
              % (r.get("created") or 0, r.get("existed") or 0))
        sys.exit(0 if r.get("ok") else 1)
    if argv[:1] == ["--tools-profile"]:
        _want = argv[1] if len(argv) > 1 else ""
        if _want not in ("lean", "full", "coding", "messaging"):
            print("  الاستعمال: --tools-profile <lean|coding|messaging|full>"
                  "\n\n  lean     المطلوبُ وحده — بحثٌ وملفّاتٌ وتنفيذٌ "
                  "ومتصفّحٌ وذاكرة   (≈4,884 رمزاً)"
                  "\n  coding   ملفُّ أوبن كلاو للبرمجة                      "
                  "  (≈14,828)"
                  "\n  full     الكاملُ كما يكتبه `onboard`                  "
                  "  (≈24,499)", file=sys.stderr)
            sys.exit(2)
        os.environ["WEAVER_TOOL_PROFILE"] = _want
        _p, _a = tools_policy()
        _tree = {}
        _merge(_tree, _nest("tools.profile", _p))
        _merge(_tree, _nest("tools.alsoAllow", _a))
        okp, why = config_patch(_tree)
        print(("  ✓ " if okp else "  ✗ ") + "tools.profile = " + _p
              + (("   ·   alsoAllow = " + ", ".join(_a)) if _a else "")
              + ("" if okp else "   — " + str(why)[:160]))
        if okp:
            _inv = tool_inventory()
            print("  ⟵ %d أداة  ≈ %d رمزاً في كلِّ رسالة"
                  % (len(_inv.get("tools") or []), _inv.get("tokens") or 0))
            print("\n  وتُثبَّت بلا هذا الأمر: WEAVER_TOOL_PROFILE=" + _want
                  + " في بيئتك")
        sys.exit(0 if okp else 1)
    if argv == ["--tools"]:
        inv = tool_inventory()
        if inv.get("error"):
            print("  تعذّر: " + inv["error"], file=sys.stderr)
            sys.exit(1)
        print("  الوكيل : " + (inv.get("agentId") or "—")
              + "   ·   ملفُّ الأدوات: " + (inv.get("profile") or "—"))
        print("  النموذج: " + (model_id() or "— غير محدَّد"))
        # الكلفةُ في كلِّ رسالة — وهي ما لم يكن يُقاس، فكانت الدقيقتان.
        if inv.get("chars"):
            print("  الكلفة : %d حرفاً  ≈ %d رمزاً في **كلِّ** رسالة"
                  % (inv["chars"], inv.get("tokens") or 0))
        for g in inv.get("groups") or []:
            print("\n  [%s] %s — %d" % (g.get("id"), g.get("label"),
                                         g.get("count") or 0))
            print("    " + ", ".join(g.get("tools") or []))
        print()
        for n in ("web_search", "web_fetch", "browser"):
            print("  %-12s %s" % (n, "حاضرة ✓" if n in (inv.get("tools") or [])
                                  else "غائبة ✗"))
        if not inv.get("web_search"):
            print("\n  وسببُ الغياب عند المحرّك: "
                  + (inv.get("suppressReason") or "غيرُ معروف"))
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
        _rt = engine_route()
        print("  الطريق   : " + {
            "bundled": "مزوّدٌ مدمجٌ في المحرّك (" + _rt.get("provider", "")
                       + ")",
            "custom": "مزوّدٌ مخصَّص «" + CUSTOM_PROVIDER + "» ⟵ "
                      + _rt.get("base_url", "") + "  [" + _rt.get("api", "")
                      + "]"}.get(_rt.get("mode"), "— " + _rt.get("why", "")))
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
            def _p(t):
                print("  " + str(t))
                sys.stdout.flush()
            ok, why = gateway_start(say=_p)
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
    if argv[:2] == ["--web-search", "test"]:
        _q = argv[2] if len(argv) > 2 else "الإعجاز العلمي في القرآن"
        print(f"  استعلام: {_q}\n  (نداءُ بحثٍ حقيقيٌّ بدوالّ المحرّك)\n")
        r = probe_search(_q)
        print("  المزوّدون المرئيّون : "
              + (", ".join(r.get("providers") or []) or "لا شيء"))
        print("  المختار            : " + (r.get("chosen") or "لا شيء"))
        print("  صالحٌ للاستعمال     : "
              + ("نعم" if r.get("usable") else "لا"))
        if r.get("ok"):
            _ms = r.get("tookMs") or 0
            print(f"\n  ✓ البحثُ يعمل — {r.get('count')} نتيجة"
                  + (f"  ({_ms/1000:.1f} ث)" if _ms else "")
                  + (f"  ·  {r.get('provider')}" if r.get("provider") else ""))
            if r.get("first"):
                print("    أوّلُ نتيجة: " + str(r["first"])[:120])
        else:
            print("\n  ✗ البحثُ لا يعمل")
            if r.get("error"):
                print("    السبب: " + str(r["error"])[:220])
            # يُعرض المعالجُ كلّما تعثّر البحثُ — سواءٌ لم يُختَر مزوّدٌ
            # أصلاً، أو اختِير ثمّ فشل (رصيدٌ نافد، أو حجبُ شبكة). فالمخرجُ
            # واحدٌ في الحالين: اختر مزوّداً آخر.
            if True:
                print("\n    ولاختيار المزوّد بنفسك — قائمةُ أوبن كلاو نفسُها،"
                      "\n    فيها المجّانيُّ والمدفوع:"
                      "\n      python3 -m pipeline.weaver_core --web-search choose"
                      "\n    أو ضَع مفتاحَك ثمّ أعِد تشغيل البوّابة:"
                      "\n      python3 -m pipeline.weaver_core --gateway stop"
                      "\n      python3 -m pipeline.weaver_core --gateway start")
        return
    if argv[:1] == ["--providers"]:
        rows = auth_catalog(refresh=("refresh" in argv))
        if not rows:
            print("  تعذّرت قراءةُ الكتالوج من المحرّك")
            return
        _by = {}
        for r in rows:
            _by.setdefault(r.get("providerId") or "?", []).append(r)
        print(f"  {len(rows)} خيارَ اعتماد · {len(_by)} مزوّداً"
              "   (من المحرّك، لا من قائمةٍ عندنا)\n")
        _mine = provider_id()
        for pid in sorted(_by):
            _mark = " ←" if pid == _mine else "  "
            print(f"{_mark} {pid:<22} "
                  + ", ".join(r["choice"] for r in _by[pid])[:74])
        if _mine:
            print("\n  مزوّدُك: " + _mine + "  ·  الخيار: "
                  + (auth_choice() or "غيرُ معروف"))
        return
    if argv[:1] == ["--onboard"]:
        _force = "--force" in argv
        print("  تهيئةُ أوبن كلاو الكاملة (auth · models · gateway ·"
              " workspace · skills)…")
        ok, why = onboard(force=_force)
        print(("  ✓ " if ok else "  ⚠ ") + str(why))
        if ok:
            # المعالجُ يضع `openrouter/auto`؛ نثبّت نموذجَك بعينه.
            for n, k, w in list(configure_runtime()) + list(configure_model()):
                print(("    ✓ " if k else "    ⚠ ") + n
                      + ("" if k else "   " + str(w)[:140]))
            if gateway_health():
                gateway_stop()
            _g, _w = gateway_start()
            print("    " + ("✓ البوّابة حيّة" if _g else "⚠ " + str(_w)[:120]))
        return
    if argv == ["--model"]:
        print("  في نظامك : " + (model_ref() or "لا شيء (config/.env)"))
        _rt = engine_route()
        if _rt.get("mode"):
            print("  الطريق   : " + _rt.get("why", "")
                  + ("  ⟵ " + _rt["base_url"] if _rt.get("mode") == "custom"
                     else ""))
        code, out, _ = run(["config", "get", "agents.defaults.model"],
                           timeout=60)
        print("  في المحرّك: "
              + ((out or "").strip().replace("\n", " ") if code == 0
                 else "غيرُ مضبوط"))
        print("\n  للضبط: python3 -m pipeline.weaver_core --model set")
        return
    if argv == ["--model", "set"]:
        for n, ok, why in list(configure_runtime()) + list(configure_model()):
            print(("  ✓ " if ok else "  ⚠ ") + n
                  + ("" if ok else "   " + str(why)[:160]))
        if gateway_health():
            print("  ⇒ إعادةُ تشغيل البوّابة لتقرأه…")
            gateway_stop()
            ok, why = gateway_start()
            print("    " + ("✓ حيّة" if ok else "⚠ " + str(why)[:120]))
        return
    if argv[:2] == ["--web-search", "choose"]:
        # معالجُ المحرّك نفسُه. وإن لم تكن الطرفيّةُ تفاعليّةً قال هو ذلك
        # ودلّ على البديل غير التفاعليّ — فلا نكرّر كلامه.
        sys.exit(configure_web())
    if argv == ["--web-search", "ddg"]:
        # تعيينٌ صريح: يجعل duckduckgo هو المزوّد، فيعمل البحثُ بلا مفتاح.
        code, out, err = run(["config", "set",
                              "tools.web.search.provider", "duckduckgo"],
                             timeout=90)
        print("  " + ("✓ المزوّد = duckduckgo" if code == 0
                      else "⚠ تعذّر: " + (_real_error(err) or "")[:160]))
        return
    if argv == ["--web-search"]:
        if not (available() and node_bin()):
            print(why_unavailable(), file=sys.stderr)
            sys.exit(2)
        print("  تركيبُ مزوّدي البحثِ من كتالوج أوبن كلاو…")
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
