import json
import os
from datetime import datetime
from typing import Any

STATE_FILE = "state.json"


def _load() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE) as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get(key: str, default: Any = None) -> Any:
    return _load().get(key, default)


def set_val(key: str, value: Any) -> None:
    data = _load()
    data[key] = value
    _save(data)


def record_cycle() -> None:
    set_val("last_cycle_at", datetime.utcnow().isoformat())


def _issue_key(project_name: str, issue_number: int) -> str:
    return f"{project_name}#{issue_number}"


def add_in_progress(project_name: str, issue_number: int) -> None:
    s = get_in_progress_set()
    s.add(_issue_key(project_name, issue_number))
    set_val("in_progress_issues", list(s))


def remove_in_progress(project_name: str, issue_number: int) -> None:
    s = get_in_progress_set()
    s.discard(_issue_key(project_name, issue_number))
    set_val("in_progress_issues", list(s))


def is_in_progress(project_name: str, issue_number: int) -> bool:
    return _issue_key(project_name, issue_number) in get_in_progress_set()


def get_in_progress_set() -> set:
    return set(get("in_progress_issues", []))
