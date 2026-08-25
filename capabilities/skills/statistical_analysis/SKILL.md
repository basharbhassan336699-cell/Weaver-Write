---
name: statistical-survey-analysis
description: >
  A rigorous, execution-based skill for analyzing survey/questionnaire
  data statistically — from variable classification and assumption
  checking through test selection, real code execution (pandas, scipy,
  statsmodels, pingouin), and honest, critical interpretation of
  results. Use this whenever the user has questionnaire or survey data
  (Likert-scale items, xlsx/csv responses) and wants descriptive
  statistics, reliability/validity testing (Cronbach's alpha, factor
  analysis), inferential tests (t-test, ANOVA, chi-square, correlation,
  regression), or a results write-up (e.g., APA-style). This skill
  governs statistical methodology and correctness, NOT prose/bullet
  formatting — for how to structure the written report's mix of
  narrative and bullet points, defer to the narrative-bullet-mixing
  skill if present; the two are complementary and must never be
  conflated.
triggers:
  - تحليل إحصائي
  - إحصاء
  - استبيان
  - بيانات
  - statistical
  - survey
  - analysis
  - spss
---

# Skill: Statistical Analysis of Survey Data

## 0. Scope and Boundaries (to prevent overlap)

This skill is **knowledge-and-execution based**: it governs the
correctness of statistical methodology and its actual execution. It
does **not** govern how the resulting text is laid out (when to use
prose vs. bullets) — that is the exclusive domain of the separate
`narrative-bullet-mixing` skill. When writing the final report:

- **This skill** determines: which test to use, whether assumptions
  are met, what the correct numbers are, and how to interpret them
  honestly.
- **The prose-formatting skill** (if present) determines: whether test
  results are presented as bullets (discrete, countable items) or as
  continuous prose (because the interpretation builds a causal
  argument) — which typically means **descriptive statistics and test
  results are usually tabulated/bulleted**, while **methodological
  interpretation and critical commentary remain continuous prose**,
  following that skill's governing principle.

This skill never imports formatting judgments, and the formatting
skill never imports statistical judgments — each stays within its own
boundary.

---

## 1. Methodological Knowledge Layer (mandatory reference before any analysis)

### 1.1 Classifying Variable Types
The type of every variable must be determined **before** any other
step, since this classification pre-determines which tests are even
eligible:

- **Nominal**: unordered categories (gender, major).
- **Ordinal**: ordered categories without confirmed equal spacing
  (satisfaction: dissatisfied/neutral/satisfied).
- **Interval**: equal spacing, no true zero (temperature in Celsius).
- **Ratio**: equal spacing and a true zero (age, income, years of
  experience).

### 1.2 The Methodological Sticking Point: Likert Scales
This skill takes a clear, explicit position rather than leaving it
ambiguous:

- A **single Likert item** (one question with 1–5 options) is
  methodologically treated as **ordinal**, and any descriptive/
  inferential statistic on it alone must use ordinal-appropriate tools
  (median, non-parametric tests).
- The **sum/mean of several homogeneous Likert items** forming one
  dimension (a composite scale, after reliability has been verified)
  can practically be treated as **approximately interval** — the more
  widely accepted position in applied statistical literature — provided
  this assumption is stated explicitly in any report, never passed
  over silently.
- A single Likert item must never be treated as ratio or full interval
  data without this caveat.

### 1.3 Instrument Reliability and Validity
- **Cronbach's alpha**: computed for each composite dimension/scale
  separately, not for the entire questionnaire at once if it measures
  multiple dimensions. The conventionally accepted threshold is
  ≥ 0.70 (applied with methodological caution, not as a rigid rule).
- **Reverse-coded items**: must be mathematically re-coded before
  computing reliability or means, otherwise Cronbach's alpha appears
  misleadingly low.
- **Instrument validity**: exploratory factor analysis (EFA) as a
  verification step that items actually load onto their theoretically
  assumed dimensions.

### 1.4 Descriptive Statistics
Mean, median, mode, standard deviation, frequency distributions — with
attention to the fact that mean and standard deviation have limited
meaning on purely ordinal data (see 1.2).

### 1.5 Inferential Statistics and Their Conditions of Use

| Test | Used When | Core Condition to Check |
|---|---|---|
| t-test (independent/paired) | Comparing means of two groups | Normal distribution, homogeneity of variance |
| One-/two-way ANOVA | Comparing means of 3+ groups | Normal distribution, homogeneity of variance |
| Chi-square | Association between two nominal variables | Sufficient expected cell count (usually ≥5) |
| Correlation (Pearson/Spearman) | Strength/direction of a linear relationship | Pearson assumes linearity and normality; Spearman is the non-parametric ordinal alternative |
| Linear/multiple regression | Predicting a dependent variable from independent variable(s) | Linearity, independence of errors, no multicollinearity |
| Non-parametric alternatives (Mann-Whitney, Kruskal-Wallis, Wilcoxon) | When the parametric assumptions above are violated | Do not assume normal distribution |

### 1.6 Sample Size and Sampling Method
The sampling method (random, convenience, stratified...) and sample
size must be stated as part of assessing the generalizability of
results — not treated as a peripheral detail.

---

## 2. Technical Tooling Layer (mandatory real execution)

**This skill is always executed via code, never presented as
mentally-derived numbers.** Any statistical figure not actually
computed through executed code is a fabricated figure and is rejected.

### 2.1 Libraries Used
- `pandas` — loading and cleaning data (missing values, outliers,
  re-coding reverse-worded items).
- `scipy.stats` — core inferential tests (t, one-way ANOVA,
  chi-square, Pearson/Spearman, normality tests such as Shapiro-Wilk).
- `statsmodels` — multi-factor ANOVA, full regression detail
  (coefficients, confidence intervals, residual diagnostics).
- `pingouin` — reliability tests (Cronbach's alpha), effect-size
  analysis directly and conveniently.
- `matplotlib` / `seaborn` — visualization genuinely suited to the
  data type (boxplots for comparisons, histograms for checking
  distribution, heatmaps for correlations) — never decorative.

### 2.2 Reading User Files
When an actual xlsx/csv file is received from the user, the available
**xlsx skill** is invoked as a dependent layer to read/inspect the
file before any analysis begins — this skill does not reinvent file
reading, it builds on top of it.

### 2.3 Strict Rule: No Results Without Actually Executed Code
No statement of the form "the result is expected to be statistically
significant" may be made without actually running the test and
reporting the real number (test statistic, degrees of freedom,
p-value, effect size) exactly as produced by the code, unembellished.

---

## 3. Execution Workflow (mandatory order — no step may be skipped)

1. **Understand the research question/hypothesis first** — before
   touching any numbers; the type of question determines the
   candidate test type.
2. **Precisely determine each variable's type** (see 1.1 and 1.2) —
   this pre-determines which tests are even possible.
3. **Actually clean and explore the data via code**: missing values,
   outliers, and checking the distribution (Shapiro-Wilk or visual
   inspection) — **actual checking, not assumption**, because tests
   like t and ANOVA assume normality; if it doesn't hold, mandatorily
   switch to the corresponding non-parametric alternative from table
   1.5.
4. **Choose the test based on the actual results of the previous
   step**, not on a pre-existing preference of the user or the model.
5. **Run the test via real code** and report the numbers as they are —
   without smoothing or rounding the result to make it look
   "nicer" statistically.
6. **Interpret the result with methodological caution**: a strict
   distinction between statistical significance (p-value) and
   practical significance (effect size, Cohen's d or equivalent), and
   avoiding the common error of conflating correlation with causation.
7. **Visualize the result in a way genuinely suited to the data type**
   — not decoratively or uniformly across all cases.

---

## 4. Mandatory Constructive-Critique Layer (final step of every analysis, not optional)

This skill is **not a validation machine** that produces numbers to
prove whatever the researcher wants proven. Every analysis mandatorily
closes with the following:

1. **Statistical significance is not proof**: a small p-value only
   means the result is unlikely to have occurred by chance under
   certain conditions, not that the hypothesis is "true." A strict
   distinction must always be drawn between "statistically
   significant" and "practically important" (effect size).
2. **Checking assumption violations is a mandatory step**: applying a
   t-test to non-normally distributed data, or ignoring sample
   independence, produces numbers that are "formally correct" but
   methodologically misleading — this must be explicitly flagged when
   violated, never silently ignored.
3. **Explicit rejection of p-hacking and confirmation-bias patterns**:
   if the user asks to "re-run the analysis until it shows
   significance," or to try several tests until one supports their
   prior hypothesis, this skill mandates explicitly refusing that
   pattern and explaining why it is a serious methodological error
   that undermines the credibility of the results — rather than
   silently complying to please the user.
4. **Flagging sample and generalization limits**: a small sample size
   or bias in how it was collected must be explicitly noted before any
   generalization from the results is allowed.
5. **Honest results write-up** (e.g., in APA style): clearly separating
   what the data actually showed from any additional interpretive
   conclusion, so the two are never blurred together in the reader's
   mind.

In other words: the skill "argues with" the result before delivering
it — it never automatically trusts everything that comes out of the
code without scrutiny.

---

## 5. Quick Checklist Before Delivering Any Analysis

| Question | If the answer is "No" |
|---|---|
| Was every variable's type explicitly determined? | Return to step 2 |
| Was the distribution actually checked via code before choosing a parametric test? | Return to step 3 |
| Are the reported numbers the output of actually executed code, not an estimate? | Return to step 5 |
| Was effect size reported alongside the p-value? | Add it before delivering |
| Were sample/generalization limits stated? | Add them before delivering |
| Was any implicit p-hacking request refused rather than silently executed? | Review the user's request and address it directly |
