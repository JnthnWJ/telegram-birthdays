from __future__ import annotations

from dataclasses import dataclass


DEFAULT_REMINDER_OFFSETS = [30, 7, 1, 0]


@dataclass(frozen=True)
class BirthdayEntry:
    name: str
    month: int
    day: int
    year: int | None
    reminder_offsets: list[int]


@dataclass(frozen=True)
class AppConfig:
    timezone: str
    daily_send_time: str
    leap_day_rule: str
    birthdays: list[BirthdayEntry]


@dataclass(frozen=True)
class BirthdayWithId:
    person_id: str
    entry: BirthdayEntry
