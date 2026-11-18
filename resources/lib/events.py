# -*- coding: utf-8 -*-
"""Turns raw Protect event messages into "should we pop up?" decisions.

No Kodi imports here, so this file can be tested on any computer.
"""
from collections import OrderedDict

SMART_KINDS = ("person", "vehicle", "animal", "package")
ALL_KINDS = SMART_KINDS + ("ring", "motion")

KIND_NAMES = {
    "person": "Person",
    "vehicle": "Vehicle",
    "animal": "Animal",
    "package": "Package",
    "ring": "Doorbell",
    "motion": "Motion",
    "test": "Test",
}


def kinds_of(item):
    """What happened in this event, as a set like {"person"}."""
    etype = item.get("type") or ""
    if etype == "ring":
        return {"ring"}
    if etype == "motion":
        return {"motion"}
    if etype.startswith("smartDetect"):   # smartDetectZone, smartDetectLine, ...
        return {k for k in (item.get("smartDetectTypes") or []) if k in SMART_KINDS}
    return set()


def describe(kinds):
    order = list(ALL_KINDS) + ["test"]
    return " + ".join(KIND_NAMES.get(k, k) for k in sorted(kinds, key=lambda k: order.index(k) if k in order else 99))


def in_quiet_hours(hour, start, end):
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end   # wraps past midnight, e.g. 23 -> 7


class EventTracker(object):
    """Remembers recent events so we don't pop up twice for the same thing."""

    def __init__(self, max_events=500):
        self.events = OrderedDict()   # event id -> merged event item
        self.alerted = {}             # event id -> kinds we already popped up for
        self.last_popup = {}          # camera id -> time of last pop-up
        self.max_events = max_events

    def feed(self, msg):
        """Return (event_id, camera_id, kinds) or None if it isn't an event."""
        if not isinstance(msg, dict):
            return None
        item = msg.get("item")
        if not isinstance(item, dict):
            return None
        if item.get("modelKey", "event") != "event":
            return None
        eid = item.get("id")
        if not eid:
            return None
        # "update" messages may only carry the fields that changed,
        # so merge them into what we already know about this event.
        merged = dict(self.events.get(eid, {}))
        merged.update(item)
        self.events[eid] = merged
        self.events.move_to_end(eid)
        while len(self.events) > self.max_events:
            old, _ = self.events.popitem(last=False)
            self.alerted.pop(old, None)
        return eid, merged.get("device"), kinds_of(merged)

    def should_alert(self, eid, camera_id, kinds, now, cooldown, bypass_cooldown=False):
        """Return the new kinds worth a pop-up (empty set = stay quiet)."""
        new = set(kinds) - self.alerted.get(eid, set())
        if not new or not camera_id:
            return set()
        self.alerted.setdefault(eid, set()).update(new)
        last = self.last_popup.get(camera_id)
        if not bypass_cooldown and last is not None and now - last < cooldown:
            return set()
        self.last_popup[camera_id] = now
        return new
