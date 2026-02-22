from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from telegram import Bot

from birthday_bot.config_store import load_config
from birthday_bot.date_logic import days_until_birthday, next_birthday, turning_age
from birthday_bot.identity_index import assign_and_persist_ids
from birthday_bot.reminder_state import ReminderState, dedupe_key, load_state, prune_old_keys, save_state_atomic

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DueReminder:
    person_id: str
    person_name: str
    offset_days: int
    next_birthday_date: date
    days_until: int
    turning_age: int | None


class ReminderService:
    def __init__(
        self,
        *,
        bot: Bot,
        chat_id: int,
        config_path,
        person_index_path,
        reminder_state_path,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._config_path = config_path
        self._person_index_path = person_index_path
        self._reminder_state_path = reminder_state_path

    async def dispatch_for_date(self, today: date) -> int:
        config = load_config(self._config_path)
        person_ids = assign_and_persist_ids(self._person_index_path, config.birthdays)

        state = load_state(self._reminder_state_path)
        prune_old_keys(state, today)

        due = self._due_reminders(today, config, person_ids, state)
        if not due:
            save_state_atomic(self._reminder_state_path, state)
            return 0

        sent_count = 0
        for reminder in due:
            message = self._format_reminder_message(reminder)
            await self._bot.send_message(chat_id=self._chat_id, text=message)
            state.sent_keys.add(dedupe_key(today, reminder.person_id, reminder.offset_days))
            sent_count += 1

        save_state_atomic(self._reminder_state_path, state)
        LOGGER.info("Sent %s reminders for %s", sent_count, today.isoformat())
        return sent_count

    def _due_reminders(self, today: date, config, person_ids: list[str], state: ReminderState) -> list[DueReminder]:
        due: list[DueReminder] = []

        for entry, person_id in zip(config.birthdays, person_ids, strict=True):
            days_until = days_until_birthday(entry, today, config.leap_day_rule)
            if days_until not in entry.reminder_offsets:
                continue

            key = dedupe_key(today, person_id, days_until)
            if key in state.sent_keys:
                continue

            next_date = next_birthday(entry, today, config.leap_day_rule)
            due.append(
                DueReminder(
                    person_id=person_id,
                    person_name=entry.name,
                    offset_days=days_until,
                    next_birthday_date=next_date,
                    days_until=days_until,
                    turning_age=turning_age(entry, next_date),
                )
            )

        due.sort(key=lambda item: (item.days_until, item.person_name.lower()))
        return due

    @staticmethod
    def _format_reminder_message(reminder: DueReminder) -> str:
        if reminder.days_until == 0:
            prefix = f"Today is {reminder.person_name}'s birthday"
        elif reminder.days_until == 1:
            prefix = f"{reminder.person_name}'s birthday is tomorrow"
        else:
            prefix = f"{reminder.person_name}'s birthday is in {reminder.days_until} days"

        if reminder.turning_age is None:
            age_text = ""
        else:
            age_text = f" (turning {reminder.turning_age})"

        return (
            f"{prefix}{age_text}. "
            f"Date: {reminder.next_birthday_date.isoformat()}."
        )


def parse_time_string(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def now_in_timezone(timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    return datetime.now(tz)
