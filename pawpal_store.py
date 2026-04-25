"""Single-user JSON persistence for PawPal+ (owner, pets, tasks)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from pawpal_system import Owner, Pet, Task

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

_DEFAULT_OWNER_NAME = "Jordan"

ALLOWED_FREQUENCIES = frozenset({"daily", "weekly", "once"})


def default_store_path() -> Path:
    """Path to the JSON store next to this package (project data/)."""
    return Path(__file__).resolve().parent / "data" / "pawpal_store.json"


class TaskValidationError(ValueError):
    """Raised when task fields fail validation before persistence."""


class TaskOverlapError(ValueError):
    """Raised when a new task overlaps another pending task on the owner."""


def _parse_due_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TaskValidationError(f"Invalid due_date: {value!r}")


def _task_to_dict(task: Task) -> dict[str, Any]:
    return {
        "id": task.task_id,
        "description": task.description,
        "time_minutes": task.time_minutes,
        "frequency": task.frequency,
        "completed": task.completed,
        "due_date": task.due_date.isoformat() if task.due_date is not None else None,
        "start_time": task.start_time,
    }


def _task_from_dict(data: dict[str, Any]) -> Task:
    tid = data.get("id")
    start_time_raw = data.get("start_time", None)
    return Task(
        description=str(data["description"]),
        time_minutes=int(data["time_minutes"]),
        frequency=str(data["frequency"]),
        completed=bool(data.get("completed", False)),
        due_date=_parse_due_date(data.get("due_date")),
        start_time=None if start_time_raw is None else str(start_time_raw),
        task_id=str(tid) if tid else None,
    )


def _owner_to_dict(owner: Owner) -> dict[str, Any]:
    pets_out: list[dict[str, Any]] = []
    for pet in owner.pets:
        pets_out.append(
            {
                "name": pet.name,
                "species": pet.species,
                "tasks": [_task_to_dict(t) for t in pet.tasks],
            }
        )
    return {"schema_version": SCHEMA_VERSION, "owner": {"name": owner.name, "pets": pets_out}}


def validate_task_fields(task: Task) -> None:
    """Raise TaskValidationError if task fields are not allowed for insert."""
    desc = task.description.strip()
    if not desc:
        raise TaskValidationError("Task description cannot be empty.")
    if not (1 <= task.time_minutes <= 240):
        raise TaskValidationError("Time (minutes) must be between 1 and 240.")
    if task.frequency not in ALLOWED_FREQUENCIES:
        raise TaskValidationError(f"Frequency must be one of {sorted(ALLOWED_FREQUENCIES)}.")


def assert_task_can_be_added(owner: Owner, pet: Pet, task: Task) -> None:
    """Validate fields and owner registration for inserts."""
    validate_task_fields(task)
    if pet not in owner.pets:
        raise TaskValidationError("Pet is not registered with this owner.")


def owner_from_dict(payload: dict[str, Any]) -> Owner:
    """Build Owner graph from stored dict."""
    version = int(payload.get("schema_version", 1))
    if version not in (1, SCHEMA_VERSION):
        raise ValueError(f"Unsupported schema_version {version!r}; expected 1 or {SCHEMA_VERSION}.")

    raw_owner = payload["owner"]
    name = str(raw_owner.get("name", _DEFAULT_OWNER_NAME)).strip() or _DEFAULT_OWNER_NAME
    owner = Owner(name)

    for p in raw_owner.get("pets", []):
        pet = Pet(str(p["name"]), str(p["species"]))
        for t in p.get("tasks", []):
            pet.add_task(_task_from_dict(t))
        owner.add_pet(pet)

    return owner


def load_owner(path: Path | None = None) -> Owner | None:
    """
    Load owner from JSON file. Returns None if file does not exist.
    Raises ValueError / json.JSONDecodeError on invalid content.
    """
    p = path or default_store_path()
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    return owner_from_dict(data)


def save_owner(owner: Owner, path: Path | None = None) -> None:
    """Atomically write owner state to JSON (temp file + replace)."""
    p = path or default_store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = _owner_to_dict(owner)
    fd, tmp_name = tempfile.mkstemp(
        prefix="pawpal_store_",
        suffix=".tmp",
        dir=str(p.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.replace(tmp_name, p)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    logger.info("Saved owner state to %s", p)


def try_add_task(owner: Owner, pet: Pet, task: Task) -> None:
    """Validate and append task to pet; raises TaskValidationError or TaskOverlapError."""
    assert_task_can_be_added(owner, pet, task)
    pet.add_task(task)


def ensure_default_store(path: Path | None = None) -> Owner:
    """If store missing, create default owner file and return owner."""
    p = path or default_store_path()
    existing = load_owner(p)
    if existing is not None:
        return existing
    owner = Owner(_DEFAULT_OWNER_NAME)
    save_owner(owner, p)
    return owner
