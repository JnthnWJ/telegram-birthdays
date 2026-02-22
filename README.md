# Telegram Birthday Reminder Bot

A self-hosted Telegram bot that tracks birthdays, supports chat-based updates, and sends scheduled reminders.

## Features

- Human-editable TOML config for bulk birthday management
- `/add` wizard to add birthdays from Telegram chat
- `/edit` wizard to update existing birthdays from Telegram chat
- `/list` to show birthdays and days until each
- `/help` for command reference
- `/cancel` to abort the active wizard
- Daily reminders at a fixed local time in your configured timezone
- App-managed identity index (`person_index.json`) so TOML never needs IDs
- Reminder dedupe state (`reminder_state.json`) to avoid duplicate sends on restart

## Requirements

- Python 3.11+
- A Telegram bot token
- Your Telegram user ID and chat ID (used to restrict bot access)

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

cp .env.example .env
cp config/birthdays.toml.example config/birthdays.toml

set -a; source .env; set +a
python -m birthday_bot.main
```

You can also run via the installed entry point:

```bash
birthday-bot
```

## Environment Variables

Required:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_ID`
- `TELEGRAM_ALLOWED_CHAT_ID`

Optional (defaults shown):

- `BIRTHDAY_CONFIG_PATH` (default: `config/birthdays.toml`)
- `PERSON_INDEX_PATH` (default: `data/person_index.json`)
- `REMINDER_STATE_PATH` (default: `data/reminder_state.json`)

## Birthday Config Format

Main file: `config/birthdays.toml`

```toml
timezone = "America/Los_Angeles"
daily_send_time = "09:00"
leap_day_rule = "feb28"

# If /add reminder offsets are left blank, defaults are [30, 7, 1, 0].

[[birthdays]]
name = "Alice"
month = 3
day = 14
year = 1990
reminder_offsets = [30, 7, 1, 0]
```

App-managed data files:

- `data/person_index.json`: internal UUID mapping
- `data/reminder_state.json`: reminder dedupe keys

## Bot Commands

- `/add`: interactive wizard for creating birthday entries
- `/edit`: interactive wizard for updating existing entries
- `/list`: list tracked birthdays with days remaining
- `/help`: list commands and input formats
- `/cancel`: stop active wizard

## Optional: Run as a Linux Service (systemd)

If you want the bot to run continuously in the background:

1. Place this project on the server (for example, `/opt/telegram-birthdays`).
2. Create a virtual environment and install dependencies.
3. Create `.env` and `config/birthdays.toml`.
4. Copy `deploy/birthday-bot.service` to `/etc/systemd/system/birthday-bot.service`.
5. Update `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` in the service file to match your paths.
6. Enable and start the service.

Useful commands:

```bash
sudo systemctl daemon-reload
sudo systemctl enable birthday-bot
sudo systemctl start birthday-bot
sudo systemctl status birthday-bot
sudo journalctl -u birthday-bot -f
```

## Notes

- Duplicate names are allowed.
- Identity is derived from normalized `name + month + day + year` and row occurrence order within each duplicate bucket.
- If two entries share the same bucket, TOML row order controls deterministic ID assignment.
- Feb 29 birthdays are treated as Feb 28 on non-leap years when `leap_day_rule = "feb28"`.
