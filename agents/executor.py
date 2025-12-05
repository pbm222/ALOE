# agents/executor.py

import json
import time
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime
from rich import print

from agents.feedback import append_feedback
from utils.metrics import LLM_USAGE, reset_llm_usage
from utils.jira_client import create_jira_issue_from_draft

from agents.log_preprocessor import run as preprocess_run
from agents.llm_triage import run as triage_run
from agents.summary import build_summary, load_triaged
from agents.llm_jira import run as jira_draft_run
from agents.llm_filter import run as filter_run
from agents.llm_confluence import run as conf_run
from agents.llm_orchestrator import plan_actions

JIRA_DRAFTS_PATH = Path("output") / "jira_drafts.json"

def review_and_submit_jira_drafts(jira_mode: str = "mock") -> Dict[str, Any]:

    if not JIRA_DRAFTS_PATH.exists():
        print("[yellow]No jira_drafts.json found; skipping Jira submission.[/yellow]")
        return {"approved": 0, "rejected": 0, "submitted": 0, "skipped_all": False}

    data = json.loads(JIRA_DRAFTS_PATH.read_text(encoding="utf-8"))
    drafts: List[Dict[str, Any]] = data.get("drafts", [])

    if not drafts:
        print("[yellow]No Jira drafts to review.[/yellow]")
        return {"approved": 0, "rejected": 0, "submitted": 0, "skipped_all": False}

    print(f"[bold magenta]Reviewing {len(drafts)} Jira drafts...[/bold magenta]")

    approved_indices: List[int] = []
    rejected_indices: List[int] = []
    skipped_all = False

    for idx, draft in enumerate(drafts):
        d = draft.get("jira");
        summary = d.get("summary") or "(no summary)"
        service = d.get("service_name") or d.get("cluster", {}).get("service_name") or "(unknown service)"
        label = d.get("cluster", {}).get("triage", {}).get("label")
        signature = draft.get("cluster", {}).get("signature") or d.get("signature")

        print("\n----------------------------------------")
        print(f"[bold]Draft #{idx}[/bold]")
        print(f"Summary : {summary}")
        print(f"Service : {service}")
        print("----------------------------------------")

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

    submitted = 0
    if not skipped_all and approved_indices:
        print(f"\n[bold cyan]Submitting {len(approved_indices)} approved drafts to Jira (mode={jira_mode})...[/bold cyan]")
        for idx in approved_indices:
            draft = drafts[idx]
            _ = create_jira_issue_from_draft(draft, mode=jira_mode)
            submitted += 1

    return {
        "approved": len(approved_indices),
        "rejected": len(rejected_indices),
        "submitted": submitted,
        "skipped_all": skipped_all,
    }

def build_baseline_plan(summary: Dict[str, Any]) -> Dict[str, Any]:
    actions = []

    by_label = summary.get("by_label", {}) or {}
    by_priority = summary.get("by_priority", {}) or {}
    internal_high_count = summary.get("internal_high_count", 0) or 0

    # 1) Jira drafts: run if we have any high-priority internal errors
    run_jira = internal_high_count > 0
    actions.append({
        "agent": "JiraDrafts",
        "run": run_jira,
        # Let the Jira agent decide which clusters based on triage.
        "max_tickets": None,
        "min_severity": None,
        "min_confidence": None,
    })

    # 2) Filter suggestions: run if there is external_service noise
    external_count = by_label.get("external_service", 0) or 0
    run_filters = external_count > 0
    if run_filters:
        actions.append({
            "agent": "FilterSuggestions",
            "run": True,
            "for_labels": ["external_service"],
            "min_count": 50,   # baseline threshold
        })

    # 3) Confluence draft: always run to generate a summary
    actions.append({
        "agent": "ConfluenceDraft",
        "run": True,
        "include_sections": ["summary", "jira_links", "filters"],
    })

    plan = {
        "actions": actions,
        "global_policy": {
            "ticket_strategy": "baseline",
            "noise_handling": "basic_filters",
        },
        "reason": (
            "Static pipeline plan without LLM orchestration: "
            "always generate a Confluence summary, create Jira drafts "
            "for high-priority internal errors, and suggest filters for "
            "external_service noise."
        ),
    }
    return plan

def execute_actions(plan: Dict[str, Any], jira_mode: str = "mock") -> Dict[str, Any]:
    actions = plan.get("actions", [])
    results: Dict[str, Any] = {}

    jira_review_ran = False

    for act in actions:
        agent = act.get("agent")
        run_flag = act.get("run", False)

        if not run_flag:
            print(f"[yellow]Skipping {agent} as per orchestrator plan[/yellow]")
            continue

        if agent == "JiraDrafts":
            print("[bold green]Running Jira Ticketing LLM Agent (drafts)...[/bold green]")
            jira_review_ran = True
            cluster_indices = act.get("cluster_indices")

            res = jira_draft_run(
                cluster_indices=cluster_indices
            )
            results["jira_drafts"] = res

        elif agent == "FilterSuggestions":
            print("[bold green]Running Filter Generalization LLM Agent...[/bold green]")

            labels = act.get("for_labels")
            min_count = act.get("min_count")

            res = filter_run(
                for_labels=labels,
                min_count=min_count,
            )
            results["filter_suggestions"] = res

        elif agent == "ConfluenceDraft":
            print("[bold green]Running Confluence Update LLM Agent (markdown draft)...[/bold green]")

            sections = act.get("include_sections")

            res = conf_run(include_sections=sections)
            results["confluence_draft"] = res

        else:
            print(f"[red]Unknown agent in plan: {agent}[/red]")

    if jira_review_ran:
        print("\n[bold magenta]Starting interactive Jira draft review...[/bold magenta]")
        review_result = review_and_submit_jira_drafts(jira_mode=jira_mode)
        results["jira_review"] = review_result

    return results

def run_full_pipeline(source: str = "mock", jira_mode: str = "mock", mode: str = "orchestrator", use_feedback: bool = True) -> Dict[str, Any]:
    reset_llm_usage()
    start_ts = time.time()
    start_iso = datetime.utcnow().isoformat() + "Z"

    context: Dict[str, Any] = {}

    print("[bold green]Step 1: Log Preprocessor Agent[/bold green]")
    context = preprocess_run(context, source=source)

    log_count = len(context.get("raw_logs", []))
    print(f"[cyan]Preprocessed {log_count} logs[/cyan]")

    if log_count == 0:
        print("[yellow]No logs found. Stopping pipeline early.[/yellow]")
        return {"log_count": 0, "stopped": "no_logs"}

    print("[bold green]Step 2: LLM Triage Agent[/bold green]")
    triage_run()
    triaged_items = load_triaged()
    print(f"[cyan]Triaged {len(triaged_items)} clusters[/cyan]")

    print("[bold green]Step 3: Build summary for Orchestrator[/bold green]")
    summary = build_summary()
    print(f"[cyan]Summary: {summary}[/cyan]")

    if mode == "orchestrator":
        print("[bold green]Step 4: LLM Orchestrator Agent[/bold green]")
        plan = plan_actions(summary, triaged_items, use_feedback=use_feedback)
        print(f"[cyan]Orchestrator plan: {plan}[/cyan]")
    else:
        print("[bold green]Step 4: Baseline pipeline plan (no orchestrator)[/bold green]")
        plan = build_baseline_plan(summary)
        print(f"[cyan]Baseline plan: {plan}[/cyan]")

    print("[bold green]Step 5: Executing plan[/bold green]")
    exec_results = execute_actions(plan, jira_mode=jira_mode)

    end_ts = time.time()
    end_iso = datetime.utcnow().isoformat() + "Z"
    duration_seconds = end_ts - start_ts

    meta = {
        "mode": mode,
        "date": datetime.utcnow().date().isoformat(),
        "start_time": start_iso,
        "end_time": end_iso,
        "duration_seconds": duration_seconds,
        "llm_usage": LLM_USAGE.to_dict(),
    }

    return {
        "meta": meta,
        "summary": summary,
        "plan": plan,
        "results": exec_results,
    }
