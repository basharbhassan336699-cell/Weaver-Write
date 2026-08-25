---
name: credibility_scorer
description: >
  Gate that decides whether a source may be cited academically. Rejects
  unreliable-by-default sources (general encyclopedias like Wikipedia,
  personal blogs, content mills, Q&A sites/forums, social media, news for
  scientific claims, commercial/promotional sites) UNLESS the task explicitly
  permits one — then it's allowed for that task only. Recommends reliable
  alternatives. Bilingual (AR/EN).
triggers:
  - مصدر موثوق
  - مصداقية
  - مرجع موثوق
  - ويكيبيديا
  - مصادر البحث
  - reliable source
  - credibility
  - source check
  - wikipedia
---

# credibility_scorer

## Unreliable by default (rejected unless explicitly permitted)
General encyclopedias (Wikipedia, Wikia/Fandom, Britannica), personal blogs
(Blogger, WordPress, Medium), content mills (mawdoo3, m3loma, ...), Q&A sites
and forums (Reddit, Quora, Chegg, Course Hero, Brainly), social media, news
(events only — not scientific claims), and commercial/promotional sites.

## Explicit-permission rule
If the task says to use one of these, it's allowed FOR THAT TASK ONLY
(`allow_unreliable`, `allowed_sources`, or `about_company` for a company's own
site when the task is about that company). If not explicitly permitted, it is
rejected.

## Reliable alternatives (always recommended)
Peer-reviewed journals (Scopus / Web of Science), published academic books,
official government sites, international-body reports (UN, WHO, IMF).

## Script
`scripts/source_reliability.py`: classify_source, check_source,
filter_sources.
