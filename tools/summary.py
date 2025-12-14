# agents/summary.py
import json
from pathlib import Path
from typing import Dict, Any

from utils.file_loader import load_triaged, _load_json

RAW_LOGS_PATH = Path("output") / "raw_logs.json"
SUMMARY_PATH = Path("output") / "summary.json"

def _load_raw_logs_count() -> int:
    data = _load_json(RAW_LOGS_PATH, [])
    if isinstance(data, dict):
        logs = data.get("logs") or data.get("items") or []
        return len(logs)
    if isinstance(data, list):
        return len(data)
    return 0

def build_summary() -> Dict[str, Any]:
    triaged_items = load_triaged()
    cluster_count = len(triaged_items)

    log_count = _load_raw_logs_count()

    by_label: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}
    internal_high_count = 0

    for it in triaged_items:
        triage = it.get("triage", {})
        label = (triage.get("label") or "").strip()
        priority = (triage.get("priority") or "").strip()
        severity = (triage.get("severity") or "").strip()

        if label:
            by_label[label] = by_label.get(label, 0) + 1
        if priority:
            by_priority[priority] = by_priority.get(priority, 0) + 1

        if label == "internal_error" and priority == "high":
            internal_high_count += 1

    summary: Dict[str, Any] = {
        "log_count": log_count,
        "cluster_count": cluster_count,
        "triaged_cluster_count": cluster_count,
        "by_label": by_label,
        "by_priority": by_priority,
        "internal_high_count": internal_high_count,
    }

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary
