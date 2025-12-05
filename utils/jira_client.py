# utils/jira_client.py
import os
import json
from typing import Optional, Dict, Any

import requests
from rich import print


# Environment-based configuration for REAL Jira mode
JIRA_BASE_URL = os.getenv("ALOE_JIRA_URL")          # e.g. "https://your-domain.atlassian.net"
JIRA_PROJECT_KEY = os.getenv("ALOE_JIRA_PROJECT")   # e.g. "PROJ"
JIRA_USER = os.getenv("ALOE_JIRA_USER")             # e.g. email or username
JIRA_TOKEN = os.getenv("ALOE_JIRA_TOKEN")           # API token


def create_jira_issue_from_draft(draft: Dict[str, Any], mode: str = "mock") -> Optional[str]:
    """
    Create a Jira issue based on a draft.

    - mode="mock": only prints to console, no HTTP calls.
    - mode="real": sends POST to Jira REST API (v3).

    Returns:
        Jira issue key (e.g. "PROJ-123") in real mode, or None in mock/failed mode.
    """
    summary = draft.get("summary") or "Log-based issue"
    description = (
            draft.get("issue_description")
            or draft.get("description")
            or "Automatically generated issue from log analysis."
    )

    if mode == "mock":
        print(f"[bold cyan][MOCK][/bold cyan] Would create Jira ticket: [bold]{summary}[/bold]")
        return None

    # REAL mode
    if not all([JIRA_BASE_URL, JIRA_PROJECT_KEY, JIRA_USER, JIRA_TOKEN]):
        print("[red]Jira configuration missing (ALOE_JIRA_URL / PROJECT / USER / TOKEN). Cannot create real issue.[/red]")
        return None

    url = JIRA_BASE_URL.rstrip("/") + "/rest/api/3/issue"
    headers = {"Content-Type": "application/json"}
    auth = (JIRA_USER, JIRA_TOKEN)

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Bug"},
        }
    }

    try:
        resp = requests.post(url, headers=headers, auth=auth, data=json.dumps(payload))
    except Exception as e:
        print(f"[red]Error calling Jira API: {e}[/red]")
        return None

    if 200 <= resp.status_code < 300:
        data = resp.json()
        key = data.get("key")
        print(f"[bold green][REAL][/bold green] Created Jira issue [bold]{key}[/bold] for draft: {summary}")
        return key

    print(f"[red]Failed to create Jira issue: {resp.status_code} {resp.text}[/red]")
    return None
