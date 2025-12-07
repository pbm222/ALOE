# agents/feedback_review.py

from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path
import json

from rich import print
from tools.file_loader import load_jira_drafts, load_feedback

FEEDBACK = Path("output") / "feedback.json"

def save_feedback(entries: List[Dict[str, Any]]) -> None:
    FEEDBACK.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK.write_text(json.dumps(entries, indent=2), encoding="utf-8")

def append_feedback(entry: Dict[str, Any]) -> None:
    entries = load_feedback()
    entries.append(entry)
    save_feedback(entries)

def run() -> Dict[str, Any]:
    drafts = load_jira_drafts()

    if not drafts:
        print("[yellow]No drafts found in jira_drafts.json[/yellow]")
        return {"reviewed": 0, "written_feedback": 0}

    approved_indices: List[int] = []
    rejected_indices: List[int] = []
    skipped_all = False

    for d in drafts:
        idx = d.get("idx")
        signature = d.get("signature")
        summary = d.get("summary") or "(no summary)"
        service = d.get("service_name") or d.get("cluster", {}).get("service_name") or "(unknown service)"
        java_class = d.get("java_class")
        label = d.get("cluster", {}).get("triage", {}).get("label")
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

        while True:
            choice = input("Approve (A) / Reject (R) / Skip all (S): ").strip().lower()
            if choice in ("a", "approve"):
                approved_indices.append(idx)

                append_feedback(
                    {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "signature": signature,
                    "decision": "approved",
                    "source": "jira_review",
                    "summary": summary,
                    "service": service,
                    }
                )

                break

            elif choice in ("r", "reject"):
                rejected_indices.append(idx)

                append_feedback(
                    {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "signature": signature,
                    "decision": "rejected",
                    "source": "jira_review",
                    "summary": summary,
                    "service": service,
                    "label": label,
                    }
                )

                break

            elif choice in ("s", "skip", "skip all"):
                skipped_all = True
                print("[yellow]Skipping all remaining drafts. No Jira tickets will be created.[/yellow]")
                break
            else:
                print("Please enter A, R, or S.")

        if skipped_all:
            break

    print(f"\n[bold]Review session finished.[/bold] "
          f"Approved={len(approved_indices)}, Rejected={len(rejected_indices)}, Skipped all={skipped_all}")
    return {
        "approved": len(approved_indices),
        "rejected": len(rejected_indices),
        "skipped_all": skipped_all,
}