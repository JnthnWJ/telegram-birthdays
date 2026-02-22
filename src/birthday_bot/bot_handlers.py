from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    CallbackContext,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from birthday_bot.config_store import append_birthday, load_config, update_birthday
from birthday_bot.date_logic import days_until_birthday, next_birthday, turning_age, validate_month_day
from birthday_bot.identity_index import assign_and_persist_ids
from birthday_bot.models import BirthdayEntry, DEFAULT_REMINDER_OFFSETS
from birthday_bot.settings import Settings

LOGGER = logging.getLogger(__name__)

(
    STATE_ADD_NAME,
    STATE_ADD_BIRTHDAY,
    STATE_ADD_OFFSETS,
    STATE_ADD_CONFIRM,
    STATE_EDIT_SELECT,
    STATE_EDIT_NAME,
    STATE_EDIT_BIRTHDAY,
    STATE_EDIT_OFFSETS,
    STATE_EDIT_CONFIRM,
) = range(9)

PENDING_ADD_KEY = "pending_add_birthday"
PENDING_EDIT_KEY = "pending_edit_birthday"


@dataclass(frozen=True)
class HandlerDependencies:
    settings: Settings


@dataclass(frozen=True)
class BirthdayListRow:
    name: str
    days_until: int
    next_date: date
    turning_age: int | None
    reminder_offsets: tuple[int, ...]


def is_authorized(update: Update, settings: Settings) -> bool:
    effective_user = update.effective_user
    effective_chat = update.effective_chat
    if effective_user is None or effective_chat is None:
        return False
    return (
        effective_user.id == settings.telegram_allowed_user_id
        and effective_chat.id == settings.telegram_allowed_chat_id
    )


async def _deny_unauthorized(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("This bot is restricted to its configured owner.")


def parse_birthday_text(raw_text: str) -> tuple[int, int, int | None]:
    value = raw_text.strip()

    full_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    if full_match:
        year = int(full_match.group(1))
        month = int(full_match.group(2))
        day = int(full_match.group(3))
        date(year, month, day)
        return month, day, year

    short_match = re.fullmatch(r"(\d{2})-(\d{2})", value)
    if short_match:
        month = int(short_match.group(1))
        day = int(short_match.group(2))
        validate_month_day(month, day, allow_feb_29=True)
        return month, day, None

    raise ValueError("Birthday must use YYYY-MM-DD or MM-DD")


def parse_offsets_text(raw_text: str) -> tuple[list[int], bool]:
    text = raw_text.strip()
    if not text or text.lower() in {"skip", "default"}:
        return list(DEFAULT_REMINDER_OFFSETS), True

    values: list[int] = []
    for token in text.split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        if not cleaned.isdigit():
            raise ValueError("Offsets must be comma-separated non-negative integers")
        values.append(int(cleaned))

    if not values:
        raise ValueError("Provide at least one offset or leave blank for default")

    unique_sorted = sorted(set(values), reverse=True)
    return unique_sorted, False


def _render_help() -> str:
    return (
        "Commands:\n"
        "/add - Start the interactive birthday wizard\n"
        "/edit - Interactively edit an existing birthday\n"
        "/list - Show tracked birthdays and days until each\n"
        "/help - Show this help message\n"
        "/cancel - Cancel the active add/edit wizard\n\n"
        "Birthday format examples:\n"
        "- 1990-03-14\n"
        "- 03-14\n\n"
        "Reminder offsets example: 30,7,1,0 (or send skip/default)"
    )


def _format_reminder_offsets(offsets: tuple[int, ...]) -> str:
    labels: list[str] = []
    for offset in offsets:
        if offset == 0:
            labels.append("day-of")
        else:
            labels.append(f"{offset}d")
    return ", ".join(labels)


def _render_list_message(rows: list[BirthdayListRow]) -> str:
    lines = [f"Tracked birthdays ({len(rows)})", "Sorted by soonest:"]

    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. {row.name}")
        details = [
            f"In {row.days_until}d",
            f"Next {row.next_date.isoformat()}",
        ]
        if row.turning_age is not None:
            details.append(f"Turning {row.turning_age}")
        details.append(f"Reminders {_format_reminder_offsets(row.reminder_offsets)}")
        lines.append(f"   {' | '.join(details)}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _format_birthday(month: int, day: int, year: int | None) -> str:
    if year is None:
        return f"{month:02d}-{day:02d}"
    return f"{year:04d}-{month:02d}-{day:02d}"


def _is_skip(value: str) -> bool:
    return value.strip().lower() in {"skip", "keep", "same"}


def _render_edit_selection(entries: list[BirthdayEntry]) -> str:
    lines = [
        "Edit birthday wizard started.",
        "Step 1/5: Reply with the number of the entry to edit:",
    ]
    for index, entry in enumerate(entries, start=1):
        lines.append(
            f"{index}. {entry.name} | {_format_birthday(entry.month, entry.day, entry.year)}"
            f" | Reminders {_format_reminder_offsets(tuple(entry.reminder_offsets))}"
        )
    return "\n".join(lines)


def _render_edit_summary(pending: dict[str, Any]) -> str:
    original_birthday = _format_birthday(
        int(pending["original_month"]),
        int(pending["original_day"]),
        int(pending["original_year"]) if pending["original_year"] is not None else None,
    )
    updated_birthday = _format_birthday(
        int(pending["month"]),
        int(pending["day"]),
        int(pending["year"]) if pending["year"] is not None else None,
    )
    original_offsets = tuple(int(v) for v in pending["original_offsets"])
    updated_offsets = tuple(int(v) for v in pending["offsets"])
    default_note = " (default)" if bool(pending.get("used_default_offsets")) else ""

    return (
        "Step 5/5: Confirm these edits:\n"
        f"Name: {pending['original_name']} -> {pending['name']}\n"
        f"Birthday: {original_birthday} -> {updated_birthday}\n"
        f"Offsets: {list(original_offsets)} -> {list(updated_offsets)}{default_note}\n\n"
        "Reply with yes to save, or no to cancel."
    )


async def help_command(update: Update, context: CallbackContext) -> None:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    if not is_authorized(update, deps.settings):
        await _deny_unauthorized(update)
        return
    await update.effective_message.reply_text(_render_help())


async def list_command(update: Update, context: CallbackContext) -> None:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    settings = deps.settings
    if not is_authorized(update, settings):
        await _deny_unauthorized(update)
        return

    config = load_config(settings.birthday_config_path)
    if not config.birthdays:
        await update.effective_message.reply_text("No birthdays are currently tracked.")
        return

    person_ids = assign_and_persist_ids(settings.person_index_path, config.birthdays)
    now = datetime.now(ZoneInfo(config.timezone)).date()

    rows: list[BirthdayListRow] = []
    for entry, _person_id in zip(config.birthdays, person_ids, strict=True):
        days_until = days_until_birthday(entry, now, config.leap_day_rule)
        next_date = next_birthday(entry, now, config.leap_day_rule)
        age = turning_age(entry, next_date)
        rows.append(
            BirthdayListRow(
                name=entry.name,
                days_until=days_until,
                next_date=next_date,
                turning_age=age,
                reminder_offsets=tuple(entry.reminder_offsets),
            )
        )

    rows.sort(key=lambda row: (row.days_until, row.name.lower()))
    message = _render_list_message(rows)
    await update.effective_message.reply_text(message)


async def add_start(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    if not is_authorized(update, deps.settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    context.user_data[PENDING_ADD_KEY] = {}
    await update.effective_message.reply_text(
        "Add birthday wizard started.\nStep 1/4: Send the person's name."
    )
    return STATE_ADD_NAME


async def add_name(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    if not is_authorized(update, deps.settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    name = (update.effective_message.text or "").strip()
    if not name:
        await update.effective_message.reply_text("Name cannot be empty. Please send a name.")
        return STATE_ADD_NAME

    context.user_data[PENDING_ADD_KEY] = {"name": name}
    await update.effective_message.reply_text(
        "Step 2/4: Send birthday as YYYY-MM-DD or MM-DD."
    )
    return STATE_ADD_BIRTHDAY


async def add_birthday(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    if not is_authorized(update, deps.settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    raw_text = update.effective_message.text or ""

    try:
        month, day, year = parse_birthday_text(raw_text)
    except ValueError as exc:
        await update.effective_message.reply_text(
            f"{exc}. Please send YYYY-MM-DD or MM-DD."
        )
        return STATE_ADD_BIRTHDAY

    pending = context.user_data.get(PENDING_ADD_KEY, {})
    pending.update({"month": month, "day": day, "year": year})
    context.user_data[PENDING_ADD_KEY] = pending

    await update.effective_message.reply_text(
        "Step 3/4: Send reminder offsets in days (e.g., 30,7,1,0).\n"
        "Send skip/default for [30,7,1,0]."
    )
    return STATE_ADD_OFFSETS


async def add_offsets(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    if not is_authorized(update, deps.settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    raw_text = update.effective_message.text or ""
    try:
        offsets, used_default = parse_offsets_text(raw_text)
    except ValueError as exc:
        await update.effective_message.reply_text(
            f"{exc}. Provide comma-separated values like 30,7,1,0 or leave blank."
        )
        return STATE_ADD_OFFSETS

    pending = context.user_data.get(PENDING_ADD_KEY, {})
    pending["offsets"] = offsets
    pending["used_default_offsets"] = used_default
    context.user_data[PENDING_ADD_KEY] = pending

    year = pending.get("year")
    year_text = str(year) if year is not None else "(not set)"
    default_note = " (default)" if used_default else ""
    summary = (
        "Step 4/4: Confirm this entry:\n"
        f"Name: {pending.get('name')}\n"
        f"Birthday: {pending.get('month'):02d}-{pending.get('day'):02d}\n"
        f"Year: {year_text}\n"
        f"Offsets: {offsets}{default_note}\n\n"
        "Reply with yes to save, or no to cancel."
    )
    await update.effective_message.reply_text(summary)
    return STATE_ADD_CONFIRM


async def add_confirm(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    settings = deps.settings
    if not is_authorized(update, settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    decision = (update.effective_message.text or "").strip().lower()
    if decision not in {"yes", "y", "no", "n"}:
        await update.effective_message.reply_text("Please reply with yes or no.")
        return STATE_ADD_CONFIRM

    if decision in {"no", "n"}:
        context.user_data.pop(PENDING_ADD_KEY, None)
        await update.effective_message.reply_text("Canceled. No changes were made.")
        return ConversationHandler.END

    pending = context.user_data.get(PENDING_ADD_KEY, {})
    entry = BirthdayEntry(
        name=str(pending["name"]),
        month=int(pending["month"]),
        day=int(pending["day"]),
        year=int(pending["year"]) if pending.get("year") is not None else None,
        reminder_offsets=[int(v) for v in pending["offsets"]],
    )
    append_birthday(settings.birthday_config_path, entry)
    context.user_data.pop(PENDING_ADD_KEY, None)

    await update.effective_message.reply_text("Birthday saved to config.")
    LOGGER.info("Added birthday for %s", entry.name)
    return ConversationHandler.END


async def edit_start(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    settings = deps.settings
    if not is_authorized(update, settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    config = load_config(settings.birthday_config_path)
    if not config.birthdays:
        await update.effective_message.reply_text("No birthdays are currently tracked.")
        return ConversationHandler.END

    context.user_data[PENDING_EDIT_KEY] = {}
    await update.effective_message.reply_text(_render_edit_selection(config.birthdays))
    return STATE_EDIT_SELECT


async def edit_select(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    settings = deps.settings
    if not is_authorized(update, settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    raw_text = (update.effective_message.text or "").strip()
    if not raw_text.isdigit():
        await update.effective_message.reply_text("Please send the entry number shown in the list.")
        return STATE_EDIT_SELECT

    selected = int(raw_text)
    config = load_config(settings.birthday_config_path)
    if selected < 1 or selected > len(config.birthdays):
        await update.effective_message.reply_text(
            f"Entry must be between 1 and {len(config.birthdays)}."
        )
        return STATE_EDIT_SELECT

    entry = config.birthdays[selected - 1]
    pending: dict[str, Any] = {
        "index": selected - 1,
        "original_name": entry.name,
        "original_month": entry.month,
        "original_day": entry.day,
        "original_year": entry.year,
        "original_offsets": list(entry.reminder_offsets),
        "name": entry.name,
        "month": entry.month,
        "day": entry.day,
        "year": entry.year,
        "offsets": list(entry.reminder_offsets),
        "used_default_offsets": False,
    }
    context.user_data[PENDING_EDIT_KEY] = pending

    await update.effective_message.reply_text(
        f"Step 2/5: Send a new name, or skip to keep \"{entry.name}\"."
    )
    return STATE_EDIT_NAME


async def edit_name(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    settings = deps.settings
    if not is_authorized(update, settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    pending = context.user_data.get(PENDING_EDIT_KEY)
    if not isinstance(pending, dict) or "index" not in pending:
        await update.effective_message.reply_text("Edit session expired. Send /edit to start again.")
        return ConversationHandler.END

    raw_text = (update.effective_message.text or "").strip()
    if not _is_skip(raw_text):
        if not raw_text:
            await update.effective_message.reply_text("Name cannot be empty. Send a name or skip.")
            return STATE_EDIT_NAME
        pending["name"] = raw_text

    current_birthday = _format_birthday(
        int(pending["month"]),
        int(pending["day"]),
        int(pending["year"]) if pending["year"] is not None else None,
    )
    context.user_data[PENDING_EDIT_KEY] = pending
    await update.effective_message.reply_text(
        "Step 3/5: Send a new birthday as YYYY-MM-DD or MM-DD,\n"
        f"or skip to keep {current_birthday}."
    )
    return STATE_EDIT_BIRTHDAY


async def edit_birthday(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    settings = deps.settings
    if not is_authorized(update, settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    pending = context.user_data.get(PENDING_EDIT_KEY)
    if not isinstance(pending, dict) or "index" not in pending:
        await update.effective_message.reply_text("Edit session expired. Send /edit to start again.")
        return ConversationHandler.END

    raw_text = (update.effective_message.text or "").strip()
    if not _is_skip(raw_text):
        try:
            month, day, year = parse_birthday_text(raw_text)
        except ValueError as exc:
            await update.effective_message.reply_text(
                f"{exc}. Please send YYYY-MM-DD or MM-DD, or skip."
            )
            return STATE_EDIT_BIRTHDAY
        pending["month"] = month
        pending["day"] = day
        pending["year"] = year

    current_offsets = _format_reminder_offsets(tuple(int(v) for v in pending["offsets"]))
    context.user_data[PENDING_EDIT_KEY] = pending
    await update.effective_message.reply_text(
        "Step 4/5: Send new reminder offsets in days (e.g., 30,7,1,0).\n"
        f"Send skip to keep {current_offsets}, or default for [30,7,1,0]."
    )
    return STATE_EDIT_OFFSETS


async def edit_offsets(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    settings = deps.settings
    if not is_authorized(update, settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    pending = context.user_data.get(PENDING_EDIT_KEY)
    if not isinstance(pending, dict) or "index" not in pending:
        await update.effective_message.reply_text("Edit session expired. Send /edit to start again.")
        return ConversationHandler.END

    raw_text = (update.effective_message.text or "").strip()
    if _is_skip(raw_text):
        pending["used_default_offsets"] = False
    else:
        try:
            offsets, used_default = parse_offsets_text(raw_text)
        except ValueError as exc:
            await update.effective_message.reply_text(
                f"{exc}. Provide comma-separated values like 30,7,1,0, send default, or skip."
            )
            return STATE_EDIT_OFFSETS
        pending["offsets"] = offsets
        pending["used_default_offsets"] = used_default

    context.user_data[PENDING_EDIT_KEY] = pending
    await update.effective_message.reply_text(_render_edit_summary(pending))
    return STATE_EDIT_CONFIRM


async def edit_confirm(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    settings = deps.settings
    if not is_authorized(update, settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    pending = context.user_data.get(PENDING_EDIT_KEY)
    if not isinstance(pending, dict) or "index" not in pending:
        await update.effective_message.reply_text("Edit session expired. Send /edit to start again.")
        return ConversationHandler.END

    decision = (update.effective_message.text or "").strip().lower()
    if decision not in {"yes", "y", "no", "n"}:
        await update.effective_message.reply_text("Please reply with yes or no.")
        return STATE_EDIT_CONFIRM

    if decision in {"no", "n"}:
        context.user_data.pop(PENDING_EDIT_KEY, None)
        await update.effective_message.reply_text("Canceled. No changes were made.")
        return ConversationHandler.END

    entry = BirthdayEntry(
        name=str(pending["name"]),
        month=int(pending["month"]),
        day=int(pending["day"]),
        year=int(pending["year"]) if pending.get("year") is not None else None,
        reminder_offsets=[int(v) for v in pending["offsets"]],
    )

    try:
        update_birthday(
            settings.birthday_config_path,
            index=int(pending["index"]),
            updated_birthday=entry,
        )
    except IndexError:
        context.user_data.pop(PENDING_EDIT_KEY, None)
        await update.effective_message.reply_text(
            "Could not save because the birthday list changed. Send /edit and try again."
        )
        return ConversationHandler.END

    context.user_data.pop(PENDING_EDIT_KEY, None)
    await update.effective_message.reply_text("Birthday updated.")
    LOGGER.info("Updated birthday for %s", entry.name)
    return ConversationHandler.END


async def cancel_command(update: Update, context: CallbackContext) -> int:
    deps: HandlerDependencies = context.application.bot_data["handler_deps"]
    if not is_authorized(update, deps.settings):
        await _deny_unauthorized(update)
        return ConversationHandler.END

    context.user_data.pop(PENDING_ADD_KEY, None)
    context.user_data.pop(PENDING_EDIT_KEY, None)
    await update.effective_message.reply_text("Wizard canceled.")
    return ConversationHandler.END


def build_handlers(settings: Settings) -> list:
    add_conversation = ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            STATE_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            STATE_ADD_BIRTHDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_birthday)],
            STATE_ADD_OFFSETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_offsets)],
            STATE_ADD_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="add_birthday_conversation",
        persistent=False,
    )

    edit_conversation = ConversationHandler(
        entry_points=[CommandHandler("edit", edit_start)],
        states={
            STATE_EDIT_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_select)],
            STATE_EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name)],
            STATE_EDIT_BIRTHDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_birthday)],
            STATE_EDIT_OFFSETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_offsets)],
            STATE_EDIT_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="edit_birthday_conversation",
        persistent=False,
    )

    return [
        CommandHandler("help", help_command),
        CommandHandler("list", list_command),
        CommandHandler("cancel", cancel_command),
        add_conversation,
        edit_conversation,
    ]
