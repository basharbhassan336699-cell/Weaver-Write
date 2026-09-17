# -*- coding: utf-8 -*-
"""الوكيلُ العامّ: أيُّ سؤالٍ، بأيّ صياغة — يفهم، ويستعمل ما يلزم، ويردّ.

لا طبقات. لا أنبوب. لا تصنيفَ نيّةٍ ولا قائمةَ عبارات. حلقةُ أوبن كلاو
(`pipeline/agent_loop.py`) وعُدَّتُه الأساسية (`pipeline/agent_tools.py`)،
والنموذجُ يقرّر كلَّ شيء: أيحتاج أداةً أم يجيب مباشرة، وأيَّ أداة، ومتى
انتهى.

هذا هو الفرق كلُّه عن المسار القديم: هناك كان الكودُ يقرّر مسبقاً أنّ هذا
«بحثٌ أكاديميّ» فيُجري إحدى عشرة مرحلةً مهما كان السؤال؛ وهنا لا يُقرَّر شيءٌ
مسبقاً. «كم عمر الأرض؟» يُجاب مباشرةً بلا أداة، و«جِد لي تسعة مراجع» تدور
له الحلقةُ حتى تكتمل — والقرارُ للنموذج في الحالتين.

    python3 -m pipeline.agent "سؤالك هنا"
    python3 -m pipeline.agent            # وضعُ المحادثة

بيئياً:
    WEAVER_AGENT_STEPS   سقفُ الخطوات المطلق (افتراضياً ٢٤)
    WEAVER_EXEC=1        يُتيح أداةَ exec (مطفأةٌ بدونه)
    WEAVER_AGENT_RO=1    قراءةٌ فقط: بلا write/edit
"""

import os
import sys

SYSTEM_AR = (
    "أنت مساعدٌ عامٌّ ذكيّ. تفهم ما يُطلب منك مهما كانت صياغتُه، وتردّ "
    "بذكاءٍ ووضوح.\n\n"
    "- إن كان الجوابُ عندك فأجب مباشرةً ولا تستعمل أداةً بلا حاجة.\n"
    "- وإن لزمك أن ترى شيئاً حقيقياً — صفحةً، أو ملفّاً، أو نتيجةَ أمرٍ — "
    "فاستعمل الأداةَ المناسبة، ولك أن تطلب عدّةَ أدواتٍ معاً فتُنفَّذ في آن.\n"
    "- ولا تقل إنك فعلتَ شيئاً لم تفعله، ولا تخترع مصدراً ولا رقماً. وإن "
    "تعذّر عليك شيءٌ فقل ما تعذّر ولماذا.\n"
    "- وإن عادت أداةٌ بخطأ فاقرأه وغيّر طريقك، ولا تُعِد النداءَ نفسَه.\n"
    "- أجب بلغة السائل، وبإيجازٍ يكفي ولا يزيد.")

SYSTEM_EN = (
    "You are a general, capable assistant. Understand what is asked however "
    "it is phrased, and answer clearly.\n\n"
    "- If you know the answer, answer directly; do not use a tool you do not "
    "need.\n"
    "- If you need to see something real — a page, a file, the output of a "
    "command — use the right tool. Several tools may be requested at once and "
    "they run in parallel.\n"
    "- Never claim to have done something you did not do, and never invent a "
    "source or a number. If something fails, say what failed and why.\n"
    "- If a tool returns an error, read it and change approach; do not repeat "
    "the same call.\n"
    "- Answer in the asker's language, briefly enough and no more.")


def _is_ar(text):
    for ch in str(text or "")[:400]:
        if "؀" <= ch <= "ۿ":
            return True
    return False


def _orchestrator():
    """المُنسِّقُ إن أمكن — يمنح web_fetch مسارَ UniWeb الذي يتجاوز الحجب.
    وغيابُه لا يمنع شيئاً: تعمل الأدواتُ بالمسار المباشر."""
    try:
        from pipeline.orchestrator import WeaverOrchestrator
        return WeaverOrchestrator.__new__(WeaverOrchestrator)
    except Exception:
        return None


def build(llm_fn=None, lang=None, orch=None):
    """(llm_fn, tools, system) — العُدّةُ جاهزةً للحلقة."""
    from pipeline.agent_tools import core_tools
    if llm_fn is None:
        try:
            from core.llm import get_llm_fn
            llm_fn = get_llm_fn()
        except Exception:
            llm_fn = None
    if orch is None:
        orch = _orchestrator()
    ro = (os.environ.get("WEAVER_AGENT_RO", "") or "").strip() == "1"
    tools = core_tools(orch, allow_write=not ro)
    system = SYSTEM_EN if lang == "en" else SYSTEM_AR
    return llm_fn, tools, system


def ask(request, llm_fn=None, lang=None, on_event=None, history=None):
    """اسأل أيَّ شيء. يُعيد {"answer", "steps", "stopped_by", "messages"}."""
    from pipeline.agent_loop import run_agent
    lang = lang or ("ar" if _is_ar(request) else "en")
    llm_fn, tools, system = build(llm_fn, lang)
    if not llm_fn:
        return {"answer": "", "steps": 0, "stopped_by": "no_model",
                "messages": []}
    steps = 24
    try:
        steps = int(os.environ.get("WEAVER_AGENT_STEPS") or 24)
    except Exception:
        pass
    task = str(request or "")
    if history:
        task = ("سياقُ المحادثة:\n" + str(history)[-4000:]
                + "\n\nالطلبُ الآن:\n" + task) if lang == "ar" else (
            "Conversation so far:\n" + str(history)[-4000:]
            + "\n\nNow:\n" + task)
    return run_agent(llm_fn, task, tools, system=system, lang=lang,
                     max_steps=max(1, steps), on_event=on_event)


def _cli():
    def ev(e):
        if e.get("type") == "tool_start":
            a = str(e.get("arguments") or "")[:90]
            print(f"  ⚙  {e['name']}  {a}", file=sys.stderr)
        elif e.get("type") == "tool_end":
            mark = "✗" if e.get("is_error") else "✓"
            print(f"  {mark}  {e['name']}  ({e.get('chars', 0)} حرفاً)",
                  file=sys.stderr)

    args = sys.argv[1:]
    if args:
        r = ask(" ".join(args), on_event=ev)
        print("\n" + (r["answer"] or "(بلا جواب)"))
        print(f"\n— {r['steps']} خطوة · توقّف: {r['stopped_by']}",
              file=sys.stderr)
        return
    print("وضعُ المحادثة. اكتب سؤالك، أو «خروج».", file=sys.stderr)
    hist = []
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return
        if q in ("خروج", "exit", "quit", ""):
            return
        r = ask(q, on_event=ev, history="\n".join(hist[-6:]) or None)
        print("\n" + (r["answer"] or "(بلا جواب)"))
        hist += [f"س: {q}", f"ج: {r['answer'][:400]}"]


if __name__ == "__main__":
    _cli()
