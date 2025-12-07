from typing import List, Dict, Any
import json
from pathlib import Path

TRIAGED = Path("output") / "triaged_logs.json"
JIRA_DRAFTS = Path("output") / "jira_drafts.json"
FILTERS = Path("output") / "filter_suggestions.json"
FEEDBACK = Path("output") / "feedback.json"
CLUSTERS_OUTPUT = Path("output") / "clusters.json"

def _load_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def load_triaged() -> List[Dict[str, Any]]:
    data = _load_json(TRIAGED, {})
    return data.get("items", [])

def load_jira_drafts() -> List[Dict[str, Any]]:
    data = _load_json(JIRA_DRAFTS, {})
    return data.get("drafts", [])

def load_filter() -> List[Dict[str, Any]]:
    data = _load_json(FILTERS, {})
    return data.get("suggestions", [])

def load_clusters() -> List[Dict[str, Any]]:
    data = _load_json(CLUSTERS_OUTPUT, {})
    return data.get("clusters", [])


def load_feedback() -> List[Dict[str, Any]]:
    if not FEEDBACK.exists():
        return []
    try:
        return json.loads(FEEDBACK.read_text(encoding="utf-8"))
    except Exception:
        return []