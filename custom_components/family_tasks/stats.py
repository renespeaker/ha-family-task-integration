"""Statistics from the ledger: this week, this month, streaks.

Free of Home Assistant imports: the caller turns every booking's timestamp into
a local calendar day first, so this module only counts days.

A booking counts on the day it was booked. The card books a task when it sees
it checked off, so a task ticked in another app counts on the day the card
next shows it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .ledger import Booking


@dataclass(frozen=True)
class Stats:
    """One person's numbers for the sensor."""

    week_points: int
    month_points: int
    week_tasks: int
    month_tasks: int
    streak: int  # days in a row up to today (or yesterday) with a task
    best_streak: int


def person_stats(bookings: list[tuple[date, Booking]], person: str, today: date) -> Stats:
    """Count a person's bookings; `bookings` pairs each booking with its local day."""
    week_start = today - timedelta(days=today.weekday())  # Monday
    month_start = today.replace(day=1)
    week_points = month_points = week_tasks = month_tasks = 0
    task_days: set[date] = set()
    for day, b in bookings:
        if b.person != person or b.kind not in ("award", "adjust"):
            continue  # spending and points handed over for a chore are no work done
        # award and adjust count as points earned; only awards are tasks
        if day >= week_start:
            week_points += b.points
        if day >= month_start:
            month_points += b.points
        if b.kind == "award":
            task_days.add(day)
            if day >= week_start:
                week_tasks += 1
            if day >= month_start:
                month_tasks += 1
    return Stats(
        week_points,
        month_points,
        week_tasks,
        month_tasks,
        _current_streak(task_days, today),
        _best_streak(task_days),
    )


def _current_streak(days: set[date], today: date) -> int:
    """Days in a row ending today; if nothing yet today, ending yesterday."""
    day = today if today in days else today - timedelta(days=1)
    n = 0
    while day in days:
        n += 1
        day -= timedelta(days=1)
    return n


def _best_streak(days: set[date]) -> int:
    best = 0
    for day in days:
        if day - timedelta(days=1) in days:
            continue  # not the start of a run
        n = 1
        while day + timedelta(days=n) in days:
            n += 1
        best = max(best, n)
    return best
