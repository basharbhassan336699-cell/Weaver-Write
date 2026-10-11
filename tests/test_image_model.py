"""نموذجُ صورٍ منفصلٌ على المنصّة نفسِها (WEAVER_IMAGE_MODEL).

    python3 tests/test_image_model.py

قِيس على هاتف المستخدم (tools/test_vision.py، مفتاحُه نفسُه):
    deepseek-v4-pro               صورةٌ حمراءُ وزرقاء ⟵ «White» و«White»
    deepseek-v4-flash-vision-exp  ⟵ «Red» و«Blue»
وقِيس هنا على المحرّك الحقيقيّ بمزوّدٍ وهميّ: النموذجُ الرئيسيُّ لا تصله الصورة
ويستدعي view_image، ونموذجُ الصور تصله الصورةُ ويصفها، والوصفُ يعود للرئيسيّ.
وهنا ما يُفحص بلا محرّك: الإعدادُ المكتوب، وأنّ غيابَ الإعداد لا يغيّر شيئاً.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))

from pipeline import weaver_core as W  # noqa: E402

FAILS = []
BASE = {"WEAVER_MODEL": "deepseek-v4-pro",
        "WEAVER_BASE_URL": "https://api.deepseek.com/v1",
        "WEAVER_API_KEY": "sk-test", "WEAVER_PROVIDER": "deepseek"}


def check(name, cond):
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        FAILS.append(name)


def with_settings(extra, fn):
    saved = W._load_settings
    s = dict(BASE)
    s.update(extra)
    W._load_settings = lambda: dict(s)
    try:
        return fn()
    finally:
        W._load_settings = saved


def models_of(tree):
    return tree["models"]["providers"][W.CUSTOM_PROVIDER]["models"]


def main():
    # بلا إعداد: كما كان حرفاً
    t0 = with_settings({}, W.custom_provider_tree)
    check("بلا إعداد: نموذجٌ واحدٌ كما كان", len(models_of(t0)) == 1)
    check("بلا إعداد: لا image_model_id", with_settings({}, W.image_model_id) == "")
    fp0 = with_settings({}, W._model_fingerprint)
    check("بلا إعداد: البصمةُ بلا image", "image" not in fp0 and
          "image:" not in fp0["boot"])
    _, allow0 = with_settings({}, W.tools_policy)
    check("بلا إعداد: لا view_image في الأدوات", "view_image" not in allow0)

    img = {"WEAVER_IMAGE_MODEL": "deepseek-v4-flash-vision-exp"}
    t1 = with_settings(img, W.custom_provider_tree)
    ms = models_of(t1)
    check("مع الإعداد: نموذجان", [m["id"] for m in ms] ==
          ["deepseek-v4-pro", "deepseek-v4-flash-vision-exp"])
    check("الرئيسيُّ نصّيّ (لا تُرسَل إليه صورٌ لا يراها)", ms[0]["input"] == ["text"])
    check("نموذجُ الصور يُعلَن بالصور", ms[1]["input"] == ["text", "image"])
    v_on = dict(img, WEAVER_MODEL_VISION="on")
    check("ومع WEAVER_MODEL_VISION=on: الرئيسيُّ يبقى نصّيّاً",
          models_of(with_settings(v_on, W.custom_provider_tree))[0]["input"] == ["text"])
    fp1 = with_settings(img, W._model_fingerprint)
    check("البصمة: تغييرُه يعيد الكتابةَ والإقلاع",
          fp1.get("image") == "deepseek-v4-flash-vision-exp" and
          "image:deepseek-v4-flash-vision-exp" in fp1["boot"])
    _, allow1 = with_settings(img, W.tools_policy)
    check("view_image في الأدوات (وإلّا لم يرَها النموذج تحت minimal)",
          "view_image" in allow1)
    check("الاسمُ ببادئة weaver/ يُقبل",
          with_settings({"WEAVER_IMAGE_MODEL": "weaver/vis"}, W.image_model_id) == "vis")
    check("الاسمُ نفسُه للرئيسيّ ⟵ لا نموذجَ ثانٍ",
          with_settings({"WEAVER_IMAGE_MODEL": "deepseek-v4-pro"}, W.image_model_id) == "")

    # configure_model: الكتابةُ والحذف
    seen = {}
    saved = (W.config_has, W.config_patch, W._applied_fingerprint, W._save_fingerprint,
             W.credentials)
    try:
        W.config_has = lambda tree, exact_paths=(): False
        W.config_patch = lambda tree, replace_paths=(): (seen.__setitem__("t", tree)
                                                         or (True, ""))
        W._save_fingerprint = lambda fp: None
        W.credentials = lambda: {}
        W._applied_fingerprint = lambda: {}
        with_settings(img, W.configure_model)
        im = seen["t"]["agents"]["defaults"].get("imageModel")
        check("configure_model: imageModel.primary = weaver/<نموذج الصور>",
              im == {"primary": "weaver/deepseek-v4-flash-vision-exp"})
        W._applied_fingerprint = lambda: {"image": "deepseek-v4-flash-vision-exp"}
        with_settings({}, W.configure_model)
        check("أُزيل الإعداد ⟵ imageModel يُحذف (null)",
              "imageModel" in seen["t"]["agents"]["defaults"] and
              seen["t"]["agents"]["defaults"]["imageModel"] is None)
        W._applied_fingerprint = lambda: {}
        with_settings({}, W.configure_model)
        check("لم يُضبط قطّ ⟵ لا ذكرَ لـimageModel",
              "imageModel" not in seen["t"]["agents"]["defaults"])
    finally:
        (W.config_has, W.config_patch, W._applied_fingerprint, W._save_fingerprint,
         W.credentials) = saved

    # ملاحظةُ المرفق في الخادم
    import server as S
    saved_im = W.image_model_id
    try:
        W.image_model_id = lambda route=None: ""
        txt0, _ = S._attach_extract([{"name": "x.png", "text": ""}])
        check("بلا نموذج صور: ملاحظةُ المرفق كما كانت", "يحتاج نموذج رؤية" in txt0)
        W.image_model_id = lambda route=None: "vis"
        txt1, _ = S._attach_extract([{"name": "x.png", "text": ""}])
        check("مع نموذج صور: الملاحظةُ تدلّ على view_image", "view_image" in txt1)
    finally:
        W.image_model_id = saved_im

    src = open(os.path.join(ROOT, "tools", "test_vision.py"), encoding="utf-8").read()
    check("tools/test_vision.py --model", '"--model" in sys.argv' in src)


if __name__ == "__main__":
    print("image model (WEAVER_IMAGE_MODEL)")
    main()
    print("FAIL: " + ", ".join(FAILS) if FAILS else "PASS")
    sys.exit(1 if FAILS else 0)
