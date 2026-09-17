# -*- coding: utf-8 -*-
"""
pipeline/model_build.py
=======================
النموذج يبني الملفّ بنفسه — بدل أن يملأ فراغاتٍ في بايثون مكتوبةٍ سلفاً.

لماذا
-----
كلُّ ما يُصدّره هذا النظام تبنيه بايثون كُتبت قبل أن يُطلب الطلب، فسقفُ أيّ
مستندٍ هو ما خطر ببال كاتبها. «اجعل التصميم احترافياً» لا يجد يداً تنفّذه،
وقالبُ ترقيمٍ لم يُبرمَج يسقط على الأرض، وكلُّ صيغةٍ جديدة تحتاج ملفَّ بايثون
جديداً — فيعود المستخدم إلى دائرةٍ من الترقيع بلا نهاية.

والقياس على حزمة openclaw (65 ميجا، 10616 ملفاً): لا مهارةَ باوربوينت ولا
إكسل ولا مراجع — صفرٌ بحدود الكلمة — وتُنتجها كلَّها، لأن النموذج يملك
`exec` فيكتب السكربت ويشغّله ويقرأ خطأه ويصلحه. أقوى ما في النموذج أنه
يبرمج؛ وبلا يدٍ لا يستطيع أن يستعمل ذلك.

كيف
---
يُسلَّم النموذجُ محتوى المستند (JSON) وطلبَ المستخدم حرفياً، ويُطلب منه سكربتٌ
ينتج الملفّ. السكربتُ **يُحفظ على القرص أولاً** بجوار المخرَج، ثم — وفقط حين
يكون المستخدم قد أذِن بـWEAVER_EXEC=1 — يُشغَّل. يفشل؟ يعود الخطأ إليه
ليصلحه، ثلاثَ محاولاتٍ على الأكثر. لم ينجح؟ المُصدِّر المعتاد يعمل كما كان.

الحدود
------
* مطفأٌ افتراضياً: بلا WEAVER_EXEC لا يُشغَّل شيء — يُكتب السكربتُ فقط ليقرأه
  المستخدم ويشغّله بيده إن شاء.
* السكربتُ محفوظٌ دائماً قبل التشغيل، فلا ينفَّذ شيءٌ بلا أثرٍ يُراجَع.
* المهلة والدليلُ المؤقّت وفحصُ الأوامر المدمّرة كلُّها في tool_exec_python.
* الفشلُ لا يضرّ: المخرَجُ القائم لا يُمَسّ إلا عند نجاحٍ مُتحقَّقٍ منه.
"""
from __future__ import annotations

MAX_ATTEMPTS = 3


def _strip_code_fence(text):
    """أزِل سياج الماركداون حول الكود إن وضعه النموذج."""
    try:
        import re
        t = str(text or "").strip()
        m = re.search(r"```(?:python|py)?\s*\n(.*?)```", t, re.S)
        return (m.group(1) if m else t).strip()
    except Exception:
        return str(text or "")


def build_payload(sections, card, lang="ar"):
    """محتوى المستند كما يراه السكربت — JSON واحدٌ لا لبس فيه."""
    import json
    secs = []
    for x in (sections or []):
        if not isinstance(x, dict):
            continue
        secs.append({"heading": x.get("heading", "") or "",
                     "body": x.get("body", "") or "",
                     "level": int(x.get("level", 1) or 1)})
    return json.dumps({
        "title": (card or {}).get("topic") or "",
        "language": lang,
        "citation_style": (card or {}).get("citation_style") or "",
        "sections": secs,
    }, ensure_ascii=False, indent=1)


def build_prompt(request_text, out_ext, lang="ar", error=None):
    """الطلبُ الموجَّه إلى النموذج. طلبُ المستخدم يُنقل حرفياً، وفوق كلّ ما دونه."""
    req = " ".join(str(request_text or "").split())
    if lang == "en":
        base = (
            f"Write a Python script that produces the final .{out_ext} file.\n\n"
            f"THE USER'S REQUEST, VERBATIM — it outranks everything below:\n"
            f"«{req}»\n\n"
            "Available in the environment:\n"
            "- WEAVER_PAYLOAD: path to a JSON file "
            "{title, language, citation_style, sections:[{heading, body, "
            "level}]}\n"
            "- WEAVER_OUT: the path you must save the file to\n\n"
            "Rules:\n"
            "- Use python-docx / python-pptx / openpyxl as the format needs.\n"
            "- Honour the user's numbering, formatting, tables and direction.\n"
            "- Never invent content that is not in the JSON.\n"
            "- Forbidden: subprocess, os.system, sockets, deleting anything "
            "outside the working directory.\n"
            "- Return ONLY the code. No prose, no markdown fences.")
    else:
        base = (
            f"اكتب سكربت بايثون يبني ملفّ ‎.{out_ext}‎ النهائيّ.\n\n"
            f"طلبُ المستخدم حرفياً — وهو فوق كلّ ما دونه:\n«{req}»\n\n"
            "ما تجده في بيئة التشغيل:\n"
            "- WEAVER_PAYLOAD: مسارُ ملفّ JSON فيه "
            "{title, language, citation_style, sections:[{heading, body, "
            "level}]}\n"
            "- WEAVER_OUT: المسارُ الذي يجب أن تحفظ فيه الملفّ\n\n"
            "قواعد:\n"
            "- استعمل python-docx / python-pptx / openpyxl بحسب الصيغة.\n"
            "- احترم ترقيم المستخدم وتنسيقه وجداوله واتجاه النصّ "
            "(العربيّ من اليمين).\n"
            "- لا تخترع محتوىً ليس في JSON.\n"
            "- ممنوع: subprocess، os.system، الشبكة، وأيّ حذفٍ خارج دليل العمل.\n"
            "- أعِد الكود وحده، بلا شرحٍ ولا علامات ماركداون.")
    if error:
        tail = ("\n\nThe previous attempt failed. Reason:\n"
                if lang == "en" else
                "\n\nالمحاولة السابقة فشلت. السبب:\n")
        fix = ("\nFix it and return the complete code again."
               if lang == "en" else
               "\nأصلحه وأعِد الكود كاملاً.")
        base += tail + str(error)[:1500] + fix
    return base


def script_path_for(out_path):
    """أين يُحفظ سكربتُ النموذج — بجوار المخرَج، باسمٍ مقروء."""
    import os
    d = os.path.dirname(out_path) or "."
    stem = os.path.splitext(os.path.basename(out_path))[0]
    return os.path.join(d, f"build_{stem}.py")


def build_with_model(llm_fn, sections, card, lang, out_path,
                     request_text="", system=None, on_status=None):
    """اطلب من النموذج سكربتاً، احفظه، وشغّله إن أذِن المستخدم.

    → dict: {"ok", "path", "script", "attempts", "reason", "ran"}
    لا يرفع استثناءً أبداً؛ وعند أيّ إخفاقٍ يعود ok=False فيبقى المُصدِّر
    المعتاد هو من يبني الملفّ."""
    res = {"ok": False, "path": None, "script": None, "attempts": 0,
           "reason": "", "ran": False}
    try:
        import os
        from capabilities.tools.tool_exec_python import (
            run_python, exec_enabled)
    except Exception as e:
        res["reason"] = f"تعذّر تحميل المنفّذ: {e}"
        return res
    if not llm_fn:
        res["reason"] = "لا نموذج"
        return res
    if not (sections or []):
        res["reason"] = "لا محتوى"
        return res

    payload = build_payload(sections, card, lang)
    ext = os.path.splitext(out_path)[1].lstrip(".") or "docx"
    spath = script_path_for(out_path)
    err = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        res["attempts"] = attempt
        try:
            code = llm_fn(build_prompt(request_text, ext, lang, err),
                          system=system, temperature=0.2,
                          max_tokens=3000) or ""
        except Exception as e:
            res["reason"] = f"نداء النموذج فشل: {e}"
            return res
        code = _strip_code_fence(code)
        if not code.strip():
            err = "أعاد النموذجُ نصّاً فارغاً"
            continue
        # THE SCRIPT IS WRITTEN BEFORE IT IS RUN — always, and whether or not
        # execution is enabled. Nothing this system runs is invisible: the user
        # can open the file, read exactly what was going to run, and run it
        # themselves. That audit trail is the point, not a formality.
        try:
            with open(spath, "w", encoding="utf-8") as fh:
                fh.write(code)
            res["script"] = spath
        except Exception:
            pass
        if not exec_enabled():
            res["reason"] = ("التنفيذ مطفأ — حُفظ السكربت ليقرأه المستخدم "
                             "ويشغّله بنفسه")
            return res
        if on_status:
            try:
                on_status(f"بناء الملفّ بالنموذج — محاولة {attempt}")
            except Exception:
                pass
        r = run_python(code, out_path, payload)
        res["ran"] = True
        if r.get("ok"):
            res["ok"] = True
            res["path"] = out_path
            return res
        err = (r.get("reason") or "") + "\n" + (r.get("stderr") or "")
        res["reason"] = str(err)[:300]
    return res
