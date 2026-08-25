"""
weak_model_support.py — reliability scaffolding for weak LLMs (working)
======================================================================
Makes the pipeline produce good work even when the connected model is weak
(small/quantized, poor at long instructions, weak Arabic, prone to bad JSON
or hallucinated citations). Implements six complementary techniques the
pipeline can apply around ANY llm_fn:

  1. task_chunking      — split a big task into small, single-purpose steps
                          a weak model can handle one at a time.
  2. cot                — force explicit step-by-step reasoning.
  3. self_consistency   — sample an answer N times and take the majority /
                          most consistent one (reduces random errors).
  4. verification_loop  — after producing text, re-ask the model to check it
                          against the rules and fix violations.
  5. two_pass_cascade   — a "draft then review" pass (same model twice, or a
                          stronger reviewer model if provided).
  6. strict_rag         — never let the model cite anything not in the
                          retrieved reference set; strip/flag invented cites.

Everything degrades safely: with no llm_fn, functions return the scaffolding
(prompts, plans) so nothing crashes; with a weak llm_fn, the techniques raise
reliability; with a strong one, they add little overhead and can be skipped.

The techniques are model-agnostic. Note on models: DeepSeek (V3/R1) and larger
Qwen (72B) are STRONG and usually need little of this; small (<=7B) or heavily
quantized models are the "weak" case these techniques target.
"""
from __future__ import annotations
import json
import re
from collections import Counter


# ═══════════════════════════════════════════════════════════
# 1. TASK CHUNKING
# ═══════════════════════════════════════════════════════════
def chunk_task(task_card: dict) -> list:
    """
    Break a task into ordered, single-purpose sub-steps a weak model can do
    one at a time. Uses the research structure if present, else a default
    academic flow. Returns a list of {"id","goal","section"}.
    """
    steps = []
    sections = task_card.get("sections")
    if sections:
        for i, s in enumerate(sections):
            steps.append({"id": f"s{i}", "goal": f"write section",
                          "section": s.get("title", s.get("key", f"section {i}"))})
    else:
        for i, key in enumerate(["introduction", "body", "conclusion"]):
            steps.append({"id": f"s{i}", "goal": "write section", "section": key})
    # each step is deliberately small: one section, with its own mini-prompt
    return steps


def chunk_prompt(step: dict, context: str, lang="ar") -> str:
    """A minimal, focused prompt for ONE chunk (weak models do better with
    short, single-goal prompts)."""
    if lang == "ar":
        return (f"اكتب فقط قسم: {step['section']}.\n"
                f"السياق المتاح:\n{context}\n"
                f"لا تكتب أقساماً أخرى. لا تخترع مراجع. اكتب القسم فقط:")
    return (f"Write ONLY the section: {step['section']}.\n"
            f"Context:\n{context}\n"
            f"Do not write other sections. Do not invent references. "
            f"Write just this section:")


# ═══════════════════════════════════════════════════════════
# 2. CHAIN-OF-THOUGHT
# ═══════════════════════════════════════════════════════════
def cot_wrap(prompt: str, lang="ar") -> str:
    """Force explicit reasoning before the answer — helps weak models."""
    if lang == "ar":
        return (prompt + "\n\nفكّر خطوة بخطوة أولاً (اكتب تفكيرك)، ثم أعطِ "
                "الإجابة النهائية بعد سطر يبدأ بـ 'الإجابة:'.")
    return (prompt + "\n\nThink step by step first (write your reasoning), "
            "then give the final answer after a line starting with 'Answer:'.")


def extract_answer(response: str, lang="ar") -> str:
    """Pull the final answer out of a CoT response."""
    marker = "الإجابة:" if lang == "ar" else "Answer:"
    if marker in response:
        return response.split(marker, 1)[1].strip()
    return response.strip()


# ═══════════════════════════════════════════════════════════
# 3. SELF-CONSISTENCY (majority vote over samples)
# ═══════════════════════════════════════════════════════════
def self_consistency(llm_fn, prompt: str, n: int = 3, lang="ar",
                     temperature=0.7) -> dict:
    """
    Sample the model n times and pick the most consistent answer. Best for
    short/structured answers (a label, a number, a JSON field). Returns
    {"answer","agreement","samples"}.
    """
    if llm_fn is None:
        return {"answer": None, "agreement": 0.0, "samples": [],
                "note": "no llm_fn — scaffolding only"}
    samples = []
    for _ in range(n):
        try:
            out = llm_fn(prompt, temperature=temperature)
            samples.append(extract_answer(out, lang))
        except Exception:
            continue
    if not samples:
        return {"answer": None, "agreement": 0.0, "samples": []}
    # normalize whitespace for voting
    norm = [re.sub(r"\s+", " ", s.strip().lower()) for s in samples]
    counts = Counter(norm)
    top_norm, top_count = counts.most_common(1)[0]
    # return the original-cased sample matching the winning normalized form
    answer = next(s for s, nrm in zip(samples, norm) if nrm == top_norm)
    return {"answer": answer, "agreement": top_count / len(samples),
            "samples": samples}


# ═══════════════════════════════════════════════════════════
# 4. VERIFICATION LOOP
# ═══════════════════════════════════════════════════════════
_RULES_AR = """تحقّق من النص التالي والتزم بهذه القواعد:
- كل استشهاد يجب أن يكون من المراجع المتاحة فقط (لا اختراع).
- لا رموز آلية (— ★ → |).
- لا خلط لغوي خاطئ.
أعِد كتابة النص مصحّحاً إن وُجدت مخالفات، وإلا أعده كما هو."""

_RULES_EN = """Check the text against these rules:
- Every citation must come only from the available references (no invention).
- No AI symbols (— ★ → |).
- No wrong language mixing.
Rewrite the text corrected if any violations exist, else return it as is."""


def verification_prompt(text: str, references: list, lang="ar") -> str:
    """Build a prompt that asks the model to verify + fix its own output."""
    rules = _RULES_AR if lang == "ar" else _RULES_EN
    ref_list = "\n".join(f"- {r}" for r in (references or []))
    head = "المراجع المتاحة:" if lang == "ar" else "Available references:"
    return f"{rules}\n\n{head}\n{ref_list}\n\n---\n{text}\n---"


def verify_and_fix(llm_fn, text: str, references: list, lang="ar") -> str:
    """Run one verification pass; returns corrected text (or original)."""
    if llm_fn is None:
        return text
    try:
        return llm_fn(verification_prompt(text, references, lang))
    except Exception:
        return text


# ═══════════════════════════════════════════════════════════
# 5. TWO-PASS CASCADE (draft -> review)
# ═══════════════════════════════════════════════════════════
def two_pass(draft_fn, prompt: str, review_fn=None, lang="ar") -> str:
    """
    Draft with draft_fn, then improve with review_fn (or draft_fn again).
    A stronger review_fn (if available) catches a weak drafter's mistakes.
    """
    if draft_fn is None:
        return ""
    draft = draft_fn(prompt)
    reviewer = review_fn or draft_fn
    review_prompt = (
        ("راجع وحسّن النص التالي دون تغيير المعنى أو حذف الاستشهادات:\n\n"
         if lang == "ar" else
         "Review and improve the following without changing meaning or "
         "dropping citations:\n\n") + draft)
    try:
        return reviewer(review_prompt)
    except Exception:
        return draft


# ═══════════════════════════════════════════════════════════
# 6. STRICT RAG (no citation outside the retrieved set)
# ═══════════════════════════════════════════════════════════
_CITE_RE = re.compile(r"\(([^()]+?)[،,]\s*(?:ص\.?|p\.?)?\s*\d*\)")


def enforce_strict_rag(text: str, allowed_keys: list) -> dict:
    """
    Remove or flag any citation whose source key isn't in `allowed_keys`.
    Returns {"text","removed":[...],"kept":[...]}.
    Weak models often invent plausible-looking citations; this catches them.
    """
    allowed_norm = {re.sub(r"\s+", "", k).lower() for k in (allowed_keys or [])}
    removed, kept = [], []

    def _check(m):
        cite = m.group(0)
        key = re.sub(r"\s+", "", m.group(1)).lower()
        # accept if any allowed key is a prefix/substring of the cited author
        if any(a in key or key in a for a in allowed_norm):
            kept.append(cite)
            return cite
        removed.append(cite)
        return ""  # strip invented citation

    new_text = _CITE_RE.sub(_check, text)
    new_text = re.sub(r"\s{2,}", " ", new_text)
    return {"text": new_text, "removed": removed, "kept": kept}


# ═══════════════════════════════════════════════════════════
# ORCHESTRATION: apply the right techniques for a weak model
# ═══════════════════════════════════════════════════════════
def reliability_plan(model_strength="weak") -> dict:
    """
    Which techniques to apply, by model strength.
      weak    -> all six.
      medium  -> cot + verification + strict_rag.
      strong  -> strict_rag only (cheap safety).
    """
    if model_strength == "strong":
        return {"chunking": False, "cot": False, "self_consistency": False,
                "verification": False, "two_pass": False, "strict_rag": True}
    if model_strength == "medium":
        return {"chunking": False, "cot": True, "self_consistency": False,
                "verification": True, "two_pass": False, "strict_rag": True}
    return {"chunking": True, "cot": True, "self_consistency": True,
            "verification": True, "two_pass": True, "strict_rag": True}


if __name__ == "__main__":
    # demos that need no llm_fn
    card = {"sections": [{"title": "Introduction"}, {"title": "Methods"},
                         {"title": "Conclusion"}]}
    print("chunks:", [s["section"] for s in chunk_task(card)])
    print("\ncot wrap:", cot_wrap("Summarize X", "en")[:70], "...")

    # strict RAG demo
    text = ("Education matters (Smith, 2023). AI grows fast (FakeAuthor, 2024). "
            "Data is key (Ahmed, 2022).")
    r = enforce_strict_rag(text, ["Smith", "Ahmed"])
    print("\nstrict RAG:")
    print("  kept:", r["kept"])
    print("  removed (invented):", r["removed"])
    print("  text:", r["text"])

    print("\nplans:")
    for s in ("weak", "medium", "strong"):
        on = [k for k, v in reliability_plan(s).items() if v]
        print(f"  {s}: {on}")
