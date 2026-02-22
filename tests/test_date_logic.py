from datetime import date

from birthday_bot.date_logic import days_until_birthday, next_birthday
from birthday_bot.models import BirthdayEntry


def test_days_until_future_date_same_year() -> None:
    entry = BirthdayEntry(name="A", month=3, day=14, year=None, reminder_offsets=[7])
    today = date(2026, 3, 1)

    assert days_until_birthday(entry, today, "feb28") == 13


def test_days_until_next_year_after_passed() -> None:
    entry = BirthdayEntry(name="A", month=1, day=2, year=None, reminder_offsets=[7])
    today = date(2026, 6, 1)

    assert days_until_birthday(entry, today, "feb28") == (date(2027, 1, 2) - today).days


def test_feb_29_maps_to_feb_28_on_non_leap_year() -> None:
    entry = BirthdayEntry(name="Leap", month=2, day=29, year=2000, reminder_offsets=[1])
    today = date(2025, 2, 27)

    assert next_birthday(entry, today, "feb28") == date(2025, 2, 28)
    assert days_until_birthday(entry, today, "feb28") == 1


def test_feb_29_keeps_date_on_leap_year() -> None:
    entry = BirthdayEntry(name="Leap", month=2, day=29, year=2000, reminder_offsets=[1])
    today = date(2028, 2, 27)

    assert next_birthday(entry, today, "feb28") == date(2028, 2, 29)
