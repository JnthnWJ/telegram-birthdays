from __future__ import annotations

import hashlib
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

TODAY_TEMPLATES = (
    "🎉 It's {person_name}'s birthday today!\nDate: {date}\nThis is not a drill.",
    "🥳 Today we celebrate {person_name}.\nDate: {date}\nGo make it count.",
    "🚨 Birthday Alert 🚨\n{person_name}'s big day has arrived.\nDate: {date}",
    "🎈 {person_name} leveled up today.\nDate: {date}\nAchievement unlocked.",
    "🎂 It's {person_name} Day™.\nDate: {date}",
    "📢 Public service announcement:\n{person_name} was born on this day.\nDate: {date}\nCake is appropriate.",
    "🎊 The calendar has spoken - it's {person_name}'s birthday.\nDate: {date}",
    "🗓️ Marked, confirmed, undeniable: {person_name}'s birthday is today.\nDate: {date}",
    "🎉 Today belongs to {person_name}.\nDate: {date}",
    "🚀 Launch sequence complete.\nIt's {person_name}'s birthday.\nDate: {date}",
    "🎂 Celebration protocol activated for {person_name}.\nDate: {date}",
    "🌟 Today's featured human: {person_name}.\nDate: {date}",
)

TOMORROW_TEMPLATES = (
    "⏳ 24-hour warning.\n{person_name}'s birthday is tomorrow.\nDate: {date}",
    "🎁 Heads up - {person_name}'s big day is tomorrow.\nDate: {date}",
    "🗓️ Tomorrow: {person_name}'s birthday.\nDate: {date}\nPlan accordingly.",
    "⚠️ Birthday approaching.\n{person_name} celebrates tomorrow.\nDate: {date}",
    "🎈 One sleep left until {person_name}'s birthday.\nDate: {date}",
    "⏰ Reminder: {person_name}'s birthday lands tomorrow.\nDate: {date}",
    "🎉 Almost {person_name} Day.\nTomorrow is the big one.\nDate: {date}",
    "📦 Final call before {person_name}'s birthday.\nDate: {date}",
    "🚨 Tomorrow, {person_name} officially levels up.\nDate: {date}",
    "🗓️ The countdown ends tomorrow - {person_name}'s birthday.\nDate: {date}",
)

IN_DAYS_TEMPLATES = (
    "📆 Countdown: {days_until} days until {person_name}'s birthday.\nDate: {date}",
    "🎉 {person_name}'s birthday is in {days_until} days.\nDate: {date}",
    "⌛ T-minus {days_until} days until {person_name} Day.\nDate: {date}",
    "🗓️ In {days_until} days, it's {person_name}'s big day.\nDate: {date}",
    "🎈 {days_until} days until cake for {person_name}.\nDate: {date}",
    "⏳ {days_until}-day countdown active for {person_name}'s birthday.\nDate: {date}",
    "📅 {person_name}'s birthday arrives in {days_until} days.\nDate: {date}",
    "🎊 Only {days_until} days until {person_name} takes over the calendar.\nDate: {date}",
    "🚀 Launch scheduled in {days_until} days: {person_name}'s birthday.\nDate: {date}",
    "🌟 {days_until} days until {person_name}'s annual spotlight.\nDate: {date}",
    "🧁 {days_until} days left to prepare for {person_name}'s birthday.\nDate: {date}",
    "📢 Announcement: {person_name}'s birthday is {days_until} days away.\nDate: {date}",
)

TODAY_AGE_TEMPLATES = (
    "🎉 It's {person_name}'s birthday (turning {age})!\nDate: {date}",
    "🎈 {person_name} officially turns {age} today.\nDate: {date}",
    "🚨 {person_name} levels up to {age} today.\nDate: {date}",
    "🎂 {person_name} hits {age} today.\nDate: {date}",
    "🥳 Today marks {age} years of {person_name}.\nDate: {date}",
    "🌟 {person_name} unlocks level {age} today.\nDate: {date}",
    "🎊 {age} looks good on {person_name}.\nDate: {date}",
)

TOMORROW_AGE_TEMPLATES = (
    "⏳ {person_name} turns {age} tomorrow.\nDate: {date}",
    "🎉 {age} begins tomorrow for {person_name}.\nDate: {date}",
    "🎈 {person_name} levels up to {age} tomorrow.\nDate: {date}",
    "🗓️ Tomorrow: {person_name} hits {age}.\nDate: {date}",
    "🚀 In 24 hours, {person_name} turns {age}.\nDate: {date}",
)

IN_DAYS_AGE_TEMPLATES = (
    "📆 In {days_until} days, {person_name} turns {age}.\nDate: {date}",
    "🎉 {days_until} days until {person_name} hits {age}.\nDate: {date}",
    "⌛ {days_until} days until level {age} for {person_name}.\nDate: {date}",
    "🎈 {days_until} days until {person_name} celebrates {age}.\nDate: {date}",
    "🌟 {person_name} reaches {age} in {days_until} days.\nDate: {date}",
)


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
        has_age = reminder.turning_age is not None
        if reminder.days_until == 0:
            templates = TODAY_AGE_TEMPLATES if has_age else TODAY_TEMPLATES
            variant_group = "today-age" if has_age else "today"
        elif reminder.days_until == 1:
            templates = TOMORROW_AGE_TEMPLATES if has_age else TOMORROW_TEMPLATES
            variant_group = "tomorrow-age" if has_age else "tomorrow"
        else:
            templates = IN_DAYS_AGE_TEMPLATES if has_age else IN_DAYS_TEMPLATES
            variant_group = "in-days-age" if has_age else "in-days"

        template = ReminderService._select_rotating_template(reminder, templates, variant_group)
        return template.format(
            person_name=reminder.person_name,
            age=reminder.turning_age,
            days_until=reminder.days_until,
            date=reminder.next_birthday_date.isoformat(),
        )

    @staticmethod
    def _select_rotating_template(reminder: DueReminder, templates: tuple[str, ...], variant_group: str) -> str:
        seed = "|".join(
            (
                reminder.person_id,
                reminder.next_birthday_date.isoformat(),
                str(reminder.days_until),
                variant_group,
            )
        )
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % len(templates)
        return templates[index]


def parse_time_string(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def now_in_timezone(timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    return datetime.now(tz)
