from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass
class ReminderState:
    sent_keys: set[str]
    last_pruned: str | None = None


def load_state(path: Path) -> ReminderState:
    if not path.exists():
        return ReminderState(sent_keys=set(), last_pruned=None)

    with path.open("r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)

    sent_keys = {str(value) for value in data.get("sent_keys", [])}
    last_pruned = data.get("last_pruned")
    return ReminderState(sent_keys=sent_keys, last_pruned=str(last_pruned) if last_pruned else None)


def save_state_atomic(path: Path, state: ReminderState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sent_keys": sorted(state.sent_keys),
        "last_pruned": state.last_pruned,
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temp_file:
        json.dump(payload, temp_file, indent=2)
        temp_file.write("\n")
        temp_name = temp_file.name

    os.replace(temp_name, path)


def dedupe_key(send_date: date, person_id: str, offset_days: int) -> str:
    return f"{send_date.isoformat()}|{person_id}|{offset_days}"


def prune_old_keys(state: ReminderState, today: date, *, retention_days: int = 400) -> None:
    cutoff = today - timedelta(days=retention_days)
    retained: set[str] = set()

    for key in state.sent_keys:
        parts = key.split("|")
        if len(parts) != 3:
            continue
        send_date_str = parts[0]
        try:
            send_date = date.fromisoformat(send_date_str)
        except ValueError:
            continue

        if send_date >= cutoff:
            retained.add(key)

    state.sent_keys = retained
    state.last_pruned = today.isoformat()
