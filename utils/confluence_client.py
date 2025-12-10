# utils/confluence_client.py
import os
import json
from typing import Optional, Dict, Any

import requests
from rich import print

CONFLUENCE_BASE_URL = os.getenv("ALOE_CONFLUENCE_URL")
CONFLUENCE_USER = os.getenv("ALOE_CONFLUENCE_USER")
CONFLUENCE_TOKEN = os.getenv("ALOE_CONFLUENCE_TOKEN")
CONFLUENCE_PAGE_ID = os.getenv("ALOE_CONFLUENCE_PAGE_ID")

def _missing_conf() -> bool:
    if not all([CONFLUENCE_BASE_URL, CONFLUENCE_USER, CONFLUENCE_TOKEN, CONFLUENCE_PAGE_ID]):
        print("[red]Confluence configuration missing (ALOE_CONFLUENCE_URL / USER / TOKEN / PAGE_ID). "
              "Cannot update real Confluence page.[/red]")
        return True
    return False


def fetch_page(mode: str = "mock") -> Optional[Dict[str, Any]]:

    if mode == "mock":
        return None

    if _missing_conf():
        return None

    url = (
            CONFLUENCE_BASE_URL.rstrip("/")
            + f"/rest/api/content/{CONFLUENCE_PAGE_ID}"
            + "?expand=body.storage,version"
    )
    auth = (CONFLUENCE_USER, CONFLUENCE_TOKEN)
    headers = {"Accept": "application/json"}

    try:
        resp = requests.get(url, headers=headers, auth=auth)
    except Exception as e:
        print(f"[red]Error calling Confluence API (GET): {e}[/red]")
        return None

    if 200 <= resp.status_code < 300:
        try:
            return resp.json()
        except Exception as e:
            print(f"[red]Failed to parse Confluence GET response JSON: {e}[/red]")
            return None

    print(f"[red]Failed to fetch Confluence page: {resp.status_code} {resp.text}[/red]")
    return None


def update_confluence_page_with_markdown(
        markdown: str,
        mode: str = "mock"
) -> Optional[str]:

    if mode == "mock":
        print("[bold cyan][MOCK-X][/bold cyan] Would update Confluence page "
              f"[bold]{CONFLUENCE_PAGE_ID or '(unset)'}[/bold] with markdown section:")
        return None

    if _missing_conf():
        return None

    page = fetch_page(mode="real")
    if page is None:
        return None

    current_version = page.get("version", {}).get("number", 1)
    title = page.get("title")

    existing_body = page.get("body", {}).get("storage", {}).get("value", "")
    if not isinstance(existing_body, str):
        existing_body = ""

    escaped_markdown = (
        markdown
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    new_section = f"""
        <pre>
        {escaped_markdown}
        </pre>
        """

    new_body = existing_body + new_section

    url = CONFLUENCE_BASE_URL.rstrip("/") + f"/rest/api/content/{CONFLUENCE_PAGE_ID}"
    auth = (CONFLUENCE_USER, CONFLUENCE_TOKEN)
    headers = {"Content-Type": "application/json"}

    payload = {
        "id": CONFLUENCE_PAGE_ID,
        "type": "page",
        "title": title,
        "version": {
            "number": current_version + 1
        },
        "body": {
            "storage": {
                "value": new_body,
                "representation": "storage",
            }
        }
    }

    try:
        resp = requests.put(url, headers=headers, auth=auth, data=json.dumps(payload))
    except Exception as e:
        print(f"[red]Error calling Confluence API (PUT): {e}[/red]")
        return None

    if 200 <= resp.status_code < 300:
        data = resp.json()
        page_id = data.get("id")
        print(f"[bold green][REAL][/bold green] Updated Confluence page [bold]{page_id}[/bold]")
        return page_id

    print(f"[red]Failed to update Confluence page: {resp.status_code} {resp.text}[/red]")
    return None
