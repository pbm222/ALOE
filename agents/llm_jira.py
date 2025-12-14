# agents/jira_drafts.py
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from utils.file_loader import load_triaged
from utils.jira_client import create_jira_issues
from utils.llm import ask_json

JIRA_OUTPUT = Path("output") / "jira_drafts.json"
BATCH_SIZE = 10

SYSTEM = """You are a senior backend engineer writing Jira bug tickets for Java backend services.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.

You will receive a LIST of log clusters. Each cluster has:
- idx: numeric index
- service: service name
- java_class: Java class or component name
- message: representative log message
- count: number of occurrences
- triage: label, severity, priority, confidence, reason
- stack_excerpt: the first lines of the stack trace

Your job for EACH cluster:
- Fill the team's Jira bug template with concrete, helpful content.
- Extract the most relevant stack frame (the first 'at ...Class.method(File.java:line)' line) from stack_excerpt.
- Clearly mention the service name, fully qualified Java class, method name, and line number in the description or notes for developers.
- If you cannot find a method/line, say so explicitly instead of guessing.

Use the cluster's `count` and time window to describe frequency (e.g. "17 hits in past 48 hours").
For the Kibana URL, DO NOT invent a real URL. Use a placeholder like:
  "TODO: Add Kibana Discover URL with this KQL filter".
For the KQL filter, propose a precise query based on service, java_class, and a stable part of the message (no timestamps).

You must return a single JSON object with key "items".

"items" must be a list where each element corresponds to one input cluster and has:
- "idx": the same idx as the input cluster
- "summary": short Jira summary line
- "service_name": name of the service
- "issue_description": filled Issue description section
- "kibana_url": placeholder URL as described
- "kql_filter": KQL query string
- "hits_past_window": e.g. "17 hits in past 48 hours"
- "notes_for_development": filled Notes for development section
- "steps_to_reproduce": filled Steps to reproduce section
- "stack_trace_excerpt": relevant stack trace excerpt only
"""

USER_TEMPLATE = """Here is the list of log clusters and triage info.

The logs for these clusters were collected over approximately 24 hours.

Clusters:
{clusters_json}

For EACH cluster in this list, produce one Jira draft object as described in the system prompt.
Return a single JSON object with key "items" as specified.
"""

def _chunked(seq: List[Any], size: int) -> List[List[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]

def run(cluster_indices: Optional[List[int]] = None, mode: str = "orchestrator") -> Dict[str, Any]:
    items = load_triaged()

    if mode == "pipeline":
        selected = list(items)
        skipped: List[Dict[str, Any]] = []
    else:
        idx_set = set(cluster_indices or [])
        selected = [it for it in items if it.get("idx") in idx_set]
        skipped = [
            {
                "idx": it.get("idx"),
                "reason": "not selected",
                "triage": it.get("triage"),
            }
            for it in items
            if it.get("idx") not in idx_set
        ]

    drafts: List[Dict[str, Any]] = []

    if not selected:
        JIRA_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        JIRA_OUTPUT.write_text(
            json.dumps(
                {
                    "draft_count": 0,
                    "skipped_count": len(items),
                    "drafts": [],
                    "skipped": [
                        {"idx": it.get("idx"), "reason": "not selected"}
                        for it in items
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return {"count": 0, "output": str(JIRA_OUTPUT)}

    jira_by_idx: Dict[Any, Dict[str, Any]] = {}

    for batch in _chunked(selected, BATCH_SIZE):
        cluster_payloads: List[Dict[str, Any]] = []
        for it in batch:
            cluster_payloads.append(
                {
                    "idx": it.get("idx"),
                    "signature": it.get("signature"),
                    "service": it.get("service"),
                    "java_class": it.get("java_class"),
                    "message": it.get("message"),
                    "count": it.get("count"),
                    "triage": it.get("triage"),
                    "stack_excerpt": it.get("stack_excerpt"),
                }
            )

        user = USER_TEMPLATE.format(
            clusters_json=json.dumps(cluster_payloads, ensure_ascii=False, indent=2))

        out = ask_json(SYSTEM, user)

        if not isinstance(out, dict):
            for it in batch:
                skipped.append(
                    {
                        "idx": it.get("idx"),
                        "reason": "LLM output not a dict",
                        "triage": it.get("triage"),
                    }
                )
            continue

        items_out = out.get("items")
        if items_out is None:
            if len(batch) == 1:
                jira_by_idx[batch[0].get("idx")] = out
            else:
                for it in batch:
                    skipped.append(
                        {
                            "idx": it.get("idx"),
                            "reason": "no 'items' field in LLM output for batch",
                            "triage": it.get("triage"),
                        }
                    )
            continue

        if not isinstance(items_out, list):
            for it in batch:
                skipped.append(
                    {
                        "idx": it.get("idx"),
                        "reason": "'items' is not a list in LLM output",
                        "triage": it.get("triage"),
                    }
                )
            continue

        for ji in items_out:
            if not isinstance(ji, dict):
                continue
            idx = ji.get("idx")
            if idx is None:
                continue
            jira_by_idx[idx] = ji

    for it in selected:
        idx = it.get("idx")
        jira = jira_by_idx.get(idx)

        if jira is None:
            skipped.append(
                {
                    "idx": idx,
                    "reason": "no Jira draft returned for this idx",
                    "triage": it.get("triage"),
                }
            )
            continue

        drafts.append(
            {
                "idx": idx,
                "signature": it.get("signature"),
                "java_class": it.get("java_class"),
                "count": it.get("count"),
                "triage": it.get("triage"),
                "jira": jira,
            }
        )

    JIRA_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    JIRA_OUTPUT.write_text(
        json.dumps(
            {
                "draft_count": len(drafts),
                "skipped_triaged_issues_count": len(skipped),
                "drafts": drafts,
                "skipped": skipped,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    create_jira_issues(drafts)

    return {"count": len(drafts), "output": str(JIRA_OUTPUT)}
