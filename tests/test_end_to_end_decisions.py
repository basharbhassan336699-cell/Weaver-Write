# -*- coding: utf-8 -*-
"""خطّ الأنابيب كاملاً على طلباتك الثلاثة — بنموذجٍ بديل، بلا مفتاح ولا ريال."""
import sys, os, json, asyncio
# THE TESTS ONLY RAN ON THE MACHINE THEY WERE WRITTEN ON. The repository
# root was hardcoded as an absolute path, so on any other checkout the insert
# pointed at a directory that does not exist and every file died on
# "No module named 'pipeline'" before running a single check. The root is
# where this file lives, one directory up — the way tests/smoke_pipeline.py
# already computes it — so the suite runs from any clone on any device.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
for k in list(os.environ):
    if k.startswith("WEAVER_"): os.environ.pop(k)
from pipeline.orchestrator import WeaverOrchestrator as W

REQS = [
 ("١ ملخّص", "اكتب ملخصاً في صفحة واحدة عن أثر قلة النوم على التركيز، بلا جداول، ووثّق بنمط APA.",
  {"action":"summarize","pages":1,"wants_table":False,"citation_style":"APA",
   "sourcing":"cited","recency":False,"topic":"أثر قلة النوم على التركيز"}),
 ("٢ بحث",   "اكتب بحثاً عن تحويل الطاقة الشمسية إلى كهرباء في ثلاثة مباحث.",
  {"action":"research","mabhath_count":3,"wants_table":None,"citation_style":None,
   "sourcing":None,"recency":False,"topic":"تحويل الطاقة الشمسية إلى كهرباء"}),
 ("٣ بلا مصادر","لخّص لي هذا الموضوع بلا مصادر: مفهوم الذكاء الاصطناعي التوليدي.",
  {"action":"summarize","wants_table":None,"citation_style":None,
   "sourcing":"none","recency":False,"topic":"مفهوم الذكاء الاصطناعي التوليدي"}),
]

def make_model(plan):
    def m(prompt, system=None, temperature=0.7, max_tokens=None, timeout=None):
        if '"tasks"' in prompt or "أعِد الخطة" in prompt:
            t = {"action": plan.get("action"), "scopes": [], "format": None,
                 "language": "ar", "topic": plan.get("topic"),
                 "source": "topic", "target": "new_file", "on_previous": False,
                 "mabhath_count": plan.get("mabhath_count"),
                 "matlab_count": None, "slide_count": None,
                 "words": plan.get("words"), "pages": plan.get("pages"),
                 "wants_table": plan.get("wants_table"), "wants_chart": None,
                 "wants_data": False, "needs_sources": plan.get("sourcing") != "none",
                 "sourcing": plan.get("sourcing"),
                 "citation_style": plan.get("citation_style"),
                 "recency": plan.get("recency")}
            return json.dumps({"language": "ar", "tasks": [t]}, ensure_ascii=False)
        if "task card as JSON" in prompt or "task_type" in prompt:
            return json.dumps({"task_type": "research", "topic": plan.get("topic"),
                               "language": "ar", "citation_style": "unspecified",
                               "output_format": ["DOCX"], "page_count": None,
                               "reference_count": None,
                               "extras": {}, "academic_field": "", "missing_info": []},
                              ensure_ascii=False)
        return ""
    return m

from pipeline.orchestrator import understand_request

print("═"*74)
for name, req, plan in REQS:
    llm = make_model(plan)
    o = W.__new__(W); o.llm_fn = llm; o.system_main = "s"
    # نفهم الطلب كما يفعل النظام، ثم نطبّق كتلة الدمج نفسها
    iv = understand_request("", req, None, llm, "s") or {}
    tasks = (iv.get("tasks") or [{}])
    _iv = tasks[0] if tasks else {}
    c = {"topic": plan.get("topic"), "language": "ar",
         "citation_style": "unspecified"}
    cur = req
    o._current_request = staticmethod(lambda t, _c=cur: _c)
    # نفس التسلسل الذي في الكود
    for key, mv, dv in (
        ("action", (str(_iv.get("action") or "").lower() or None), W._task_action(cur)),
        ("sourcing_mode", (_iv.get("sourcing") if _iv.get("sourcing") in ("cited","uncited","none") else None), W._sourcing_mode(cur)),
    ):
        W._settle(c, key, mv, dv, "فهم الطلب")
    _cs = _iv.get("citation_style")
    W._settle(c, "citation_style", (_cs if _cs and str(_cs).lower() not in ("null","none","unspecified") else None),
              None, "فهم الطلب", explicit=W._requested_citation_style(cur))
    _wt = _iv.get("wants_table")
    got = W._settle(c, "want_table", (_wt if isinstance(_wt, bool) else None),
                    (True if W._wants_table(cur) else None), "فهم الطلب")
    if got is False:
        c["tables_forbidden"] = True; c.pop("want_table", None)
    if _iv.get("pages"): W._settle(c, "target_pages", _iv["pages"], None, "فهم الطلب")
    if _iv.get("words"): W._settle(c, "target_words", _iv["words"], None, "فهم الطلب")

    print(f"\n■ {name}: {req[:58]}…")
    for k, v in (c.get("decisions") or {}).items():
        print(f"    {k:16s} = {str(v['value']):10s} ← {v['by']}")
    print(f"    tables_forbidden = {c.get('tables_forbidden', False)}")
print("\n" + "═"*74)
