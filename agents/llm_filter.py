# agents/llm_filter.py
import json
from pathlib import Path
from typing import Dict, Any, List
from utils.llm import ask_json

DRAFTS = Path("output") / "jira_drafts.json"
OUT = Path("output") / "filter_suggestions.json"
MAX_FILTER_SUGGESTIONS = 1

SYSTEM = """You are a log filtering assistant.
Given a cluster message and class, produce a safe regex or KQL snippet that matches this issue without over-matching.
- Generalize variable IDs, UUIDs, timestamps.
- Keep constants literal.
Return strict JSON."""

USER_TEMPLATE = """Input:
{cluster_json}

Output JSON schema:
{{
  "regex": "string or null",
  "kql": "string or null",
  "explanation": "why this matches the issue without catching unrelated logs"
}}"""

def run() -> Dict[str, Any]:
    data = json.loads(DRAFTS.read_text(encoding="utf-8"))
    drafts: List[Dict[str, Any]] = data.get("drafts", [])

    drafts = drafts[:MAX_FILTER_SUGGESTIONS]  # <= only first N drafts

    suggs: List[Dict[str, Any]] = []
    for d in drafts:
        cluster = d.get("cluster", {})
        user = USER_TEMPLATE.format(cluster_json=json.dumps(cluster, ensure_ascii=False, indent=2))
        out = ask_json(SYSTEM, user)
        suggs.append({
            "cluster_idx": d.get("cluster_idx"),
            "regex": out.get("regex"),
            "kql": out.get("kql"),
            "explanation": out.get("explanation"),
            "summary": d.get("summary"),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"suggestions": suggs}, indent=2), encoding="utf-8")
    return {"count": len(suggs), "output": str(OUT)}
