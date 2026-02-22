from __future__ import annotations

import os
import tempfile
import tomllib
from datetime import date
from pathlib import Path

from birthday_bot.date_logic import InvalidBirthdayError, validate_month_day
from birthday_bot.models import AppConfig, BirthdayEntry

ALLOWED_LEAP_DAY_RULES = {"feb28", "mar1"}


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _parse_daily_send_time(value: str) -> str:
    pieces = value.split(":")
    if len(pieces) != 2:
        raise ValueError("daily_send_time must be in HH:MM format")

    hour, minute = pieces
    if not hour.isdigit() or not minute.isdigit():
        raise ValueError("daily_send_time must contain numeric hour/minute")

    hour_i = int(hour)
    minute_i = int(minute)
    if hour_i < 0 or hour_i > 23 or minute_i < 0 or minute_i > 59:
        raise ValueError("daily_send_time must be a valid 24-hour time")

    return f"{hour_i:02d}:{minute_i:02d}"


def _validate_offsets(offsets: list[int]) -> list[int]:
    if not offsets:
        raise ValueError("reminder_offsets must not be empty")
    if any((not isinstance(offset, int) or offset < 0) for offset in offsets):
        raise ValueError("reminder_offsets values must be non-negative integers")

    unique_sorted = sorted(set(offsets), reverse=True)
    return unique_sorted


def validate_config(config: AppConfig) -> AppConfig:
    timezone = config.timezone.strip()
    if not timezone:
        raise ValueError("timezone must not be empty")

    daily_send_time = _parse_daily_send_time(config.daily_send_time)

    leap_day_rule = config.leap_day_rule.strip().lower()
    if leap_day_rule not in ALLOWED_LEAP_DAY_RULES:
        raise ValueError(f"leap_day_rule must be one of {sorted(ALLOWED_LEAP_DAY_RULES)}")

    validated_birthdays: list[BirthdayEntry] = []
    for birthday in config.birthdays:
        name = birthday.name.strip()
        if not name:
            raise ValueError("birthday name must not be empty")

        try:
            validate_month_day(birthday.month, birthday.day, allow_feb_29=True)
        except InvalidBirthdayError as exc:
            raise ValueError(str(exc)) from exc

        if birthday.year is not None:
            if birthday.year < 1900 or birthday.year > 3000:
                raise ValueError("year must be between 1900 and 3000 when provided")
            try:
                date(birthday.year, birthday.month, birthday.day)
            except ValueError as exc:
                raise ValueError(str(exc)) from exc

        validated_birthdays.append(
            BirthdayEntry(
                name=name,
                month=int(birthday.month),
                day=int(birthday.day),
                year=int(birthday.year) if birthday.year is not None else None,
                reminder_offsets=_validate_offsets(list(birthday.reminder_offsets)),
            )
        )

    return AppConfig(
        timezone=timezone,
        daily_send_time=daily_send_time,
        leap_day_rule=leap_day_rule,
        birthdays=validated_birthdays,
    )


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("rb") as file_obj:
        data = tomllib.load(file_obj)

    birthdays: list[BirthdayEntry] = []
    for row in data.get("birthdays", []):
        birthdays.append(
            BirthdayEntry(
                name=str(row.get("name", "")),
                month=int(row.get("month", 0)),
                day=int(row.get("day", 0)),
                year=int(row["year"]) if row.get("year") is not None else None,
                reminder_offsets=[int(v) for v in row.get("reminder_offsets", [])],
            )
        )

    config = AppConfig(
        timezone=str(data.get("timezone", "")),
        daily_send_time=str(data.get("daily_send_time", "")),
        leap_day_rule=str(data.get("leap_day_rule", "feb28")),
        birthdays=birthdays,
    )
    return validate_config(config)


def render_config(config: AppConfig) -> str:
    validated = validate_config(config)

    lines: list[str] = [
        f'timezone = "{_toml_escape(validated.timezone)}"',
        f'daily_send_time = "{validated.daily_send_time}"',
        f'leap_day_rule = "{validated.leap_day_rule}"',
        "",
        "# Reminder: if /add wizard offsets are left blank, default offsets are [30, 7, 1, 0].",
        "",
    ]

    for person in validated.birthdays:
        lines.append("[[birthdays]]")
        lines.append(f'name = "{_toml_escape(person.name)}"')
        lines.append(f"month = {person.month}")
        lines.append(f"day = {person.day}")
        if person.year is not None:
            lines.append(f"year = {person.year}")
        offsets = ", ".join(str(offset) for offset in person.reminder_offsets)
        lines.append(f"reminder_offsets = [{offsets}]")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def save_config_atomic(path: Path, config: AppConfig) -> None:
    rendered = render_config(config)
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temp_file:
        temp_file.write(rendered)
        temp_name = temp_file.name

    os.replace(temp_name, path)


def ensure_default_config(path: Path) -> None:
    if path.exists():
        return

    default_config = AppConfig(
        timezone="America/Los_Angeles",
        daily_send_time="09:00",
        leap_day_rule="feb28",
        birthdays=[],
    )
    save_config_atomic(path, default_config)


def append_birthday(path: Path, new_birthday: BirthdayEntry) -> AppConfig:
    config = load_config(path)
    updated = AppConfig(
        timezone=config.timezone,
        daily_send_time=config.daily_send_time,
        leap_day_rule=config.leap_day_rule,
        birthdays=[*config.birthdays, new_birthday],
    )
    save_config_atomic(path, updated)
    return updated
