# agents/summary.py
import json
from pathlib import Path
from typing import Dict, Any, List

TRIAGED_PATH = Path("output") / "triaged_llm.json"
RAW_LOGS_PATH = Path("output") / "raw_logs.json"
SUMMARY_PATH = Path("output") / "summary.json"


def _load_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_triaged() -> List[Dict[str, Any]]:
    """
    Load triaged clusters from output/triaged_llm.json

    Expected shape:
    {
      "items": [
        {
          "idx": int,
          "signature": str,
          "service": str,
          "java_class": str,
          "message": str,
          "count": int,
          "stack_excerpt": str,
          "triage": {
            "label": str,
            "priority": str,
            "severity": str,
            "confidence": float,
            "reason": str
          }
        },
        ...
      ]
    }
    """
    data = _load_json(TRIAGED_PATH, {})
    return data.get("items", [])


def _load_raw_logs_count() -> int:
    """
    Optionally load raw logs from output/raw_logs.json and return count.

    Adjust this to match your log_preprocessor output format.
    For now we expect either:
      { "logs": [ ... ] }
    or a plain list at top level.
    """
    data = _load_json(RAW_LOGS_PATH, [])
    if isinstance(data, dict):
        logs = data.get("logs") or data.get("items") or []
        return len(logs)
    if isinstance(data, list):
        return len(data)
    return 0


def build_summary() -> Dict[str, Any]:
    """
    Build a compact summary used by the LLM orchestrator.

    Produces something like:
    {
      "log_count": 100,
      "cluster_count": 38,
      "triaged_cluster_count": 38,
      "by_label": {"internal_error": 24, "noise": 1, "external_service": 13},
      "by_priority": {"high": 14, "medium": 23, "low": 1},
      "internal_high_count": 14
    }
    """
    triaged_items = load_triaged()
    cluster_count = len(triaged_items)

    # raw log count (if available)
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
