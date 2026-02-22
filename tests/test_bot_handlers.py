from dataclasses import dataclass
from datetime import date

import pytest

from birthday_bot.bot_handlers import (
    BirthdayListRow,
    _format_reminder_offsets,
    _render_list_message,
    is_authorized,
    parse_birthday_text,
    parse_offsets_text,
)
from birthday_bot.settings import Settings


def test_parse_birthday_text_full_date() -> None:
    month, day, year = parse_birthday_text("1990-03-14")
    assert (month, day, year) == (3, 14, 1990)


def test_parse_birthday_text_short_date() -> None:
    month, day, year = parse_birthday_text("03-14")
    assert (month, day, year) == (3, 14, None)


def test_parse_birthday_text_invalid_real_date() -> None:
    with pytest.raises(ValueError):
        parse_birthday_text("2025-02-29")


def test_parse_offsets_blank_uses_default() -> None:
    offsets, used_default = parse_offsets_text("   ")
    assert offsets == [30, 7, 1, 0]
    assert used_default is True


def test_parse_offsets_sorts_and_dedupes() -> None:
    offsets, used_default = parse_offsets_text("1,7,1,0")
    assert offsets == [7, 1, 0]
    assert used_default is False


def test_parse_offsets_skip_uses_default() -> None:
    offsets, used_default = parse_offsets_text("skip")
    assert offsets == [30, 7, 1, 0]
    assert used_default is True


def test_format_reminder_offsets() -> None:
    assert _format_reminder_offsets((30, 7, 1, 0)) == "30d, 7d, 1d, day-of"


def test_render_list_message_structured_output() -> None:
    message = _render_list_message(
        [
            BirthdayListRow(
                name="Nik Hold",
                days_until=81,
                next_date=date(2026, 5, 14),
                turning_age=None,
                reminder_offsets=(7, 0),
            ),
            BirthdayListRow(
                name="Dad",
                days_until=181,
                next_date=date(2026, 8, 22),
                turning_age=67,
                reminder_offsets=(30, 7, 1, 0),
            ),
        ]
    )

    assert message == (
        "Tracked birthdays (2)\n"
        "Sorted by soonest:\n"
        "1. Nik Hold\n"
        "   In 81d | Next 2026-05-14 | Reminders 7d, day-of\n"
        "\n"
        "2. Dad\n"
        "   In 181d | Next 2026-08-22 | Turning 67 | Reminders 30d, 7d, 1d, day-of"
    )


@dataclass
class FakeUser:
    id: int


@dataclass
class FakeChat:
    id: int


@dataclass
class FakeUpdate:
    effective_user: FakeUser
    effective_chat: FakeChat


def test_is_authorized_true() -> None:
    settings = Settings(
        telegram_bot_token="token",
        telegram_allowed_user_id=111,
        telegram_allowed_chat_id=222,
        birthday_config_path=__import__("pathlib").Path("config/birthdays.toml"),
        person_index_path=__import__("pathlib").Path("data/person_index.json"),
        reminder_state_path=__import__("pathlib").Path("data/reminder_state.json"),
    )

    update = FakeUpdate(effective_user=FakeUser(id=111), effective_chat=FakeChat(id=222))
    assert is_authorized(update, settings) is True


def test_is_authorized_false() -> None:
    settings = Settings(
        telegram_bot_token="token",
        telegram_allowed_user_id=111,
        telegram_allowed_chat_id=222,
        birthday_config_path=__import__("pathlib").Path("config/birthdays.toml"),
        person_index_path=__import__("pathlib").Path("data/person_index.json"),
        reminder_state_path=__import__("pathlib").Path("data/reminder_state.json"),
    )

    update = FakeUpdate(effective_user=FakeUser(id=111), effective_chat=FakeChat(id=999))
    assert is_authorized(update, settings) is False
