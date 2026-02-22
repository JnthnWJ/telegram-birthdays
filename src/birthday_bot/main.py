from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram.ext import Application, CallbackContext

from birthday_bot.bot_handlers import HandlerDependencies, build_handlers
from birthday_bot.config_store import ensure_default_config, load_config
from birthday_bot.reminder_service import ReminderService, parse_time_string
from birthday_bot.settings import load_settings


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


async def scheduled_reminder_callback(context: CallbackContext) -> None:
    service: ReminderService = context.application.bot_data["reminder_service"]
    config = load_config(context.application.bot_data["settings"].birthday_config_path)
    now = datetime.now(ZoneInfo(config.timezone)).date()
    await service.dispatch_for_date(now)


async def startup_catchup(application: Application) -> None:
    settings = application.bot_data["settings"]
    config = load_config(settings.birthday_config_path)
    now = datetime.now(ZoneInfo(config.timezone))

    hour, minute = parse_time_string(config.daily_send_time)
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= scheduled:
        service: ReminderService = application.bot_data["reminder_service"]
        await service.dispatch_for_date(now.date())


def main() -> None:
    configure_logging()

    settings = load_settings()
    _ensure_parent(settings.birthday_config_path)
    _ensure_parent(settings.person_index_path)
    _ensure_parent(settings.reminder_state_path)

    ensure_default_config(settings.birthday_config_path)
    config = load_config(settings.birthday_config_path)

    tz = ZoneInfo(config.timezone)
    hour, minute = parse_time_string(config.daily_send_time)

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["handler_deps"] = HandlerDependencies(settings=settings)

    reminder_service = ReminderService(
        bot=application.bot,
        chat_id=settings.telegram_allowed_chat_id,
        config_path=settings.birthday_config_path,
        person_index_path=settings.person_index_path,
        reminder_state_path=settings.reminder_state_path,
    )
    application.bot_data["reminder_service"] = reminder_service

    for handler in build_handlers(settings):
        application.add_handler(handler)

    application.job_queue.run_daily(
        scheduled_reminder_callback,
        time=time(hour=hour, minute=minute, tzinfo=tz),
        name="daily-birthday-reminders",
    )

    application.post_init = startup_catchup
    application.run_polling()


if __name__ == "__main__":
    main()
