# Telegram Birthday Reminder Bot

A Python Telegram bot that tracks birthdays in TOML, supports interactive adds via chat, and sends reminder messages using long polling.

## Features

- Human-editable TOML config for bulk birthday management
- `/add` wizard to add birthdays from Telegram chat
- `/edit` wizard to update existing birthdays from Telegram chat
- `/list` to show birthdays and days until each
- `/help` for command reference
- `/cancel` to abort wizard
- Daily reminders at fixed local time in configured timezone
- App-managed identity index (`person_index.json`) so TOML never needs IDs
- Reminder dedupe state (`reminder_state.json`) to avoid duplicate sends on restart

## Configuration

Main file: `config/birthdays.toml`

```toml
timezone = "America/Los_Angeles"
daily_send_time = "09:00"
leap_day_rule = "feb28"

# Reminder: if /add wizard offsets are left blank, default offsets are [30, 7, 1, 0].

[[birthdays]]
name = "Alice"
month = 3
day = 14
year = 1990
reminder_offsets = [30, 7, 1, 0]
```

Data files:

- `data/person_index.json`: app-managed internal UUID mapping
- `data/reminder_state.json`: app-managed reminder dedupe keys

## Environment Variables

Required:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_ID`
- `TELEGRAM_ALLOWED_CHAT_ID`

Optional:

- `BIRTHDAY_CONFIG_PATH`
- `PERSON_INDEX_PATH`
- `REMINDER_STATE_PATH`

## Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
cp config/birthdays.toml.example config/birthdays.toml
set -a; source .env; set +a
python -m birthday_bot.main
```

## Commands

- `/add` interactive wizard for creating birthday entries
- `/edit` interactive wizard for updating existing entries
- `/list` list tracked birthdays with days remaining
- `/help` list commands and input formats
- `/cancel` stop active wizard

## Oracle Server Deployment (systemd)

1. Copy project to `/opt/telegram-birthdays`.
2. Create virtualenv and install:
   - `python3 -m venv .venv`
   - `.venv/bin/pip install -e .`
3. Create `.env` and `config/birthdays.toml`.
4. Copy `deploy/birthday-bot.service` to `/etc/systemd/system/birthday-bot.service`.
5. Enable and start:
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable birthday-bot`
   - `sudo systemctl start birthday-bot`
6. Tail logs:
   - `sudo journalctl -u birthday-bot -f`

## Notes

- Duplicate names are allowed.
- Identity is derived from normalized `name + month + day + year` and row occurrence order within each duplicate bucket.
- If two entries share the same bucket, TOML row order controls deterministic ID assignment.
- Feb 29 birthdays are treated as Feb 28 on non-leap years when `leap_day_rule = "feb28"`.
