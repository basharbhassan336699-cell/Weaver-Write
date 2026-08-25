---
name: weak_model_support
description: >
  Reliability scaffolding that makes the pipeline produce good work even when
  the connected LLM is weak (small/quantized, poor Arabic, bad JSON, prone to
  hallucinated citations) or partially failing. Applies six techniques around
  any llm_fn: task chunking, chain-of-thought, self-consistency voting, a
  verification loop, a draft->review cascade, and strict RAG (no citation
  outside the retrieved set). Degrades safely with no model.
triggers:
  - نموذج ضعيف
  - تحسين الموثوقية
  - نموذج صغير
  - fallback
  - weak model
  - small model
  - reliability
  - self consistency
  - verification loop
---

# weak_model_support

Six complementary techniques, applied by model strength.

## Techniques
1. **task_chunking** — split a big task into small single-purpose steps.
2. **cot** — force explicit step-by-step reasoning.
3. **self_consistency** — sample N times, take the majority answer.
4. **verification_loop** — re-ask the model to check + fix its output.
5. **two_pass_cascade** — draft then review (same or stronger reviewer model).
6. **strict_rag** — strip/flag any citation not in the retrieved reference
   set (catches invented citations — the main weak-model failure).

## When each applies (reliability_plan)
- **weak** (<=7B / heavily quantized): all six.
- **medium**: cot + verification + strict_rag.
- **strong** (DeepSeek V3/R1, Qwen 72B, GPT-4-class): strict_rag only.

## Safe degradation
With no llm_fn, functions return scaffolding (plans/prompts) — nothing
crashes. strict_rag and chunking work WITHOUT a model at all.

## Note on models
DeepSeek and larger Qwen are strong, not weak — they need little of this.
The techniques target small/quantized models and partial-failure cases.

## Script
`scripts/weak_model_support.py`: chunk_task, cot_wrap, self_consistency,
verify_and_fix, two_pass, enforce_strict_rag, reliability_plan.
