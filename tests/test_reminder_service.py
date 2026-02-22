from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from birthday_bot.config_store import save_config_atomic
from birthday_bot.models import AppConfig, BirthdayEntry
from birthday_bot.reminder_service import ReminderService


@dataclass
class FakeBot:
    sent_messages: list[tuple[int, str]] = field(default_factory=list)

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))


def test_dispatch_deduplicates_same_day(tmp_path: Path) -> None:
    config_path = tmp_path / "birthdays.toml"
    index_path = tmp_path / "person_index.json"
    state_path = tmp_path / "reminder_state.json"

    save_config_atomic(
        config_path,
        AppConfig(
            timezone="UTC",
            daily_send_time="09:00",
            leap_day_rule="feb28",
            birthdays=[
                BirthdayEntry(
                    name="Alice",
                    month=3,
                    day=14,
                    year=1990,
                    reminder_offsets=[7],
                )
            ],
        ),
    )

    fake_bot = FakeBot()
    service = ReminderService(
        bot=fake_bot,
        chat_id=100,
        config_path=config_path,
        person_index_path=index_path,
        reminder_state_path=state_path,
    )

    today = date(2026, 3, 7)

    first_count = __import__("asyncio").run(service.dispatch_for_date(today))
    second_count = __import__("asyncio").run(service.dispatch_for_date(today))

    assert first_count == 1
    assert second_count == 0
    assert len(fake_bot.sent_messages) == 1


def test_dispatch_next_day_allows_new_send(tmp_path: Path) -> None:
    config_path = tmp_path / "birthdays.toml"
    index_path = tmp_path / "person_index.json"
    state_path = tmp_path / "reminder_state.json"

    save_config_atomic(
        config_path,
        AppConfig(
            timezone="UTC",
            daily_send_time="09:00",
            leap_day_rule="feb28",
            birthdays=[
                BirthdayEntry(
                    name="Alice",
                    month=3,
                    day=14,
                    year=1990,
                    reminder_offsets=[7, 6],
                )
            ],
        ),
    )

    fake_bot = FakeBot()
    service = ReminderService(
        bot=fake_bot,
        chat_id=100,
        config_path=config_path,
        person_index_path=index_path,
        reminder_state_path=state_path,
    )

    day_one = date(2026, 3, 7)
    day_two = date(2026, 3, 8)

    __import__("asyncio").run(service.dispatch_for_date(day_one))
    count_day_two = __import__("asyncio").run(service.dispatch_for_date(day_two))

    assert count_day_two == 1
    assert len(fake_bot.sent_messages) == 2
