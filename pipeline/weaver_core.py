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
import subprocess
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
    for it in (data.get("payloads") or []):
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


def ask(text, timeout=300, cwd=None, fallback=True):
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
        args = ["agent", "exec", str(text or ""), "--json",
                "--timeout", str(max(30, int(timeout) - 20))]
        _m = model_id()
        if _m:
            # بلا هذا يسقط المحرّكُ إلى نموذجه الافتراضيّ (openai/…) ثمّ
            # يفشل بـauth — وهو بالضبط ما رآه المستخدم.
            args += ["--model", _m]
        if cwd:
            args += ["--cwd", str(cwd)]
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
