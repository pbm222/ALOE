# agents/llm_confluence.py
import json
from pathlib import Path
from typing import Dict, Any

from utils.file_loader import load_jira_drafts, load_filter
from utils.confluence_client import update_confluence_page_with_markdown
from utils.llm import ask_json

OUT = Path("output") / "confluence_draft.md"

SYSTEM = """You are an assistant that writes concise Confluence-ready markdown reports
summarizing an automated log review session in an enterprise Java backend.

You MUST respond with ONLY a single valid JSON object.
No markdown fences, no backticks, no extra text.

CRITICAL OUTPUT RULES:
- You MUST return ONLY a single valid JSON object.
- The JSON MUST have exactly this schema:
  {"markdown": "<string>"}
- The markdown MUST be a single JSON string. You MUST escape newlines as \\n.
  (Do NOT put literal newlines inside the JSON string.)
  
The JSON MUST have exactly this schema:
{
  "markdown": "Confluence-ready markdown content as a single string"
}

The "markdown" field must contain ONLY the markdown content of the report.
Do NOT include any other top-level keys.
Keep the report reasonably short:
- At most ~30 lines of markdown.
- Tables should have at most 10 rows.

You will receive:
- Jira ticket drafts (if any)
- filter suggestions (if any)

Include these sections as ONE table row with these columns :
- service name   (the affected service)
- short error summary    (usually the first line in stack trace)
- Jira ticket created (a link to Jira ticket; if no link just mention a summary  (e.g. MOCK-1 Document generation error))
- KQL exclusion filter  (e.g. not log: "XXX")
- error count ('count' number from jira json)

DO NOT include any headings, titles, or description text into the markdown. 

"""

USER_TEMPLATE = """

Jira drafts (JSON):
{jira_json}

Produced KQL (JSON):
{filters_json}

Return ONLY:
{{"markdown":"<markdown table as a JSON string with \\n between lines>"}}
"""

def _salvage_markdown_from_raw(raw: str) -> str:
    if not raw:
        return ""

    text = raw.strip()

    # Case A: Groq returned something JSON-ish but invalid due to raw newlines inside quotes.
    # Try to extract the main content between the first quote after { and the last quote before }.
    if text.startswith("{") and text.endswith("}"):
        # If it returned {"something|...": "...."} (key is the table), salvage the key
        try:
            obj = json.loads(text)
            # If valid JSON but wrong schema:
            if isinstance(obj, dict) and "markdown" not in obj and len(obj) == 1:
                only_key = next(iter(obj.keys()))
                if "|" in only_key:
                    return only_key
        except Exception:
            pass
        # Heuristic salvage: if it contains pipes and looks like a table, pull that part out.
        # Common pattern in your raw output: {"<table>"} or {"...|...\n..."}
        if "|" in text:
            # remove outer braces
            inner = text[1:-1].strip()

            # If it starts with a quote, strip quotes
            if inner.startswith('"') and inner.endswith('"'):
                inner = inner[1:-1]

            # Replace escaped sequences if they exist, but also accept literal newlines.
            return inner

    # Case B: not JSON at all; just return it as markdown.
    return text


def run() -> Dict[str, Any]:

    jira = load_jira_drafts()
    filters_ = load_filter()

    user = USER_TEMPLATE.format(
        jira_json=json.dumps(jira, ensure_ascii=False, indent=2),
        filters_json=json.dumps(filters_, ensure_ascii=False, indent=2),
    )

    out = ask_json(SYSTEM, user)

    markdown = ""
    if isinstance(out, dict) and out.get("markdown"):
        markdown = out.get("markdown") or ""
    elif isinstance(out, dict) and out.get("_raw"):
        markdown = _salvage_markdown_from_raw(out.get("_raw") or "")
    else:
        markdown = ""

    if not markdown.strip():
        markdown = "| service name | short error summary | Jira ticket created | KQL exclusion filter | error count |\n| --- | --- | --- | --- | --- |"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(markdown, encoding="utf-8")

    update_confluence_page_with_markdown(markdown)

    return {"length": len(markdown), "output": str(OUT)}
