# agents/feedback_review.py
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from rich import print
from agents.feedback import append_feedback

JIRA_DRAFTS_PATH = Path("output") / "jira_drafts.json"


def _load_jira_drafts() -> Dict[str, Any]:
    if not JIRA_DRAFTS_PATH.exists():
        raise FileNotFoundError(f"{JIRA_DRAFTS_PATH} not found. Run jira_drafts first.")
    return json.loads(JIRA_DRAFTS_PATH.read_text(encoding="utf-8"))


def run() -> Dict[str, Any]:
    """
    Interactive review of Jira drafts:
    - shows each draft
    - asks for approval (y) / disapproval (n) / skip (s) / quit (q)
    - writes feedback.json entries keyed by cluster signature
    """
    data = _load_jira_drafts()
    drafts: List[Dict[str, Any]] = data.get("drafts", [])

    if not drafts:
        print("[yellow]No drafts found in jira_drafts.json[/yellow]")
        return {"reviewed": 0, "written_feedback": 0}

    reviewed = 0
    written = 0

    for d in drafts:
        idx = d.get("idx")
        signature = d.get("signature")
        service = d.get("service")
        java_class = d.get("java_class")
        triage = d.get("triage", {})
        jira = d.get("jira", {})

        print("\n" + "-" * 80)
        print(f"[bold]Draft for cluster idx={idx}, signature={signature}[/bold]")
        print(f"[cyan]Service:[/cyan] {service}")
        print(f"[cyan]Class:[/cyan] {java_class}")
        print(f"[cyan]Triage:[/cyan] label={triage.get('label')}, "
              f"priority={triage.get('priority')}, severity={triage.get('severity')}, "
              f"confidence={triage.get('confidence')}")
        print("\n[bold]Jira summary:[/bold]")
        print(jira.get("summary", "(no summary)"))
        print("\n[bold]Issue description (truncated):[/bold]")
        desc = jira.get("issue_description", "")
        if len(desc) > 600:
            print(desc[:600] + " ... [truncated]")
        else:
            print(desc)

        print("\n[y] approve  [n] reject  [s] skip  [q] quit")
        choice = input("Your choice: ").strip().lower()

        if choice == "q":
            break
        if choice == "s":
            continue

        if choice not in ("y", "n"):
            print("[yellow]Invalid choice, skipping.[/yellow]")
            continue

        reviewed += 1

        decision = "approved" if choice == "y" else "rejected"
        reason = input("Optional short reason/comment (enter to skip): ").strip()

        feedback_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "signature": signature,
            "idx": idx,
            "service": service,
            "java_class": java_class,
            "triage": triage,
            "decision": decision,
            "reason": reason or None,
        }
        append_feedback(feedback_entry)
        written += 1
        print(f"[green]Recorded feedback: {decision}[/green]")

    print(f"\n[bold]Review session finished.[/bold] "
          f"Reviewed={reviewed}, feedback entries written={written}")
    return {"reviewed": reviewed, "written_feedback": written}
