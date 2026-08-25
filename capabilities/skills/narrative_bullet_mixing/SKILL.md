---
name: narrative-bullet-mixing
description: >
  A precise skill explaining the governing principle behind mixing
  continuous narrative prose with bullet-point structure in academic,
  legal, and professional writing, grounded in documented examples from
  real texts in Arabic and English. Use this when analyzing the
  structural quality of any professional document, or when trying to
  understand why one text's formatting feels natural while another's
  distribution between prose and bullets feels arbitrary or forced.
  This skill governs presentation FORM only (prose vs. bullets) — it
  does not govern statistical or methodological correctness. When a
  document reports statistical/survey results, defer to the sibling
  statistical-survey-analysis skill for what numbers, tests, and
  interpretations are valid; use this skill only to decide how that
  already-validated content should be laid out on the page.
triggers:
  - نقاط
  - تعداد
  - سرد
  - bullets
  - narrative
  - list format
---

# Skill: The Governing Principle Behind Mixing Narrative and Bullet-Point Style

## I. The Core Principle

The governing rule is not "alternate between prose and bullets to break
monotony" — that is a superficial understanding. The real rule is:

> **The form of presentation follows the nature of the information, not
> the writer's desire for visual variety.**

In other words, a skilled writer never decides "I'll add bullets now
because this paragraph is getting long." Instead, the writer asks: is
this piece of information, in its essence, **a set of separate,
countable items**, or is it **a single continuous idea that requires
explanation and logical connection**? The answer to that question is
what determines the form.

---

## II. When Does Information Turn Into Bullets? (Conditions That Must Combine, Not Substitute)

A passage turns into a bulleted list when **most** of the following
conditions hold together:

1. **Countability**: the items can be enumerated as a finite, discrete
   set (three procedures, four technologies, six activities...).
2. **Structural homogeneity**: every item in the list belongs to the same
   "grammatical/conceptual type" — all are procedural actions, all are
   named technologies, or all are offered services.
3. **Relative independence**: each item can be read in isolation, out of
   its given order, without losing its meaning (unlike narrative steps
   that are causally sequential).
4. **No need for direct causal linking between items**: you don't need to
   write "because," "therefore," or "as a result" between one item and
   the next to understand it.

If even one of these conditions is missing, the passage should remain
prose — no matter how long it is.

---

## III. When Does the Passage Remain Continuous Prose?

Prose remains the correct form when the purpose of the passage is one of
the following:

- **Explanation**: answering "why" or "how this relates to that."
- **Building an argument**: a premise that leads to a conclusion through
  logically connected steps.
- **Historical or conceptual context**: framing that links the topic to a
  broader background.
- **A causal relationship between ideas**: when understanding the second
  idea depends on understanding the first (it would be incorrect to split
  them into two separate bullets, because the connection itself carries
  the meaning).

---

## IV. Documented Examples (Structural Analysis, Not Verbatim Quotation)

### Example 1 — Arabic Legal Text (Establishing a Mortgage Security Interest)

The passage opens with narrative prose explaining a **causal relationship**:
how the process of creating the mortgage begins as a negotiation phase
between two parties, and why the preliminary agreement alone is not
enough to produce legal effect (because it requires formal, notarized
execution). This is a causal/legal explanation that cannot be broken into
bullets without losing its logic.

The text then shifts immediately into bullets when enumerating **separate,
concrete actions** performed by the official notary: verifying identity,
verifying the title deed, determining the debt amount, drafting the
contract. These four items are homogeneous (all are verification/
notarization actions), independent of each other's order (their listing
order could be swapped without losing meaning), and precisely countable —
so they became bullets.

The text then returns to prose immediately after the list, because the
following passage explains a **legal classification** (these are purely
procedural rules governed by evidentiary law) — which is conceptual
explanation, not enumeration.

### Example 2 — English Academic Text (AI in Education)

The introductory paragraphs are entirely narrative because they build a
connected argument: why this topic deserves study, and what research gap
the document fills. This cannot be converted into bullets because each
sentence is logically built on the one before it.

When transitioning to defining "the underlying technologies that power
automation" (Machine Learning, NLP, Intelligent Tutoring Systems,
Learning Analytics), the text immediately shifts to bullets — because
these are four independent technologies, structurally homogeneous (each
follows the same pattern: bolded term + one definitional sentence), and
require no causal link between them.

### Example 3 — English Business Text (Agritourism Platform Business Plan)

Same pattern: a narrative paragraph introduces the concept of "two
interconnected value streams," then immediately shifts into a list
enumerating concrete activities (fruit picking, educational workshops,
animal interaction...) because these are literally countable product-
offering items. Notice that this list is proportionally longer than in
the previous two examples — because the nature of the content itself
(a service catalog) demands broader enumeration, not because the writer
"wanted variety."

When moving to intellectual property rights, the text returns to prose
immediately, because this is a legal/conceptual explanation of the scope
of protection and its relationship to user-generated content — not an
enumeration of items.

---

## V. The Decision Comparison Table

| Question | If "Yes" is typically the answer | If "No" is typically the answer |
|---|---|---|
| Are the items precisely countable? | Bullets | Prose |
| Can the items' order be swapped without losing meaning? | Bullets | Prose |
| Do you need "because" or "therefore" between items? | Prose | Bullets |
| Does the passage answer "why" or "how does this relate to that"? | Prose | Bullets |
| Are the items the same grammatical/conceptual type? | Bullets (if condition 1 also holds) | Prose |

---

## VI. Common Mistakes That Reveal Inexperienced Writing

1. **Converting a causal relationship into separate bullets**: breaking a
   sentence like "because X happened, Y occurred, which led to Z" into
   three independent bullet points, losing the logical connection between
   them.
2. **Narrating at length what should be enumerated**: writing a list of
   six homogeneous items as one long sentence full of conjunctions,
   making it harder for the reader to count or scan.
3. **Bulleting non-homogeneous items**: placing a long explanatory idea
   inside a bulleted list alongside short, countable items, making the
   list feel disjointed.
4. **Over-bulleting as a default style**: converting nearly every
   paragraph into bullets regardless of the nature of its content, so the
   text loses its ability to build a continuous argument.

---

## VII. Conclusion

Mixing prose and bullets in genuine professional writing is **not an
aesthetic choice made for variety**; it is **a direct reflection of the
structure of the information itself**: whatever is countable,
homogeneous, and order-independent becomes bullets; whatever is
explanatory, causal, or built on a continuous logical chain remains
prose. Understanding this principle explains why one text feels coherent
and natural in its organization, while another feels arbitrary or forced
in how it distributes content between the two forms — regardless of
language or field (legal, academic, or business).

---

## VIII. Scope Boundary (to avoid conflict with statistical-survey-analysis)

This skill decides **form**, never **content correctness**. In a
document that reports statistical or survey results, this skill's job
is limited to: given a passage of already-verified content, should it
be prose or bullets? It never decides whether a p-value is correctly
computed, whether a test's assumptions were checked, or whether a
conclusion is methodologically sound — that is the exclusive domain of
the `statistical-survey-analysis` skill. The two are complementary and
must be applied in sequence, not merged: methodology and execution
first (statistical-survey-analysis), presentation form second
(this skill).
