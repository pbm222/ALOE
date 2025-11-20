# agents/llm_confluence.py
import json
from pathlib import Path
from typing import Dict, Any, List
from utils.llm import ask_json

TRIAGED = Path("output") / "triaged_llm.json"
DRAFTS = Path("output") / "jira_drafts.json"
OUT = Path("output") / "confluence_draft.md"

SYSTEM = """You are a technical writer preparing a weekly log review summary for Confluence.
Write concise markdown with:
- overview counts (clusters, internal tickets)
- a short bullet list of the tickets with one line context each
- a final 'filter updates' placeholder.
You MUST respond with ONLY a JSON object: { "markdown": "..." }."""

# note the doubled {{ }} to escape literal braces for .format()
USER_TEMPLATE = """Inputs:
triaged_items_count: {t_count}
jira_drafts: {drafts_json}

Return JSON:
{{ "markdown": "..." }}"""

def run() -> Dict[str, Any]:
    tri = json.loads(TRIAGED.read_text(encoding="utf-8"))
    t_items = tri.get("items", [])
    j = json.loads(DRAFTS.read_text(encoding="utf-8"))
    drafts: List[Dict[str, Any]] = j.get("drafts", [])

    user = USER_TEMPLATE.format(
        t_count=len(t_items),
        drafts_json=json.dumps(drafts, ensure_ascii=False, indent=2),
    )
    out = ask_json(SYSTEM, user)
    md = out.get("markdown", "# Log Review\n\n(No content)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(md, encoding="utf-8")
    return {"length": len(md), "output": str(OUT)}
