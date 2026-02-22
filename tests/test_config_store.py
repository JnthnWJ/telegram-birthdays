from pathlib import Path

import pytest

from birthday_bot.config_store import load_config, save_config_atomic, update_birthday
from birthday_bot.models import AppConfig, BirthdayEntry


def test_roundtrip_config(tmp_path: Path) -> None:
    path = tmp_path / "birthdays.toml"
    config = AppConfig(
        timezone="America/Los_Angeles",
        daily_send_time="09:00",
        leap_day_rule="feb28",
        birthdays=[
            BirthdayEntry(
                name="Alice",
                month=3,
                day=14,
                year=1990,
                reminder_offsets=[30, 7, 1, 0],
            )
        ],
    )

    save_config_atomic(path, config)
    loaded = load_config(path)

    assert loaded.timezone == config.timezone
    assert loaded.daily_send_time == config.daily_send_time
    assert loaded.leap_day_rule == config.leap_day_rule
    assert loaded.birthdays[0].name == "Alice"
    assert loaded.birthdays[0].reminder_offsets == [30, 7, 1, 0]


def test_invalid_offset_rejected(tmp_path: Path) -> None:
    path = tmp_path / "birthdays.toml"
    path.write_text(
        """
timezone = "America/Los_Angeles"
daily_send_time = "09:00"
leap_day_rule = "feb28"

[[birthdays]]
name = "Alice"
month = 3
day = 14
reminder_offsets = [-1]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(path)


def test_update_birthday_replaces_selected_entry(tmp_path: Path) -> None:
    path = tmp_path / "birthdays.toml"
    save_config_atomic(
        path,
        AppConfig(
            timezone="America/Los_Angeles",
            daily_send_time="09:00",
            leap_day_rule="feb28",
            birthdays=[
                BirthdayEntry(name="Alice", month=3, day=14, year=1990, reminder_offsets=[30, 7, 1, 0]),
                BirthdayEntry(name="Bob", month=8, day=22, year=None, reminder_offsets=[7, 0]),
            ],
        ),
    )

    update_birthday(
        path,
        index=1,
        updated_birthday=BirthdayEntry(
            name="Bobby",
            month=8,
            day=23,
            year=2001,
            reminder_offsets=[14, 1, 0],
        ),
    )
    loaded = load_config(path)

    assert loaded.birthdays[0].name == "Alice"
    assert loaded.birthdays[1].name == "Bobby"
    assert loaded.birthdays[1].month == 8
    assert loaded.birthdays[1].day == 23
    assert loaded.birthdays[1].year == 2001
    assert loaded.birthdays[1].reminder_offsets == [14, 1, 0]


def test_update_birthday_rejects_invalid_index(tmp_path: Path) -> None:
    path = tmp_path / "birthdays.toml"
    save_config_atomic(
        path,
        AppConfig(
            timezone="America/Los_Angeles",
            daily_send_time="09:00",
            leap_day_rule="feb28",
            birthdays=[],
        ),
    )

    with pytest.raises(IndexError):
        update_birthday(
            path,
            index=0,
            updated_birthday=BirthdayEntry(
                name="Alice",
                month=3,
                day=14,
                year=1990,
                reminder_offsets=[30, 7, 1, 0],
            ),
        )
