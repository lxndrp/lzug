"""Pure iCalendar rendering from detached Calendar event projections."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from backend.calendar.ports import CalendarEventSnapshot


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_local(value: str, time_zone: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(value.replace(" ", "T"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=time_zone)
    return parsed.astimezone(time_zone)


def render_calendar(events: Iterable[CalendarEventSnapshot], name: str) -> str:
    """Serialize fully materialized event values without persistence or HTTP access."""
    calendar = Calendar()
    calendar.add("VERSION", "2.0")
    calendar.add("PRODID", "-//lzug//Personal Calendar//EN")
    calendar.add("CALSCALE", "GREGORIAN")
    calendar.add("METHOD", "PUBLISH")
    calendar.add("X-WR-CALNAME", name)
    for event in events:
        zone = ZoneInfo(event.time_zone)
        start = _parse_local(event.starts_at, zone)
        end = _parse_local(event.ends_at, zone)
        description = f"Rolle: {event.role}\nDetails: /api/confirmed-plan-days/{event.exam_day_id}"
        component = Event()
        component.add("UID", f"{event.external_event_id}@lzug")
        component.add("SEQUENCE", event.version)
        component.add("DTSTAMP", _now())
        component.add("DTSTART", start)
        component.add("DTEND", end)
        component.add("SUMMARY", event.round_name + " – " + event.role)
        component.add("LOCATION", event.location)
        component.add("DESCRIPTION", description)
        component.add("STATUS", "CANCELLED" if event.status == "cancelled" else "CONFIRMED")
        calendar.add_component(component)
    return calendar.to_ical().decode("utf-8")
