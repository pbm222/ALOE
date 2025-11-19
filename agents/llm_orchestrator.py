# agents/llm_orchestrator.py
import json
from typing import Dict, Any
from utils.llm import ask_json


SYSTEM = """You are an orchestration planner for a multi-agent log review system in an enterprise Java backend.

Available agents:
- JiraDrafts: generates Jira bug ticket drafts from important log clusters.
- FilterSuggestions: generates generalized Kibana/KQL filters for noisy or non-actionable logs.
- ConfluenceDraft: generates a Confluence-ready markdown summary of the log review session.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.

Your job:
- Read the summary of the triaged log clusters.
- Decide which agents to run this time.
- For each agent, optionally specify parameters (e.g. limits, thresholds).
- Explain your reasoning briefly.

Guidelines:
- JiraDrafts should run only if there are enough high-priority internal errors to justify developer attention.
- FilterSuggestions should run when there is a significant amount of noise, timeouts, or external_service errors.
- ConfluenceDraft should run when something meaningful happened (e.g. tickets proposed, new filters suggested), not on empty or trivial runs.
- Prefer conservative ticket creation (avoid spamming Jira for low-impact or low-confidence issues).
- Use the numeric summary fields and label/priority distributions to decide."""

USER_TEMPLATE = """Here is the current summary of the log review state:

{summary_json}

Decide which agents to run next and with which policies.

Return JSON with this exact schema:
{{
  "actions": [
    {{
      "agent": "JiraDrafts",
      "run": true or false,
      "max_tickets": <int or null>,
      "min_severity": "low"|"medium"|"high"|null,
      "min_confidence": <float between 0 and 1 or null>
    }},
    {{
      "agent": "FilterSuggestions",
      "run": true or false,
      "for_labels": ["timeout", "external_service", "noise"],
      "min_count": <int or null>
    }},
    {{
      "agent": "ConfluenceDraft",
      "run": true or false,
      "include_sections": ["summary", "jira_links", "filters"]
    }}
  ],
  "global_policy": {{
    "ticket_strategy": "aggressive"|"balanced"|"conservative",
    "noise_handling": "none"|"basic_filters"|"aggressive_filters"
  }},
  "reason": "short explanation of your decision"
}}"""


def plan_actions(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call the LLM orchestrator to decide which agents to run and with what policies.

    Example summary:
    {
      "log_count": 100,
      "cluster_count": 38,
      "triaged_cluster_count": 38,
      "by_label": {"internal_error": 24, "noise": 1, "external_service": 13},
      "by_priority": {"high": 14, "medium": 23, "low": 1},
      "internal_high_count": 14
    }
    """
    user_prompt = USER_TEMPLATE.format(
        summary_json=json.dumps(summary, ensure_ascii=False, indent=2)
    )
    out = ask_json(SYSTEM, user_prompt)

    actions = out.get("actions")
    if not isinstance(actions, list) or len(actions) == 0:
        # Safe default: don't run anything
        actions = [
            {
                "agent": "JiraDrafts",
                "run": False,
                "max_tickets": None,
                "min_severity": None,
                "min_confidence": None,
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
                "include_sections": ["summary"],
            },
        ]

    # Normalize fields a bit to avoid KeyError downstream
    normalized_actions = []
    for a in actions:
        agent = a.get("agent")
        if agent == "JiraDrafts":
            normalized_actions.append(
                {
                    "agent": "JiraDrafts",
                    "run": bool(a.get("run", False)),
                    "max_tickets": a.get("max_tickets"),
                    "min_severity": a.get("min_severity"),
                    "min_confidence": a.get("min_confidence"),
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
                    "include_sections": a.get("include_sections", ["summary", "jira_links", "filters"]),
                }
            )

    reason = out.get("reason", "no reason provided")
    global_policy = out.get("global_policy", {})

    return {
        "actions": normalized_actions,
        "global_policy": global_policy,
        "reason": reason,
    }
