# agents/llm_confluence.py
import json
from pathlib import Path
from typing import Dict, Any

from tools.file_loader import load_triaged, load_jira_drafts, load_filter
from utils.llm import ask_json

OUT = Path("output") / "confluence_draft.md"

SYSTEM = """You are a technical writer generating a Confluence-ready markdown summary of a log review session.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.

Fields:
- markdown: the complete Confluence/Markdown document as a single string.

Your goals:
- Summarize important clusters (especially high severity or high priority internal errors).
- Mention any Jira ticket drafts that were generated.
- Include filter suggestions if they exist.
- The document must be clear, concise, and well-structured.
"""

USER_TEMPLATE = """You will receive:
- triaged clusters
- Jira ticket drafts (if any)
- filter suggestions (if any)

Include these sections as a table row:
- service name   (the affected service)
- short error summary    (usually the first line in stack trace)
- Jira ticket created (a link to Jira ticket; if no link just mention a summary  (e.g. MOCK-1 Document generation error))
- KQL exclusion filter    
- error date in human readable format (dd:MM:yyy:hh:ss)

Triaged clusters (JSON):
{triaged_json}

Jira drafts (JSON):
{jira_json}

Filter suggestions (JSON):
{filters_json}

Return JSON with this exact schema:
{{
  "markdown": "full markdown document as a string"
}}
"""

def run() -> Dict[str, Any]:

    triaged = load_triaged()
    jira = load_jira_drafts()
    filters_ = load_filter()

    user = USER_TEMPLATE.format(
        triaged_json=json.dumps(triaged, ensure_ascii=False, indent=2),
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

    return {"length": len(markdown), "output": str(OUT)}
