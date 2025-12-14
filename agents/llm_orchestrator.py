# agents/llm_orchestrator.py
import json
from typing import Dict, Any, List

from utils.file_loader import load_feedback
from utils.llm import ask_json

SYSTEM = SYSTEM = """You are an orchestration planner for a multi-agent log review system in an enterprise Java backend.

Available agents:
- JiraDrafts: generates Jira bug ticket drafts from important log clusters.
- FilterSuggestions: generates generalized Kibana/KQL filters for noisy or non-actionable logs.
- ConfluenceDraft: generates a Confluence-ready markdown summary of the log review session.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.

Important dependencies between agents:
- FilterSuggestions operates on the clusters that had Jira drafts created in THIS run
  (it reads jira_drafts.json). If JiraDrafts.run = false or cluster_indices is empty,
  FilterSuggestions will not have anything useful to do.
- ConfluenceDraft summarizes what happened in this run (tickets proposed, filters suggested).
  If neither JiraDrafts nor FilterSuggestions runs (or you expect no drafts/filters),
  you should usually set ConfluenceDraft.run = false.

Your job:
- Read the summary of the triaged log clusters.
- Inspect individual triaged clusters.
- Decide which agents to run this time.
- For JiraDrafts, explicitly choose which cluster indices should be turned into tickets.
- For each agent, optionally specify parameters (e.g. limits, thresholds).
- Explain your reasoning briefly.

Guidelines:
- Prefer JiraDrafts only for internal, high-impact errors with reasonable confidence.
- Prefer FilterSuggestions when there is a significant amount of noise, timeouts, or external_service errors,
  AND when JiraDrafts is actually producing drafts for those clusters.
- Prefer ConfluenceDraft when something meaningful happened (e.g. tickets proposed, new filters suggested),
  NOT on empty or trivial runs.
- It is allowed and sometimes preferred to run JiraDrafts but skip FilterSuggestions and/or ConfluenceDraft.
- If there are no external_service/timeout/noise clusters, you should usually set FilterSuggestions.run = false.
- If JiraDrafts.run = false AND there are no new filter suggestions to make, you should usually set ConfluenceDraft.run = false.
- Prefer conservative ticket creation (avoid spamming Jira for low-impact or low-confidence issues).
- Use both the numeric summary fields, the per-cluster triage information, and any feedback to decide.

Feedback:
- Some clusters may contain a 'feedback' field with previous human decisions:
  - decision: 'approved' means tickets for this signature were useful.
  - decision: 'rejected' means tickets for this signature were noise.
- In general, you should NOT propose JiraDrafts again for clusters that already have feedback
  (approved or rejected), because they have already been reviewed.
- If all clusters already have feedback and nothing important changed, you may skip JiraDrafts
  entirely by setting "run": false and an empty "cluster_indices" list.

Use this feedback to:
- Avoid proposing Jira tickets for signatures that were rejected as noise.
- Prefer tickets for signatures previously approved (assuming conditions are similar), but do not re-ticket the same signature repeatedly.

Your objectives, in order:
1) Ensure severe internal errors in production are not missed (favor JiraDrafts for these).
2) Reduce noise from recurring timeout/external_service issues by proposing filters.
3) Provide human-readable documentation only when there is something noteworthy to report, and skip ConfluenceDraft on uninteresting runs.

Trade-offs:
- If there are many severe internal_error clusters, prioritize JiraDrafts and ConfluenceDraft.
- If there are few or no internal_error clusters but many timeout/external_service clusters, prioritize FilterSuggestions and possibly skip JiraDrafts.
- If almost nothing happened (few clusters, mostly low severity), you may skip all agents or only run ConfluenceDraft with a short 'no critical issues' note.
"""

USER_TEMPLATE = """Here is the current summary of the log review state:

{summary_json}

Here are the triaged clusters (each with idx and triage info):

{clusters_json}

Decide which agents to run next and with which policies.

Return JSON with this exact schema:
{{
  "actions": [
    {{
      "agent": "JiraDrafts",
      "run": true or false,
      "cluster_indices": [<int> or empty list]
    }},
    {{
      "agent": "FilterSuggestions",
      "run": true or false,
      "for_labels": ["timeout", "external_service", "noise"],
      "min_count": <int or null>
    }},
    {{
      "agent": "ConfluenceDraft",
      "run": true or false
    }}
  ],
  "global_policy": {{
    "ticket_strategy": "aggressive"|"balanced"|"conservative",
    "noise_handling": "none"|"basic_filters"|"aggressive_filters"
  }},
  "reason": "short explanation of your decision"
}}
"""


def _compact_clusters(triaged_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    for it in triaged_items:
        triage = it.get("triage", {})
        compact.append(
            {
                "idx": it.get("idx"),
                "signature": it.get("signature"),
                "service": it.get("service"),
                "label": triage.get("label"),
                "priority": triage.get("priority"),
                "severity": triage.get("severity"),
                "confidence": triage.get("confidence"),
                "count": it.get("count"),
                "java_class": it.get("java_class"),
                "message": it.get("message"),
            }
        )
    return compact


def plan_actions(summary: Dict[str, Any], triaged_items: List[Dict[str, Any]], use_feedback: bool = True) -> Dict[str, Any]:
    compact_clusters = _compact_clusters(triaged_items)
    feedback_entries = load_feedback()

    fb_by_sig = {}
    if use_feedback:
        for fb in feedback_entries:
            sig = fb.get("signature")
            if not sig:
                continue
            fb_by_sig[sig] = {
                "decision": fb.get("decision"),
                "reason": fb.get("reason"),
            }

        for c in compact_clusters:
            sig = c.get("signature")
            if sig in fb_by_sig:
                c["feedback"] = fb_by_sig[sig]


    user_prompt = USER_TEMPLATE.format(
        summary_json=json.dumps(summary, ensure_ascii=False, indent=2),
        clusters_json=json.dumps(compact_clusters, ensure_ascii=False, indent=2),
    )

    out = ask_json(SYSTEM, user_prompt)

    actions = out.get("actions")
    if not isinstance(actions, list) or len(actions) == 0:
        actions = [
            {
                "agent": "JiraDrafts",
                "run": False,
                "cluster_indices": [],
            },
            {
                "agent": "FilterSuggestions",
                "run": False,
                "for_labels": ["timeout", "external_service", "noise"],
                "min_count": None,
            },
            {
                "agent": "ConfluenceDraft",
                "run": False,
            },
        ]

    normalized_actions = []
    for a in actions:
        agent = a.get("agent")
        if agent == "JiraDrafts":
            normalized_actions.append(
                {
                    "agent": "JiraDrafts",
                    "run": bool(a.get("run", False)),
                    "cluster_indices": a.get("cluster_indices", []),
                }
            )
        elif agent == "FilterSuggestions":
            normalized_actions.append(
                {
                    "agent": "FilterSuggestions",
                    "run": bool(a.get("run", False)),
                    "for_labels": a.get("for_labels", ["timeout", "external_service", "noise"]),
                    "min_count": a.get("min_count"),
                }
            )
        elif agent == "ConfluenceDraft":
            normalized_actions.append(
                {
                    "agent": "ConfluenceDraft",
                    "run": bool(a.get("run", False)),
                }
            )

    reason = out.get("reason", "no reason provided")
    global_policy = out.get("global_policy", {})

    return {
        "actions": normalized_actions,
        "global_policy": global_policy,
        "reason": reason,
    }
