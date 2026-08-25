"""
schedule-core — calendar and scheduling engine.
Vendored icalendar, pytz, apscheduler in vendored/;
used by the `calendar` and `scheduler` tools.
"""
import os, sys
_V = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendored")
if os.path.isdir(_V) and _V not in sys.path:
    sys.path.insert(0, _V)
