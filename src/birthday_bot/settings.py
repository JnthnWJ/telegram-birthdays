from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_allowed_user_id: int
    telegram_allowed_chat_id: int
    birthday_config_path: Path
    person_index_path: Path
    reminder_state_path: Path


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {name}")
    return value.strip()


def load_settings() -> Settings:
    root = Path.cwd()

    token = _required_env("TELEGRAM_BOT_TOKEN")
    allowed_user_id = int(_required_env("TELEGRAM_ALLOWED_USER_ID"))
    allowed_chat_id = int(_required_env("TELEGRAM_ALLOWED_CHAT_ID"))

    birthday_config_path = Path(
        os.getenv("BIRTHDAY_CONFIG_PATH", root / "config" / "birthdays.toml")
    )
    person_index_path = Path(
        os.getenv("PERSON_INDEX_PATH", root / "data" / "person_index.json")
    )
    reminder_state_path = Path(
        os.getenv("REMINDER_STATE_PATH", root / "data" / "reminder_state.json")
    )

    return Settings(
        telegram_bot_token=token,
        telegram_allowed_user_id=allowed_user_id,
        telegram_allowed_chat_id=allowed_chat_id,
        birthday_config_path=birthday_config_path,
        person_index_path=person_index_path,
        reminder_state_path=reminder_state_path,
    )
