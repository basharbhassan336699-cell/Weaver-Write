# -*- coding: utf-8 -*-
"""إصلاحان:

١ نصٌّ داخليٌّ من المنصّة تسرّب في المسار المباشر (مقيسٌ على جهاز المستخدم):
    «Hello! How can<ds_safety>[用户未成年]否 …</ds_safety>Safe»
  ⟵ يُحذف الوسمُ وحده، ولا يُمَسّ غيرُه.

٢ حفظُ المفتاح بلا اختيار نموذج كان يعطي افتراضياً قديماً (gpt-4o …)
  ⟵ أحدثُ نموذجِ محادثةٍ حين تعلن المنصّةُ التواريخ؛ وإلّا كما كان حرفاً.
"""
import io
import json
import os
import pathlib
import sys
import tempfile
import threading
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "web"))

import server as S                        # noqa: E402
from config import keysync as K          # noqa: E402
from config import providers as PV       # noqa: E402

P = F = 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  ✓ {name}")
    else:
        F += 1
        print(f"  ✗ {name}" + (f"   — {extra}" if extra else ""))


print("\n— ١ حذفُ النصّ المتسرّب —")
_LEAK = ("Hello! How can<ds_safety>[用户未成年]否 [分类]其他 [判定]用户仅发送问候，"
         "无任何实质内容。[规则]无</ds_safety>Safe")
ok("ما رآه المستخدم ⟵ بلا الوسم ولا «Safe»",
   S._strip_leaked(_LEAK) == "Hello! How can", repr(S._strip_leaked(_LEAK)))
ok("في وسط النصّ ⟵ يُحذف ويبقى ما حوله",
   S._strip_leaked("مرحباً<ds_safety>x</ds_safety> كيف أساعدك؟")
   == "مرحباً كيف أساعدك؟")
ok("وسمٌ غيرُ مغلق ⟵ يُحذف إلى آخر النصّ",
   S._strip_leaked("جواب<ds_safety>[分类]") == "جواب")
ok("«Safe» في نصٍّ عاديّ لا تُمَسّ", S._strip_leaked("Safe travels")
   == "Safe travels")
ok("وسومٌ أخرى لا تُمَسّ", S._strip_leaked("نص <b>x</b> <think>y</think>")
   == "نص <b>x</b> <think>y</think>")
ok("نصٌّ بلا وسم ⟵ كما هو حرفاً (حتى الفراغُ الأخير)",
   S._strip_leaked("جواب عاديّ  \n") == "جواب عاديّ  \n")
ok("فراغٌ وNone لا يكسران", S._strip_leaked("") == ""
   and S._strip_leaked(None) is None)

# المسارُ المباشرُ نفسُه: نداءٌ مزيّفٌ يعيد ما رآه المستخدم.
_real_gs, _real_open = K.get_settings, urllib.request.urlopen
S.keysync.get_settings = lambda: {
    "WEAVER_API_KEY": "sk-x", "WEAVER_BASE_URL": "https://api.deepseek.com",
    "WEAVER_MODEL": "deepseek-chat", "WEAVER_PROVIDER": "deepseek"}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_open(req, timeout=None):
    body = {"choices": [{"message": {"content": _LEAK},
                         "finish_reason": "stop"}]}
    return _Resp(json.dumps(body).encode())


urllib.request.urlopen = _fake_open
try:
    r = S._chat_direct("مرحبا")
    ok("_chat_direct يعيد الجوابَ نظيفاً", r.get("reply") == "Hello! How can",
       repr(r)[:200])
finally:
    S.keysync.get_settings = _real_gs
    urllib.request.urlopen = _real_open

print("\n— ٢ أحدثُ نموذجِ محادثة —")
_OPENAI = {"data": [
    {"id": "gpt-4o", "created": 1715000000},
    {"id": "gpt-5.1", "created": 1760000000},
    {"id": "gpt-5.2-preview", "created": 1790000000},
    {"id": "text-embedding-4", "created": 1795000000},
    {"id": "gpt-image-2", "created": 1796000000},
    {"id": "tts-2", "created": 1797000000},
    {"id": "whisper-2", "created": 1798000000},
]}


def _get(data, err=None):
    calls = []

    def g(url, headers, timeout):
        calls.append((url, headers))
        return (None, err) if err else (data, None)
    g.calls = calls
    return g


g = _get(_OPENAI)
m = PV.newest_chat_model("https://api.openai.com/v1", "sk-proj-1",
                         default="gpt-4o", http_get=g)
ok("مؤرَّخة ⟵ أحدثُ نموذجِ محادثةٍ مستقرّ (لا تضمين ولا صوت ولا صور)",
   m == "gpt-5.1", m)
ok("  ⟵ وبمفتاح المستخدم في الترويسة",
   g.calls and g.calls[0][1].get("Authorization") == "Bearer sk-proj-1")
ok("كلُّها معاينات ⟵ أحدثُها",
   PV.newest_chat_model("u", "k", http_get=_get({"data": [
       {"id": "a-preview", "created": 1}, {"id": "b-preview", "created": 2}]}))
   == "b-preview")
_UND = {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}
ok("بلا تواريخ ⟵ الافتراضيُّ كما كان",
   PV.newest_chat_model("u", "k", default="deepseek-chat",
                        http_get=_get(_UND)) == "deepseek-chat")
ok("فشلُ الاتّصال ⟵ الافتراضيُّ كما كان",
   PV.newest_chat_model("u", "k", default="gpt-4o",
                        http_get=_get(None, "HTTP 401")) == "gpt-4o")
ok("استثناءٌ داخل الجلب ⟵ لا يرفع",
   PV.newest_chat_model("u", "k", default="d",
                        http_get=lambda *a: 1 / 0) == "d")

# _newest_model_for: لا يعيد إلا ما اكتُشف فعلاً — وإلّا "" (السلوكُ القديم).
_real_nm = PV.newest_chat_model
PV.newest_chat_model = lambda b, k, a="bearer", default="", **kw: "gpt-5.1"
ok("مفتاح OpenAI ⟵ gpt-5.1",
   S._newest_model_for("sk-proj-1") == "gpt-5.1")
PV.newest_chat_model = lambda b, k, a="bearer", default="", **kw: default
ok("رجع الافتراضيّ ⟵ \"\" فيقرّر set_api_key كما كان",
   S._newest_model_for("sk-proj-1") == "")
ok("لا منصّةَ معروفة ولا رابط ⟵ \"\"", S._newest_model_for("zzz") == "")
_seen = {}


def _spy(b, k, a="bearer", default="", **kw):
    _seen.update(base=b, auth=a, default=default)
    return "x-new"


PV.newest_chat_model = _spy
S._newest_model_for("k-no-prefix", provider="deepseek")
ok("المنصّةُ من القائمة حين لا بادئة ⟵ رابطُها", _seen.get("base")
   == "https://api.deepseek.com/v1", str(_seen))
S._newest_model_for("sk-ant-1")
ok("أنثروبيك ⟵ بترويسة x-api-key", _seen.get("auth") == "x-api-key")
_seen.clear()
ok("OpenRouter (مجمِّع) ⟵ \"\" بلا نداء: افتراضيُّه كما كان",
   S._newest_model_for("sk-or-v1-x") == "" and not _seen)
ok("Groq برابطه ⟵ كذلك", S._newest_model_for(
    "k", base_url="https://api.groq.com/openai/v1") == "" and not _seen)
PV.newest_chat_model = _real_nm

print("\n— POST /api/settings —")
_TMP = pathlib.Path(tempfile.mkdtemp())
_real_env = (K._ENV_FILE, K._CONF_DIR)
_saved = {k: os.environ.get(k) for k in K.SYNC_KEYS}
K._CONF_DIR, K._ENV_FILE = _TMP, _TMP / ".env"
K._ENV_FILE.write_text("", encoding="utf-8")
srv = S._ReuseTCPServer(("127.0.0.1", 0), S.Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def post(body):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/settings" % port,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


_real_nmf = S._newest_model_for
try:
    S._newest_model_for = lambda k, p="", b="": "gpt-5.1"
    post({"api_key": "sk-proj-abc", "provider": "", "base_url": "",
          "model": ""})
    env = K._ENV_FILE.read_text()
    ok("بلا اختيار ⟵ أحدثُ نموذج", "WEAVER_MODEL=gpt-5.1" in env, env)
    S._newest_model_for = lambda k, p="", b="": 1 / 0
    post({"api_key": "sk-proj-abc", "provider": "", "base_url": "",
          "model": "gpt-4.1"})
    env = K._ENV_FILE.read_text()
    ok("اختار نموذجاً ⟵ اختيارُه، ولا نداءَ اكتشاف",
       "WEAVER_MODEL=gpt-4.1" in env, env)
    S._newest_model_for = lambda k, p="", b="": ""
    post({"api_key": "sk-proj-abc", "provider": "", "base_url": "",
          "model": ""})
    env = K._ENV_FILE.read_text()
    ok("فشل الاكتشاف ⟵ الافتراضيُّ كما كان", "WEAVER_MODEL=gpt-4o" in env,
       env)
finally:
    S._newest_model_for = _real_nmf
    srv.shutdown()
    K._ENV_FILE, K._CONF_DIR = _real_env
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

print("\n" + "=" * 62)
print(f" RESULT: {'PASS' if F == 0 else 'FAIL'}   ({P}/{P + F})")
print("=" * 62)
sys.exit(1 if F else 0)
