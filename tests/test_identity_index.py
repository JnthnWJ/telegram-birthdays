from birthday_bot.identity_index import resolve_ids
from birthday_bot.models import BirthdayEntry


def test_resolve_ids_reuses_existing_and_extends() -> None:
    entries = [
        BirthdayEntry(name="Alice", month=3, day=14, year=1990, reminder_offsets=[7]),
        BirthdayEntry(name="Alice", month=3, day=14, year=1990, reminder_offsets=[1]),
        BirthdayEntry(name="Bob", month=5, day=1, year=None, reminder_offsets=[0]),
    ]
    existing = {
        "alice|03|14|1990": ["id-a-1"],
        "bob|05|01|none": ["id-b-1"],
    }

    resolution = resolve_ids(entries, existing)

    assert resolution.person_ids[0] == "id-a-1"
    assert resolution.person_ids[1] != "id-a-1"
    assert resolution.person_ids[2] == "id-b-1"
    assert len(resolution.buckets["alice|03|14|1990"]) == 2
