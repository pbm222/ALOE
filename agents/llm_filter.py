# agents/llm_filter.py
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from utils.llm import ask_json

TRIAGED = Path("output") / "triaged_llm.json"
OUT = Path("output") / "filter_suggestions.json"
JIRA_DRAFTS = Path("output") / "jira_drafts.json"

# Limit how many filters we ask the LLM to generate in one run
MAX_FILTER_SUGGESTIONS = 3

SYSTEM = """You are a log filtering assistant for an enterprise backend system.

Your task is to propose precise regex or Kibana KQL filters that:
- Match the given error cluster reliably.
- Generalize dynamic parts such as IDs, UUIDs, timestamps, numeric values.
- Keep stable constants (service name, error code, class name, key phrases) as literals.
- Avoid over-matching unrelated logs.

Additionally, you must generate an Elasticsearch filter clause that can be inserted
directly into the 'must_not' array of an existing query. This clause should usually be:

- A simple match_phrase on the 'log' field, e.g.:
  { "match_phrase": { "log": "Some stable error text" } }

or, if necessary, a bool with multiple match_phrase subclauses, e.g.:
  {
    "bool": {
      "must": [
        { "match_phrase": { "log": "Part 1 of message" } },
        { "match_phrase": { "log": "Part 2 of message" } }
      ]
    }
  }

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
  "es_filter_clause": {{
    "match_phrase": {{ "log": "..." }}
  }}
}}
"""


def run(for_labels: Optional[List[str]] = None,
        min_count: Optional[int] = None) -> Dict[str, Any]:

    if not JIRA_DRAFTS.exists():
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"suggestions": []}, indent=2), encoding="utf-8")
        return {"count": 0, "output": str(OUT)}

    drafts_data = json.loads(JIRA_DRAFTS.read_text(encoding="utf-8"))
    drafts: List[Dict[str, Any]] = drafts_data.get("drafts", [])

    if not drafts:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"suggestions": []}, indent=2), encoding="utf-8")
        return {"count": 0, "output": str(OUT)}

    # drafts = drafts[:MAX_FILTER_SUGGESTIONS]

    suggestions: List[Dict[str, Any]] = []

    for d in drafts:
        cluster_payload = d.get("cluster") or {
            "idx": d.get("cluster_idx"),
            "service": d.get("service"),
            "java_class": d.get("java_class"),
            "message": d.get("message"),
            "count": d.get("count"),
            "triage": d.get("triage"),
        }

        user = USER_TEMPLATE.format(
            cluster_json=json.dumps(cluster_payload, ensure_ascii=False, indent=2)
        )

        out = ask_json(SYSTEM, user)

        if not isinstance(out, dict):
            continue

        suggestions.append(
            {
                "cluster_idx": d.get("cluster_idx"),
                "service": cluster_payload.get("service"),
                "java_class": cluster_payload.get("java_class"),
                "count": cluster_payload.get("count"),
                "label": (cluster_payload.get("triage") or {}).get("label"),
                "es_filter_clause": out.get("es_filter_clause"),
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"suggestions": suggestions}, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"count": len(suggestions), "output": str(OUT)}
