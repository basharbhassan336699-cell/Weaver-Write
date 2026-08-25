---
name: conclusion_writer
description: "Write a conclusion and recommendations: summary of findings, answer to the research question, recommendations, future-work suggestions. Output in the task language."
triggers: ["خاتمة", "توصيات", "مقترحات", "conclusion", "recommendations", "future work"]
layer: 6
---

# Skill: Conclusion & Recommendations

## Elements
1. A brief summary of the key findings
2. An explicit answer to the research question
3. Practical recommendations
4. Suggestions for future research

## Constraints
- Do not introduce new information in the conclusion
- Recommendations must be actionable and grounded in the findings

## Scripts
- `scripts/build_conclusion.py`

## Status
- Scripts: **built and tested** (bilingual AR/EN)
