from pathlib import Path

import pytest

from birthday_bot.config_store import load_config, save_config_atomic
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
