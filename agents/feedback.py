# agents/feedback.py
import json
from pathlib import Path
from typing import List, Dict, Any

FEEDBACK_PATH = Path("output") / "feedback.json"


def load_feedback() -> List[Dict[str, Any]]:
    if not FEEDBACK_PATH.exists():
        return []
    try:
        return json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_feedback(entries: List[Dict[str, Any]]) -> None:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def append_feedback(entry: Dict[str, Any]) -> None:
    entries = load_feedback()
    entries.append(entry)
    save_feedback(entries)
