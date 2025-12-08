# agents/llm_confluence.py
import json
from pathlib import Path
from typing import Dict, Any

from tools.file_loader import load_triaged, load_jira_drafts, load_filter
from utils.confluence_client import update_confluence_page_with_markdown
from utils.llm import ask_json

OUT = Path("output") / "confluence_draft.md"

SYSTEM = """You are an assistant that writes concise Confluence-ready markdown reports
summarizing an automated log review session in an enterprise Java backend.

You MUST respond with ONLY a single valid JSON object.
No markdown fences, no backticks, no extra text.

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

Return JSON with this exact schema:
{{
  "markdown": "full markdown document as a string"
}}
"""

def run() -> Dict[str, Any]:

    jira = load_jira_drafts()
    filters_ = load_filter()

    user = USER_TEMPLATE.format(
        jira_json=json.dumps(jira, ensure_ascii=False, indent=2),
        filters_json=json.dumps(filters_, ensure_ascii=False, indent=2),
    )

    out = ask_json(SYSTEM, user)

    if not isinstance(out, dict):
        markdown = "# Log Review Summary\n\n(LLM returned invalid response.)"
    else:
        markdown = out.get("markdown") or "# Log Review Summary\n\n(No content generated.)"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(markdown, encoding="utf-8")

    update_confluence_page_with_markdown(markdown)

    return {"length": len(markdown), "output": str(OUT)}
