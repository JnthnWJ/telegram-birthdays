from __future__ import annotations

from datetime import date

from birthday_bot.models import BirthdayEntry


class InvalidBirthdayError(ValueError):
    pass


def is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def validate_month_day(month: int, day: int, *, allow_feb_29: bool = True) -> None:
    if month < 1 or month > 12:
        raise InvalidBirthdayError(f"Invalid month: {month}")

    if day < 1 or day > 31:
        raise InvalidBirthdayError(f"Invalid day: {day}")

    year = 2000 if allow_feb_29 else 2001
    try:
        date(year, month, day)
    except ValueError as exc:
        raise InvalidBirthdayError(f"Invalid month/day combination: {month:02d}-{day:02d}") from exc


def birthday_date_for_year(entry: BirthdayEntry, year: int, leap_day_rule: str) -> date:
    if entry.month == 2 and entry.day == 29 and not is_leap_year(year):
        if leap_day_rule == "feb28":
            return date(year, 2, 28)
        if leap_day_rule == "mar1":
            return date(year, 3, 1)
        raise InvalidBirthdayError(f"Unsupported leap day rule: {leap_day_rule}")
    return date(year, entry.month, entry.day)


def next_birthday(entry: BirthdayEntry, today: date, leap_day_rule: str) -> date:
    this_year = birthday_date_for_year(entry, today.year, leap_day_rule)
    if this_year >= today:
        return this_year
    return birthday_date_for_year(entry, today.year + 1, leap_day_rule)


def days_until_birthday(entry: BirthdayEntry, today: date, leap_day_rule: str) -> int:
    nxt = next_birthday(entry, today, leap_day_rule)
    return (nxt - today).days


def turning_age(entry: BirthdayEntry, birthday_occurrence: date) -> int | None:
    if entry.year is None:
        return None
    return birthday_occurrence.year - entry.year
