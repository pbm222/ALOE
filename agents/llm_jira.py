# agents/jira_drafts.py
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from utils.llm import ask_json

TRIAGED = Path("output") / "triaged_llm.json"
OUT = Path("output") / "jira_drafts.json"

# how many hours of logs your input window covered (adjust as needed)
TIME_WINDOW_HOURS = 48


# ---------------------------
# Simple ticket policy (inline for now)
# ---------------------------

FRONTEND_HINTS = ["ui", "frontend", "spa", "webclient", "react"]
LOW_IMPORTANCE_PATTERNS = [
    "broken pipe",
    "connection reset by peer",
    "client aborted",
]


def _is_frontend_service(service: Optional[str]) -> bool:
    if not service:
        return False
    s = service.lower()
    return any(h in s for h in FRONTEND_HINTS)


def should_create_ticket(cluster: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decide whether this cluster deserves a Jira ticket.

    Expects `cluster` to contain:
      - triage: {label, severity, priority, confidence, reason}
      - service / athena_service (optional)
      - message
      - count
    """
    triage = cluster.get("triage", {})
    label = triage.get("label")
    severity = triage.get("severity")
    priority = triage.get("priority")
    confidence = float(triage.get("confidence", 0.0) or 0.0)

    service = cluster.get("service") or cluster.get("athena_service") or ""
    message = (cluster.get("message") or "").lower()
    count = cluster.get("count", 0)

    # 0) Only internal backend errors can become tickets
    if label != "internal_error":
        return {"create": False, "reason": f"label={label} (not internal_error)"}

    # 1) Skip obvious frontend services
    if _is_frontend_service(service):
        return {"create": False, "reason": f"service={service} looks like frontend"}

    # 2) Require at least medium severity
    if severity == "low":
        return {"create": False, "reason": "severity=low"}

    # 3) Require enough confidence from LLM
    if confidence < 0.6:
        return {"create": False, "reason": f"low confidence={confidence:.2f}"}

    # 4) Skip boring technical noise
    if any(p in message for p in LOW_IMPORTANCE_PATTERNS):
        return {"create": False, "reason": "matches low-importance pattern"}

    # 5) If it only happened once and priority is low → probably not worth it
    if count == 1 and priority == "low":
        return {"create": False, "reason": "single low-priority occurrence"}

    # otherwise, it's worth a ticket
    return {
        "create": True,
        "reason": (
            "internal backend error, "
            f"severity={severity}, priority={priority}, "
            f"confidence={confidence:.2f}, count={count}"
        ),
    }


# ---------------------------
# LLM prompt for filling your Jira template
# ---------------------------

SYSTEM = """You are a senior backend engineer writing Jira bug tickets for Java backend services.
You must produce high-quality, concise descriptions and practical steps for developers.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.

You are given:
- A log cluster (representative message, optional stack trace, count, service, etc.)
- Triage info (label, severity, priority, confidence, reason)

You must fill the team's Jira bug template with concrete, helpful content.
If some information is not available (e.g. exact Kibana URL), use a clear TODO placeholder instead of hallucinating.
"""

USER_TEMPLATE = """Here is the log cluster and triage info:

Cluster JSON:
{cluster_json}

Our Jira bug ticket template has these sections:

Issue description
<What has been discovered? Please describe it. How often does this occur? Determine priority! Include screenshots and so on.>

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
<>

The logs for this cluster were collected over approximately {time_window_hours} hours.

Use the following rules:
- Use the cluster's `count` and time window to describe frequency in "Issue description" and "Hits in past hours/days".
- For "URL to Kibana", DO NOT invent a real URL. Use a placeholder like "TODO: Add Kibana Discover URL with this KQL filter".
- For "Kibana search query", propose a precise KQL filter based on service, java_class, and a stable part of the message (do NOT include timestamps).
- For "Stack trace", extract only the most relevant few lines (exception type + 3–5 key frames), not the whole thing.
- For "Steps to reproduce", suggest reasonable, generic steps inferred from the log (e.g. "Create annual motor quote with invalid convictionDate format").

Return JSON with this exact schema:
{{
  "summary": "Short Jira summary line",
  "issue_description": "Filled Issue description section",
  "kibana_url": "TODO placeholder as described",
  "kql_filter": "KQL query string",
  "hits_past_window": "e.g. '17 hits in past 48 hours'",
  "notes_for_development": "Filled Notes for development section",
  "steps_to_reproduce": "Filled Steps to reproduce section",
  "stack_trace_excerpt": "Relevant stack trace excerpt only"
}}
"""


# ---------------------------
# Main entrypoint
# ---------------------------

def run() -> Dict[str, Any]:
    """
    Generate Jira bug ticket drafts for important clusters based on triaged_llm.json.

    Expects triaged_llm.json to have shape:
    {
      "items": [
        {
          "idx": <int>,
          "java_class": "...",
          "message": "...",
          "count": <int>,
          "triage": {
            "label": "...",
            "priority": "...",
            "severity": "...",
            "confidence": <float>,
            "reason": "..."
          }
        },
        ...
      ]
    }
    """
    data = json.loads(TRIAGED.read_text(encoding="utf-8"))
    items: List[Dict[str, Any]] = data.get("items", [])

    drafts: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for item in items:
        # Build a "cluster" dict we can reason about.
        cluster: Dict[str, Any] = {
            "idx": item.get("idx"),
            "java_class": item.get("java_class"),
            "message": item.get("message"),
            "count": item.get("count"),
            "triage": item.get("triage"),
            # placeholders for future enrichment (service/env/etc.)
            "service": item.get("service") or item.get("athena_service"),
        }

        decision = should_create_ticket(cluster)
        if not decision.get("create"):
            skipped.append(
                {
                    "idx": item.get("idx"),
                    "reason": decision.get("reason"),
                    "triage": item.get("triage"),
                }
            )
            continue

        user = USER_TEMPLATE.format(
            cluster_json=json.dumps(cluster, ensure_ascii=False, indent=2),
            time_window_hours=TIME_WINDOW_HOURS,
        )
        out = ask_json(SYSTEM, user)

        # Handle LLM parse failure gracefully
        if out is None or (isinstance(out, dict) and "_error" in out):
            skipped.append(
                {
                    "idx": item.get("idx"),
                    "reason": f"LLM output error: {out.get('_error') if isinstance(out, dict) else 'unknown'}",
                    "triage": item.get("triage"),
                }
            )
            continue

        drafts.append(
            {
                "idx": item.get("idx"),
                "service": cluster.get("service"),
                "java_class": cluster.get("java_class"),
                "count": cluster.get("count"),
                "triage": cluster.get("triage"),
                "jira": out,
                "ticket_policy_reason": decision.get("reason"),
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
