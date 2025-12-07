# utils/jira_client.py
import os
import json
from typing import Optional, Dict, Any, List

import requests
from rich import print

JIRA_BASE_URL = os.getenv("ALOE_JIRA_URL")
JIRA_PROJECT_KEY = os.getenv("ALOE_JIRA_PROJECT")
JIRA_USER = os.getenv("ALOE_JIRA_USER")
JIRA_TOKEN = os.getenv("ALOE_JIRA_TOKEN")

def create_jira_issues(drafts: List[Dict[str, Any]], mode: str = "mock") -> Optional[str]:
    for draft in drafts:
        create_jira_issue_from_draft(draft, mode)

def create_jira_issue_from_draft(draft: Dict[str, Any], mode: str = "mock") -> Optional[str]:
    summary = draft.get("summary") or "Log-based issue"
    description = (
            draft.get("issue_description")
            or draft.get("description")
            or "Automatically generated issue from log analysis."
    )

    if mode == "mock":
        print(f"[bold cyan][MOCK][/bold cyan] Would create Jira ticket: [bold]{summary}[/bold]")
        return None

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
