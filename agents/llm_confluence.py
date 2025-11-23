# agents/llm_confluence.py
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from utils.llm import ask_json

TRIAGED = Path("output") / "triaged_llm.json"
JIRA = Path("output") / "jira_drafts.json"
FILTERS = Path("output") / "filter_suggestions.json"
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
- a list of sections that should be included

Include only the sections requested in the 'sections' list. Typical sections:
- summary       (overview of the log review)
- jira_links    (description of proposed Jira tickets)
- filters       (description of suggested KQL/regex filters)

Sections to include:
{sections}

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


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def run(include_sections: Optional[List[str]] = None) -> Dict[str, Any]:
    if include_sections is None:
        include_sections = ["summary", "jira_links", "filters"]

    triaged = _load(TRIAGED, {}).get("items", [])
    jira = _load(JIRA, {}).get("drafts", [])
    filters_ = _load(FILTERS, {}).get("suggestions", [])

    user = USER_TEMPLATE.format(
        sections=json.dumps(include_sections, ensure_ascii=False),
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
