from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from birthday_bot.models import BirthdayEntry


@dataclass(frozen=True)
class IdentityResolution:
    person_ids: list[str]
    buckets: dict[str, list[str]]


def normalize_name(name: str) -> str:
    pieces = name.strip().lower().split()
    return " ".join(pieces)


def bucket_key(entry: BirthdayEntry) -> str:
    year = str(entry.year) if entry.year is not None else "none"
    return f"{normalize_name(entry.name)}|{entry.month:02d}|{entry.day:02d}|{year}"


def load_index(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)

    buckets = data.get("buckets", {})
    if not isinstance(buckets, dict):
        return {}

    cleaned: dict[str, list[str]] = {}
    for key, values in buckets.items():
        if isinstance(key, str) and isinstance(values, list):
            cleaned[key] = [str(value) for value in values]
    return cleaned


def save_index_atomic(path: Path, buckets: dict[str, list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "buckets": buckets}

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temp_file:
        json.dump(payload, temp_file, indent=2, sort_keys=True)
        temp_file.write("\n")
        temp_name = temp_file.name

    os.replace(temp_name, path)


def resolve_ids(entries: list[BirthdayEntry], existing_buckets: dict[str, list[str]]) -> IdentityResolution:
    bucket_occurrence_counts: dict[str, int] = {}
    resolved_ids: list[str] = []
    new_buckets: dict[str, list[str]] = {}

    for entry in entries:
        key = bucket_key(entry)
        occurrence_idx = bucket_occurrence_counts.get(key, 0)
        bucket_occurrence_counts[key] = occurrence_idx + 1

        existing_ids = existing_buckets.get(key, [])
        if occurrence_idx < len(existing_ids):
            person_id = existing_ids[occurrence_idx]
        else:
            person_id = str(uuid.uuid4())

        new_buckets.setdefault(key, []).append(person_id)
        resolved_ids.append(person_id)

    return IdentityResolution(person_ids=resolved_ids, buckets=new_buckets)


def assign_and_persist_ids(path: Path, entries: list[BirthdayEntry]) -> list[str]:
    existing = load_index(path)
    resolution = resolve_ids(entries, existing)
    save_index_atomic(path, resolution.buckets)
    return resolution.person_ids
