"""Tests for JSON persistence and validation."""

from pathlib import Path

import pytest

from pawpal_store import (
    TaskOverlapError,
    TaskValidationError,
    load_owner,
    owner_from_dict,
    save_owner,
    try_add_task,
)
from pawpal_system import Owner, Pet, Task


def test_roundtrip_owner_json(tmp_path: Path) -> None:
    store = tmp_path / "db.json"
    owner = Owner("Alex")
    p = Pet("Mochi", "dog")
    owner.add_pet(p)
    t = Task("Walk", 25, "daily", start_time="08:00", task_id="id-1")
    p.add_task(t)

    save_owner(owner, store)
    loaded = load_owner(store)
    assert loaded is not None
    assert loaded.name == "Alex"
    assert len(loaded.pets) == 1
    assert loaded.pets[0].name == "Mochi"
    assert len(loaded.pets[0].tasks) == 1
    lt = loaded.pets[0].tasks[0]
    assert lt.task_id == "id-1"
    assert lt.description == "Walk"
    assert lt.start_time == "08:00"
    assert lt.time_minutes == 25


def test_try_add_task_rejects_overlap(tmp_path: Path) -> None:
    store = tmp_path / "db.json"
    owner = Owner("O")
    pet = Pet("P", "dog")
    owner.add_pet(pet)
    pet.add_task(Task("a", 60, "daily", start_time="09:00"))
    save_owner(owner, store)
    owner2 = load_owner(store)
    assert owner2 is not None
    pet2 = owner2.pets[0]
    with pytest.raises(TaskOverlapError):
        try_add_task(owner2, pet2, Task("b", 30, "daily", start_time="09:30"))


def test_try_add_task_rejects_empty_description(tmp_path: Path) -> None:
    owner = Owner("O")
    pet = Pet("P", "dog")
    owner.add_pet(pet)
    with pytest.raises(TaskValidationError):
        try_add_task(owner, pet, Task("   ", 10, "daily", start_time="10:00"))


def test_owner_from_dict_rejects_bad_schema() -> None:
    with pytest.raises(ValueError):
        owner_from_dict({"schema_version": 999, "owner": {"name": "x", "pets": []}})
