# schedule-core — calendar & scheduling engine

Backs the `calendar` and `scheduler` tools.

## vendored/ (bundled, Termux-friendly)
| Library | Purpose | Used by |
|---------|---------|---------|
| icalendar | Create/read .ics files | calendar |
| pytz | Timezone definitions | calendar |
| apscheduler | Deferred/interval/cron task scheduling | scheduler |

## Duplicate NOT bundled
- **google-api** (15.7MB) — Google Calendar/services overlap with
  open-connector-core (1282 providers) and are far heavier; use the
  connector path instead if Google Calendar sync is ever needed.

## Overlap notes
- `pytz` overlaps slightly with the bundled `time` MCP server, but is kept
  because icalendar needs it directly for event localization.
- `scheduler` complements the orchestrator's live 5-slot parallelism by
  adding time-based/deferred triggering the orchestrator lacked.
