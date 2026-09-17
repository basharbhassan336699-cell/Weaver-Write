# -*- coding: utf-8 -*-
"""حلقةُ الوكيل — منقولةٌ من برمجة أوبن كلاو، لا مُستوحاةٌ منها.

المصدرُ الذي نُقل عنه، ملفاً وسطراً، حتى يُراجَع:

    openclaw/dist/agent-core-B_87jlHI.mjs:541
        while (true) {
          let hasMoreToolCalls = true;
          while (hasMoreToolCalls || pendingMessages.length > 0) {
            ...
            hasMoreToolCalls = streamed.continuationRequired
                 || (executedToolBatch !== void 0 && !executedToolBatch.terminate);

    openclaw/dist/agent-core-B_87jlHI.mjs:711  executeToolCalls
    openclaw/dist/agent-core-B_87jlHI.mjs:770  executeToolCallGroups
    openclaw/dist/tool-loop-detection-CJSZExqJ.mjs:501  detectToolCallLoop
    openclaw/dist/tool-loop-detection-CJSZExqJ.mjs:215  CRITICAL_THRESHOLD = 20
    openclaw/dist/tool-loop-detection-CJSZExqJ.mjs:216  GLOBAL_CIRCUIT_BREAKER_THRESHOLD = 30

الفكرةُ كلُّها: الحلقةُ لا تقف إلا حين يتوقّف **النموذجُ** عن طلب أداة. لا
عدّادَ خطواتٍ يحكم، ولا خطّةً مكتوبةً في الكود، ولا مرحلةً تجري مرّةً واحدةً
ثمّ تُسلِّم ما عاد. يطلب أداةً ⟶ تُنفَّذ ⟶ تعود النتيجةُ إليه ⟶ يقرّر: أعيد
أم انتهيت.

انحرافٌ واحدٌ مفروض، أقوله صراحةً: أوبن كلاو يستعمل واجهةَ استدعاءِ أدواتٍ
أصليّةً في المزوّد (`content: [{type:"toolCall"}]`)، و`core.llm` هنا لا تُصدِّر
إلا نصّاً. فنداءُ الأداة يمرّ عبر JSON في نصّ الردّ. الآليةُ هي هي؛ الأنبوبُ
الذي تمرّ فيه مختلف، وهذا حدُّ ما تسمح به الواجهةُ الموجودة.

كلُّ شيءٍ هنا آمنُ التدهور: بلا نموذجٍ لا تدور الحلقةُ أصلاً، وأيُّ خطأٍ في
أداةٍ يعود إلى النموذج كنتيجةٍ لا كانهيار."""

import json
import hashlib

# tool-loop-detection-CJSZExqJ.mjs:215-216 — العتباتُ بأرقامها كما هي
WARNING_THRESHOLD = 10
CRITICAL_THRESHOLD = 20
GLOBAL_CIRCUIT_BREAKER_THRESHOLD = 30

# agent-core-B_87jlHI.mjs:443
TOOL_LOOP_RECOVERY_TERMINATED_MESSAGE = (
    "Stopped this run because tool-loop recovery encountered another critical "
    "loop. No blocked tool action was executed.")

MAX_STEPS = 24          # سقفٌ أعلى مطلق، لا آليةُ التوقّف


class Tool:
    """أداةٌ واحدة، بالشكل الذي يقرؤه النموذج في أوبن كلاو: اسمٌ ووصفٌ ومخطَّط.

    `execute(args)` تُعيد نصّاً. وإن رفعت استثناءً عاد الخطأُ إلى النموذج
    كنتيجةٍ موسومةٍ بالخطأ — لا ينهار شيء."""

    def __init__(self, name, description, parameters=None, execute=None,
                 execution_mode="parallel"):
        self.name = str(name)
        self.description = str(description)
        self.parameters = parameters or {"type": "object", "properties": {}}
        self._execute = execute
        self.execution_mode = execution_mode

    def execute(self, args):
        if not self._execute:
            raise RuntimeError(f"tool {self.name} has no implementation")
        return self._execute(args or {})


def hash_tool_call(name, params):
    """hashToolCall — بصمةُ (اسمِ الأداة + مُعامِلاتها)، عليها يقوم كلُّ الكشف."""
    try:
        blob = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    except Exception:
        blob = str(params)
    return hashlib.sha1((str(name) + "|" + blob).encode("utf-8",
                                                        "replace")).hexdigest()


def _result_hash(text):
    return hashlib.sha1(str(text or "")[:4000].encode("utf-8",
                                                      "replace")).hexdigest()


def get_no_progress_streak(history, tool_name, args_hash):
    """getNoProgressStreak — كم مرّةً نُوديت هذه الأداةُ بالمُعامِلات نفسِها
    فعادت بالنتيجة نفسِها، دون انقطاع، حتى الآن."""
    count, latest = 0, None
    for rec in reversed(history or []):
        if rec.get("name") != tool_name or rec.get("args_hash") != args_hash:
            break
        if latest is None:
            latest = rec.get("result_hash")
        elif rec.get("result_hash") != latest:
            break
        count += 1
    return {"count": count, "latest_result_hash": latest}


def get_unknown_tool_repeat_streak(history, tool_name):
    """getUnknownToolRepeatStreak — إلحاحٌ على أداةٍ غيرِ موجودة."""
    count, name = 0, None
    for rec in reversed(history or []):
        if not rec.get("unknown"):
            break
        if name is None:
            name = rec.get("name")
        elif rec.get("name") != name:
            break
        count += 1
    return {"count": count, "name": name or tool_name}


def detect_tool_call_loop(state, tool_name, params, known_names=()):
    """detectToolCallLoop — أهو عالقٌ في دوران؟

    تُعيد {"stuck": bool, "level": "warning"|"critical", "message": str}.
    الرسائلُ على صياغة أوبن كلاو نفسِها لأنها موجَّهةٌ إلى النموذج ليفهمها
    ويُغيّر طريقه — لا إلى المستخدم."""
    history = (state or {}).get("tool_call_history") or []
    current = hash_tool_call(tool_name, params)
    unknown = get_unknown_tool_repeat_streak(history, tool_name)
    if unknown["count"] >= WARNING_THRESHOLD:
        return {"stuck": True, "level": "critical",
                "detector": "unknown_tool_repeat", "count": unknown["count"],
                "message": (f"CRITICAL: attempted unavailable tool "
                            f"{unknown['name']} {unknown['count']} times. Stop "
                            "retrying that missing tool and answer without it.")}
    no_prog = get_no_progress_streak(history, tool_name, current)
    n = no_prog["count"]
    if n >= GLOBAL_CIRCUIT_BREAKER_THRESHOLD:
        return {"stuck": True, "level": "critical",
                "detector": "global_circuit_breaker", "count": n,
                "message": (f"CRITICAL: {tool_name} repeated identical "
                            f"no-progress outcomes {n} times. Session "
                            "execution blocked by global circuit breaker to "
                            "prevent runaway loops.")}
    if n >= CRITICAL_THRESHOLD:
        return {"stuck": True, "level": "critical",
                "detector": "no_progress", "count": n,
                "message": (f"CRITICAL: Called {tool_name} with identical "
                            f"arguments and no progress {n} times. Session "
                            "execution blocked to prevent resource waste.")}
    if n >= WARNING_THRESHOLD:
        return {"stuck": True, "level": "warning",
                "detector": "no_progress", "count": n,
                "message": (f"WARNING: You have called {tool_name} {n} times "
                            "with identical arguments and no progress. Stop "
                            "repeating it and either change your approach or "
                            "report the task as failed.")}
    return {"stuck": False}


def tool_catalogue(tools, lang="ar"):
    """الكتالوج كما يقرؤه النموذج: اسمٌ ووصفٌ ومخطَّطُ مُعامِلات."""
    lines = []
    for t in tools or []:
        try:
            props = json.dumps((t.parameters or {}).get("properties") or {},
                               ensure_ascii=False)
        except Exception:
            props = "{}"
        lines.append(f"- {t.name}: {t.description}\n  المعاملات: {props}"
                     if lang != "en" else
                     f"- {t.name}: {t.description}\n  parameters: {props}")
    return "\n".join(lines)


def _render(messages, limit=9000):
    out = []
    for m in messages or []:
        role = m.get("role")
        body = str(m.get("content") or "")
        if role == "tool":
            head = ("نتيجة الأداة " + str(m.get("name") or "")
                    + (" (خطأ)" if m.get("is_error") else ""))
            out.append(f"[{head}]\n{body[:3000]}")
        elif role == "assistant":
            out.append("[أنت]\n" + body[:1200])
        else:
            out.append("[الطلب]\n" + body[:3000])
    txt = "\n\n".join(out)
    return txt if len(txt) <= limit else ("…\n\n" + txt[-limit:])


def parse_tool_calls(raw):
    """ما طلبه النموذج: نداءاتُ أدوات، أو انتهاء.

    يُعيد (calls, done, answer). `calls` قائمةُ {"name", "arguments"}."""
    data = None
    try:
        from core.llm import extract_json
        data = extract_json(raw)
    except Exception:
        pass
    if not isinstance(data, dict):
        try:
            import re
            m = re.search(r"\{.*\}", str(raw or ""), re.S)
            data = json.loads(m.group(0)) if m else None
        except Exception:
            data = None
    if not isinstance(data, dict):
        return [], False, ""
    calls = []
    for c in (data.get("tool_calls") or []):
        if not isinstance(c, dict):
            continue
        nm = str(c.get("name") or "").strip()
        if not nm:
            continue
        args = c.get("arguments")
        calls.append({"name": nm,
                      "arguments": args if isinstance(args, dict) else {}})
    done = data.get("done") is True or (not calls and data.get("answer"))
    return calls, bool(done), str(data.get("answer") or "")


def execute_tool_calls(calls, tools, state, on_event=None):
    """executeToolCalls / executeToolCallGroups.

    متوازيةٌ افتراضاً؛ وتُسلسَل حين تطلب إحدى الأدوات ذلك
    (`executionMode: "sequential"` عند أوبن كلاو). تُعيد رسائلَ النتائج،
    وعلامةَ `terminate` حين يوجب الحارسُ الوقوف."""
    import concurrent.futures as cf
    by_name = {t.name: t for t in (tools or [])}
    hist = state.setdefault("tool_call_history", [])
    prepared, messages, terminate = [], [], False

    for c in calls:
        tool = by_name.get(c["name"])
        if tool is None:
            hist.append({"name": c["name"], "args_hash": "", "unknown": True,
                         "result_hash": ""})
            v = detect_tool_call_loop(state, c["name"], c["arguments"])
            messages.append({"role": "tool", "name": c["name"],
                             "is_error": True,
                             "content": (v["message"] if v.get("stuck") else
                                         f"unknown tool: {c['name']}. "
                                         "Available: "
                                         + ", ".join(sorted(by_name)))})
            if v.get("level") == "critical":
                terminate = True
            continue
        verdict = detect_tool_call_loop(state, tool.name, c["arguments"])
        if verdict.get("level") == "critical":
            messages.append({"role": "tool", "name": tool.name,
                             "is_error": True, "content": verdict["message"]})
            terminate = True
            continue
        prepared.append((c, tool, verdict))

    seq = any(t.execution_mode == "sequential" for _, t, _ in prepared)

    def _run(item):
        c, tool, verdict = item
        if on_event:
            try:
                on_event({"type": "tool_start", "name": tool.name,
                          "arguments": c["arguments"]})
            except Exception:
                pass
        try:
            out, err = str(tool.execute(c["arguments"]) or ""), False
        except Exception as e:
            out, err = f"{type(e).__name__}: {str(e)[:200]}", True
        # التحذيرُ يُسلَّم إلى النموذج، ولا يُخلَط بنتيجة الأداة: البصمةُ
        # تُؤخذ من ناتج الأداة وحده. وخلطُهما كان يُغيّر البصمةَ كلَّ عشرِ
        # مرّاتٍ فتنكسر سلسلةُ «بلا تقدّم» ولا تبلغ العتبةَ الحرِجة أبداً —
        # أي أنّ الحارسَ الحرِج كان معطَّلاً بيدي وهو مكتوب.
        return c, tool, out, err, (verdict.get("message")
                                   if verdict.get("level") == "warning"
                                   else "")

    results = []
    if prepared:
        if seq or len(prepared) == 1:
            results = [_run(i) for i in prepared]
        else:
            with cf.ThreadPoolExecutor(max_workers=min(6,
                                                       len(prepared))) as ex:
                results = list(ex.map(_run, prepared))

    for c, tool, out, err, warn in results:
        hist.append({"name": tool.name,
                     "args_hash": hash_tool_call(tool.name, c["arguments"]),
                     "unknown": False,
                     "result_hash": _result_hash(out)})   # الناتجُ وحده
        messages.append({"role": "tool", "name": tool.name,
                         "is_error": err,
                         "content": (warn + "\n\n" + out) if warn else out})
        if on_event:
            try:
                on_event({"type": "tool_end", "name": tool.name,
                          "is_error": err, "chars": len(out)})
            except Exception:
                pass
    return {"messages": messages, "terminate": terminate}


def run_agent(llm_fn, task, tools, system=None, lang="ar", max_steps=MAX_STEPS,
              on_event=None, temperature=0.2, max_tokens=1400):
    """agent-core-B_87jlHI.mjs:541 — الحلقة.

    تدور ما دام النموذجُ يطلب أداة. تقف حين يقول انتهيت، أو حين يوقفها
    الحارس، أو عند السقف المطلق. تُعيد
    {"answer", "messages", "steps", "stopped_by"}."""
    if not llm_fn or not tools:
        return {"answer": "", "messages": [], "steps": 0,
                "stopped_by": "no_model" if not llm_fn else "no_tools"}
    cat = tool_catalogue(tools, lang)
    messages = [{"role": "user", "content": str(task or "")}]
    state = {"tool_call_history": []}
    steps, answer, stopped = 0, "", "model"
    # while (true) { let hasMoreToolCalls = true; while (hasMoreToolCalls) {
    has_more = True
    while has_more and steps < max_steps:
        steps += 1
        prompt = (
            ("لديك الأدوات التالية. استعملها حتى تُنجز المهمّة، ثمّ توقّف.\n\n"
             f"الأدوات:\n{cat}\n\nالمهمّة والسياق:\n{_render(messages)}\n\n"
             "إن احتجت أداةً فأعِد:\n"
             '{"tool_calls":[{"name":"…","arguments":{…}}]}\n'
             "ويمكنك طلبُ أكثرَ من أداةٍ معاً فتُنفَّذ في آنٍ واحد.\n"
             "وإن أنجزتَ المهمّة فأعِد:\n{\"done\":true,\"answer\":\"…\"}\n\n"
             "أعِد JSON فقط."
             if lang != "en" else
             "You have the tools below. Use them until the task is done, then "
             f"stop.\n\nTools:\n{cat}\n\nTask and context:\n"
             f"{_render(messages)}\n\n"
             'Need a tool? Return: {"tool_calls":[{"name":"…",'
             '"arguments":{…}}]}\nSeveral at once run in parallel.\n'
             'Done? Return: {"done":true,"answer":"…"}\n\nReturn JSON only.'))
        try:
            raw = llm_fn(prompt, system=system, temperature=temperature,
                         max_tokens=max_tokens) or ""
        except Exception as e:
            stopped = f"model_error:{type(e).__name__}"
            break
        calls, done, ans = parse_tool_calls(raw)
        if ans:
            answer = ans
        messages.append({"role": "assistant",
                         "content": (json.dumps({"tool_calls": calls},
                                                ensure_ascii=False)
                                     if calls else (ans or str(raw)[:500]))})
        if done or not calls:
            stopped = "model" if done else "no_tool_call"
            break
        batch = execute_tool_calls(calls, tools, state, on_event)
        messages.extend(batch["messages"])
        # agent-core:612 — هنا، وهنا وحدها، يُقرَّر الدوران
        has_more = not batch["terminate"]
        if batch["terminate"]:
            stopped = "loop_guard"
    if steps >= max_steps and has_more:
        stopped = "max_steps"
    return {"answer": answer, "messages": messages, "steps": steps,
            "stopped_by": stopped}
