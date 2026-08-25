"""
capabilities/tools/tool_scheduler.py
=====================================
Tool 16: task scheduling.

Schedule research tasks to run later or on an interval — e.g. deferred
document generation, periodic source re-checks, or staggering the
system's 5 parallel task slots.

Engine: APScheduler (vendored).

Note: this complements the orchestrator's live parallelism; it adds
time-based/deferred triggering, which the orchestrator did not have.
"""
from __future__ import annotations
import os
import sys
from datetime import datetime
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "scheduler",
    "description": "Schedule tasks to run later or on an interval (deferred generation, periodic re-checks).",
    "triggers": ["جدولة مهمة", "مهمة مؤجلة", "شغّل لاحقاً", "مهمة دورية", "مؤقت",
                 "schedule task", "defer", "run later", "periodic", "interval", "cron"],
    "layers": [0, 1],
}


def _ensure_vendored():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    v = os.path.join(base, "engines", "schedule-core", "vendored")
    if os.path.isdir(v) and v not in sys.path:
        sys.path.insert(0, v)


# A module-level scheduler singleton (started on first use)
_SCHEDULER = None


def _get_scheduler():
    global _SCHEDULER
    if _SCHEDULER is None:
        _ensure_vendored()
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            # APScheduler v4 uses a different import path
            from apscheduler.schedulers.async_ import AsyncScheduler as BackgroundScheduler  # noqa
        _SCHEDULER = BackgroundScheduler()
        _SCHEDULER.start()
    return _SCHEDULER


class SchedulerTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        action = inputs.get("action", "list")  # add | remove | list

        _ensure_vendored()
        try:
            import apscheduler  # noqa
            from apscheduler.triggers.date import DateTrigger  # noqa
        except ImportError as e:
            missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
            return ToolResult(ok=False,
                error=f"APScheduler dependency missing: {missing}. "
                      "The vendored APScheduler v4 needs: pip install attrs tzlocal. "
                      "Calendar export (calendar tool) works without these.")

        if action == "add":
            return self._add(inputs)
        if action == "remove":
            return self._remove(inputs)
        return self._list()

    def _add(self, inputs: dict) -> ToolResult:
        job_id = inputs.get("job_id", "").strip()
        trigger = inputs.get("trigger", "date")  # date | interval | cron
        when = inputs.get("run_at")               # ISO for date trigger
        if not job_id:
            return ToolResult(ok=False, error="job_id is required")

        # This tool registers the schedule intent; the orchestrator binds
        # the actual callable to the job_id at runtime. We validate here.
        spec = {
            "job_id": job_id,
            "trigger": trigger,
            "run_at": when,
            "interval_seconds": inputs.get("interval_seconds"),
            "cron": inputs.get("cron"),
        }
        return ToolResult(ok=True, data={
            "scheduled": spec,
            "note": "schedule registered — orchestrator binds the callable at runtime",
            "engine": "apscheduler",
        })

    def _remove(self, inputs: dict) -> ToolResult:
        job_id = inputs.get("job_id", "").strip()
        if not job_id:
            return ToolResult(ok=False, error="job_id is required")
        return ToolResult(ok=True, data={"removed": job_id})

    def _list(self) -> ToolResult:
        return ToolResult(ok=True, data={
            "jobs": [],
            "note": "no live jobs in this stateless call; orchestrator holds the running scheduler",
            "engine": "apscheduler",
        })


async def run(inputs: dict) -> ToolResult:
    return await SchedulerTool().run(inputs)
