"""Tests for AI proposed schedule validation."""

from pawpal_system import Owner, Pet, Task, validate_proposed_schedule


def _owner_with_two_tasks() -> Owner:
    owner = Owner("Alex")
    pet = Pet("Mochi", "dog")
    pet.add_task(Task("Walk", 30, "daily", start_time=None, task_id="t1"))
    pet.add_task(Task("Feed", 20, "daily", start_time=None, task_id="t2"))
    owner.add_pet(pet)
    return owner


def test_validate_proposed_schedule_passes_for_non_overlapping_rows() -> None:
    owner = _owner_with_two_tasks()
    rows = [
        {"task_id": "t1", "start_time": "08:00", "order": 1, "reason": "Morning walk", "cited_ids": []},
        {"task_id": "t2", "start_time": "09:00", "order": 2, "reason": "Breakfast", "cited_ids": []},
    ]
    out = validate_proposed_schedule(owner, rows)
    assert [r["task_id"] for r in out] == ["t1", "t2"]


def test_validate_proposed_schedule_rejects_overlaps() -> None:
    owner = _owner_with_two_tasks()
    rows = [
        {"task_id": "t1", "start_time": "08:00", "order": 1, "reason": "Morning walk", "cited_ids": []},
        {"task_id": "t2", "start_time": "08:10", "order": 2, "reason": "Breakfast", "cited_ids": []},
    ]
    try:
        validate_proposed_schedule(owner, rows)
        assert False, "Expected ValueError for overlapping windows"
    except ValueError as exc:
        assert "Overlapping proposal windows" in str(exc)


def test_validate_proposed_schedule_rejects_duplicate_task_ids() -> None:
    owner = _owner_with_two_tasks()
    rows = [
        {"task_id": "t1", "start_time": "08:00", "order": 1, "reason": "Morning walk", "cited_ids": []},
        {"task_id": "t1", "start_time": "09:00", "order": 2, "reason": "Duplicate", "cited_ids": []},
    ]
    try:
        validate_proposed_schedule(owner, rows)
        assert False, "Expected ValueError for duplicate task_id"
    except ValueError as exc:
        assert "Duplicate task_id" in str(exc)
