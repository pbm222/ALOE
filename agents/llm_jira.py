# agents/jira_drafts.py
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from utils.llm import ask_json

TRIAGED = Path("output") / "triaged_llm.json"
OUT = Path("output") / "jira_drafts.json"

SYSTEM = """You are a senior backend engineer writing Jira bug tickets for Java backend services.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.

You are given:
- A log cluster (service name, java_class, representative message, count)
- Triage info (label, severity, priority, confidence, reason)
- A stack_excerpt containing the first lines of the stack trace

Your job:
- Fill the team's Jira bug template with concrete, helpful content.
- Extract the most relevant stack frame (the first 'at ...Class.method(File.java:line)' line) from stack_excerpt.
- Clearly mention the service name, fully qualified Java class, method name, and line number in the description or notes for developers.
- If you cannot find a method/line, say so explicitly instead of guessing.
"""

USER_TEMPLATE = """Here is the log cluster and triage info:

Cluster JSON:
{cluster_json}

Our Jira bug ticket template has these sections:

Issue description
<Include a clear description of the problem, how often it occurs, and explicitly mention:
- service name
- Java class
- method name and line number extracted from stack_excerpt, if available.>

URL to Kibana
<Add a URL to Kibana that filters error.>

Kibana search query
<Add here exact and precise KQL filter that filters error>

Hits in past hours/days
<TODO> hits in past <TODO> hours/days

Notes for development
<>

Steps to reproduce
<>

Stack trace
<Include only the most relevant excerpt, including the key 'at ...Class.method(File.java:line)' line.>

The logs for this cluster were collected over approximately {time_window_hours} hours.

Use the following rules:
- Use the cluster's `count` and time window to describe frequency in "Issue description" and "Hits in past hours/days".
- For "URL to Kibana", DO NOT invent a real URL. Use a placeholder like "TODO: Add Kibana Discover URL with this KQL filter".
- For "Kibana search query", propose a precise KQL filter based on service, java_class, and a stable part of the message (do NOT include timestamps).
- For "Stack trace", extract only the most relevant few lines (exception type + 3–5 key frames), not the whole thing.
- For "Steps to reproduce", suggest reasonable, generic steps inferred from the log.

Return JSON with this exact schema:
{
  "summary": "Short Jira summary line",
  "issue_description": "Filled Issue description section",
  "kibana_url": "TODO placeholder as described",
  "kql_filter": "KQL query string",
  "hits_past_window": "e.g. '17 hits in past 48 hours'",
  "notes_for_development": "Filled Notes for development section",
  "steps_to_reproduce": "Filled Steps to reproduce section",
  "stack_trace_excerpt": "Relevant stack trace excerpt only"
}
"""

TIME_WINDOW_HOURS = 48  # adjust if you want


def _load_triaged() -> List[Dict[str, Any]]:
    data = json.loads(TRIAGED.read_text(encoding="utf-8"))
    return data.get("items", [])


def run(cluster_indices: Optional[List[int]] = None) -> Dict[str, Any]:
    """
    Generate Jira bug ticket drafts for the clusters selected by the orchestrator.

    cluster_indices:
      - list of idx values (from triaged_llm.json) to generate tickets for.
      - if None or empty, no tickets will be generated.
    """
    items = _load_triaged()
    idx_set = set(cluster_indices or [])

    selected = [it for it in items if it.get("idx") in idx_set]
    drafts: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    if not selected:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps(
                {
                    "draft_count": 0,
                    "skipped_count": len(items),
                    "drafts": [],
                    "skipped": [{"idx": it.get("idx"), "reason": "not selected by orchestrator"} for it in items],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return {"count": 0, "output": str(OUT)}

    for it in selected:
        cluster = {
            "idx": it.get("idx"),
            "signature": it.get("signature"),
            "service": it.get("service"),
            "java_class": it.get("java_class"),
            "message": it.get("message"),
            "count": it.get("count"),
            "triage": it.get("triage"),
            "stack_excerpt": it.get("stack_excerpt"),
        }

        user = USER_TEMPLATE.format(
            cluster_json=json.dumps(cluster, ensure_ascii=False, indent=2),
            time_window_hours=TIME_WINDOW_HOURS,
        )
        out = ask_json(SYSTEM, user)

        if out is None or (isinstance(out, dict) and "_error" in out):
            skipped.append(
                {
                    "idx": it.get("idx"),
                    "reason": f"LLM output error: {out.get('_error') if isinstance(out, dict) else 'unknown'}",
                    "triage": it.get("triage"),
                }
            )
            continue

        drafts.append(
            {
                "idx": it.get("idx"),
                "signature": it.get("signature"),
                "java_class": it.get("java_class"),
                "count": it.get("count"),
                "triage": it.get("triage"),
                "jira": out,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "draft_count": len(drafts),
                "skipped_count": len(skipped),
                "drafts": drafts,
                "skipped": skipped,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return {"count": len(drafts), "output": str(OUT)}
