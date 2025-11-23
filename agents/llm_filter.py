# agents/llm_filter.py
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from utils.llm import ask_json

TRIAGED = Path("output") / "triaged_llm.json"
OUT = Path("output") / "filter_suggestions.json"

# Limit how many filters we ask the LLM to generate in one run
MAX_FILTER_SUGGESTIONS = 3

SYSTEM = """You are a log filtering assistant for an enterprise backend system.

Your task is to propose precise regex or Kibana KQL filters that:
- Match the given error cluster reliably.
- Generalize dynamic parts such as IDs, UUIDs, timestamps, numeric values.
- Keep stable constants (service name, error code, class name, key phrases) as literals.
- Avoid over-matching unrelated logs.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.
"""

USER_TEMPLATE = """You will receive a single log cluster with:
- service name
- Java class
- representative message
- count (how many times it occurred)
- triage metadata (label, severity, priority, confidence)

Cluster:
{cluster_json}

Return JSON with this exact schema:
{{
  "regex": "string or null",
  "kql": "string or null",
  "explanation": "why this matches the issue without catching unrelated logs"
}}
"""


def _load_triaged() -> List[Dict[str, Any]]:
    """
    Load triaged clusters from output/triaged_llm.json.

    Expected shape:
    {
      "items": [
        {
          "idx": int,
          "service": str,
          "java_class": str,
          "message": str,
          "count": int,
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
    if not TRIAGED.exists():
        return []
    data = json.loads(TRIAGED.read_text(encoding="utf-8"))
    return data.get("items", [])


def run(for_labels: Optional[List[str]] = None,
        min_count: Optional[int] = None) -> Dict[str, Any]:
    """
    Generate filter suggestions for noisy or recurring clusters.

    Parameters:
        for_labels: list of triage labels to consider (e.g. ["timeout", "external_service", "noise"]).
                    If None, defaults to ["timeout", "external_service", "noise"].
        min_count:  minimum occurrence count for a cluster to be considered. If None, no threshold.

    Returns:
        { "count": int, "output": "path/to/filter_suggestions.json" }
    """
    if for_labels is None:
        for_labels = ["timeout", "external_service", "noise"]

    items = _load_triaged()
    if not items:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"suggestions": []}, indent=2), encoding="utf-8")
        return {"count": 0, "output": str(OUT)}

    selected: List[Dict[str, Any]] = []
    for it in items:
        triage = it.get("triage", {})
        label = triage.get("label")
        count = it.get("count", 0)

        if label not in for_labels:
            continue
        if min_count is not None and count < min_count:
            continue

        selected.append(it)

    selected = selected[:MAX_FILTER_SUGGESTIONS]

    suggestions: List[Dict[str, Any]] = []

    for it in selected:
        cluster_payload = {
            "idx": it.get("idx"),
            "service": it.get("service"),
            "java_class": it.get("java_class"),
            "message": it.get("message"),
            "count": it.get("count"),
            "triage": it.get("triage"),
        }

        user = USER_TEMPLATE.format(
            cluster_json=json.dumps(cluster_payload, ensure_ascii=False, indent=2)
        )

        out = ask_json(SYSTEM, user)

        if not isinstance(out, dict):
            continue

        suggestions.append(
            {
                "cluster_idx": it.get("idx"),
                "service": it.get("service"),
                "java_class": it.get("java_class"),
                "count": it.get("count"),
                "label": cluster_payload["triage"].get("label") if cluster_payload.get("triage") else None,
                "regex": out.get("regex"),
                "kql": out.get("kql"),
                "explanation": out.get("explanation"),
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"suggestions": suggestions}, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"count": len(suggestions), "output": str(OUT)}
