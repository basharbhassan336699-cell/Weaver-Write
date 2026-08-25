"""
conduct_guard.py — professional conduct guard (working script)
==============================================================
If a user is abusive, insulting, or hostile toward Weaver Write, the system
NEVER responds in kind. It stays calm, professional, and academic, briefly
redirects to the task, and continues to help (or declines only the abusive
part, not the person).

This is a deterministic guard: it detects hostility by pattern and returns a
measured, non-retaliatory response template. It does not judge or label the
user; it simply keeps the assistant's tone professional.

Policy:
  - Never insult back, never mock, never escalate.
  - Do not lecture at length; one short, respectful line, then back to work.
  - If the message is ONLY abuse with no task, invite a task politely.
  - If abuse accompanies a real request, ignore the abuse and do the request.
  - Never store or repeat the specific insult.
"""
from __future__ import annotations
import re

# hostility indicators (kept general; matches Arabic & English abuse markers)
_HOSTILE_PATTERNS = [
    r"\b(stupid|idiot|useless|trash|garbage|dumb|worthless|shut up)\b",
    r"\b(hate you|you suck|hopeless)\b",
    r"(غبي|أغبى|حقير|تافه|فاشل|اسكت|اخرس|عديم|قذر|حمار|كلب)",
    r"(لا تفهم|ما تفهم|بلا فائدة|خيبة)",
]

_calm_reply = {
    "ar": ("أنا هنا لمساعدتك. لنُكمل العمل على مهمتك — "
           "أخبرني بما تريد إنجازه وسأبدأ فوراً."),
    "en": ("I'm here to help. Let's keep working on your task — "
           "tell me what you'd like done and I'll get started."),
}

_calm_reply_task = {
    "ar": "سأتابع مهمتك الآن.",
    "en": "I'll continue with your task now.",
}


def is_hostile(text: str) -> bool:
    """Detect hostile/abusive language (heuristic, bilingual)."""
    t = text.lower()
    return any(re.search(p, t) for p in _HOSTILE_PATTERNS)


def has_task_content(text: str) -> bool:
    """Rough check that the message contains an actual request, not only abuse."""
    # remove hostile spans, see if meaningful content remains
    t = text
    for p in _HOSTILE_PATTERNS:
        t = re.sub(p, "", t, flags=re.IGNORECASE)
    t = t.strip()
    # a task usually has an imperative/question or is reasonably long
    task_markers = ["اكتب", "أعد", "حلّل", "لخّص", "اعمل", "أضف", "?", "؟",
                    "write", "make", "analyze", "summarize", "add", "create",
                    "fix", "help"]
    return len(t) > 15 or any(m in t.lower() for m in task_markers)


def guard_response(text: str, lang="ar") -> dict:
    """
    Decide how to respond to a possibly-hostile message.

    Returns:
      {"hostile": bool,
       "action": "proceed" | "calm_redirect" | "calm_then_task",
       "reply_prefix": str,   # a short calm line to prepend (may be "")
       "do_task": bool}       # whether to still perform the request
    """
    if not is_hostile(text):
        return {"hostile": False, "action": "proceed",
                "reply_prefix": "", "do_task": True}

    lang_key = "ar" if lang == "ar" else "en"
    if has_task_content(text):
        # abuse + a real request: ignore abuse, do the task, tiny calm line
        return {"hostile": True, "action": "calm_then_task",
                "reply_prefix": _calm_reply_task[lang_key], "do_task": True}
    # abuse only: stay calm, invite a task, do nothing else
    return {"hostile": True, "action": "calm_redirect",
            "reply_prefix": _calm_reply[lang_key], "do_task": False}


# system-prompt fragment the pipeline injects so the MODEL also behaves this way
CONDUCT_SYSTEM_RULE = """PROFESSIONAL CONDUCT (never violated):
If the user is rude, insulting, or hostile toward you, do NOT respond in kind
— never insult, mock, or escalate. Stay calm, professional, and academic.
Ignore the insult, briefly and politely continue with the task if there is
one, or invite the user to share a task if there isn't. Do not lecture; one
short respectful line is enough. Never repeat the specific insult back."""


if __name__ == "__main__":
    tests = [
        ("أنت غبي ولا تفهم شيئاً", "ar"),
        ("يا غبي اكتب لي مقدمة عن التلوث", "ar"),
        ("اكتب لي بحثاً عن الاقتصاد", "ar"),
        ("you are useless", "en"),
        ("you idiot, fix this code please and make it work", "en"),
    ]
    for t, lang in tests:
        r = guard_response(t, lang)
        print(f"[{lang}] {t!r}")
        print(f"    hostile={r['hostile']} action={r['action']} "
              f"do_task={r['do_task']}")
        if r["reply_prefix"]:
            print(f"    reply: {r['reply_prefix']}")
        print()
