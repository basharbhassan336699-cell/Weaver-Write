"""
capabilities/tools/tool_calendar.py
====================================
Tool 15: calendar (.ics) operations.

Create and read iCalendar files — useful for exporting a research
project's timeline: submission deadlines, milestones, review dates, or
a study schedule the user can import into any calendar app.

Engine: icalendar (vendored) + pytz (vendored) for timezones.
"""
from __future__ import annotations
import os
import sys
from datetime import datetime
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "calendar",
    "description": "Create or read iCalendar (.ics) files for research timelines, deadlines, and milestones.",
    "triggers": ["تقويم", "موعد", "جدول زمني", "تسليم", "ملف ics", "مواعيد",
                 "calendar", "deadline", "schedule", "ics file", "milestone", "event"],
    "layers": [8],
}


def _ensure_vendored():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    v = os.path.join(base, "engines", "schedule-core", "vendored")
    if os.path.isdir(v) and v not in sys.path:
        sys.path.insert(0, v)


class CalendarTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        action = inputs.get("action", "create")  # create | read
        if action == "read":
            return await self._read(inputs)
        return await self._create(inputs)

    async def _create(self, inputs: dict) -> ToolResult:
        events = inputs.get("events", [])
        if not events:
            return ToolResult(ok=False, error="events list is required")

        output = inputs.get("output_path", "./output/schedule.ics")
        cal_name = inputs.get("calendar_name", "Weaver Write Schedule")
        tz_name = inputs.get("timezone", "Asia/Dubai")

        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        _ensure_vendored()

        try:
            from icalendar import Calendar, Event
        except ImportError:
            return ToolResult(ok=False, error="icalendar not available")

        # Prefer Python's built-in zoneinfo (3.9+); fall back to pytz
        try:
            from zoneinfo import ZoneInfo
            def _localize(dt):
                return dt.replace(tzinfo=ZoneInfo(tz_name)) if dt.tzinfo is None else dt
        except ImportError:
            import pytz
            _tz = pytz.timezone(tz_name)
            def _localize(dt):
                return _tz.localize(dt) if dt.tzinfo is None else dt

        cal = Calendar()
        cal.add("prodid", "-//Weaver Write//Research Schedule//EN")
        cal.add("version", "2.0")
        cal.add("x-wr-calname", cal_name)

        count = 0
        for ev in events:
            event = Event()
            event.add("summary", ev.get("title", "Untitled"))
            # start/end as ISO strings or date objects
            start = ev.get("start")
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            if start:
                event.add("dtstart", _localize(start))
            end = ev.get("end")
            if isinstance(end, str):
                end = datetime.fromisoformat(end)
            if end:
                event.add("dtend", _localize(end))
            if ev.get("description"):
                event.add("description", ev["description"])
            if ev.get("location"):
                event.add("location", ev["location"])
            cal.add_component(event)
            count += 1

        with open(output, "wb") as f:
            f.write(cal.to_ical())

        return ToolResult(ok=True, data={
            "output_path": output, "events": count, "engine": "icalendar",
        })

    async def _read(self, inputs: dict) -> ToolResult:
        path = inputs.get("path", "").strip()
        if not path or not os.path.exists(path):
            return ToolResult(ok=False, error=f"file not found: {path}")

        _ensure_vendored()
        try:
            from icalendar import Calendar
        except ImportError:
            return ToolResult(ok=False, error="icalendar not available")

        with open(path, "rb") as f:
            cal = Calendar.from_ical(f.read())

        events = []
        for comp in cal.walk("VEVENT"):
            events.append({
                "title": str(comp.get("summary", "")),
                "start": str(comp.get("dtstart").dt) if comp.get("dtstart") else None,
                "end": str(comp.get("dtend").dt) if comp.get("dtend") else None,
                "description": str(comp.get("description", "")),
            })
        return ToolResult(ok=True, data={
            "events": events, "count": len(events), "engine": "icalendar",
        })


async def run(inputs: dict) -> ToolResult:
    return await CalendarTool().run(inputs)
