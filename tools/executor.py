# agents/executor.py

import time
from typing import Dict, Any, List
from datetime import datetime
from rich import print

from tools.file_loader import load_triaged
from utils.metrics import LLM_USAGE, reset_llm_usage

from tools.log_preprocessor import run as preprocess_run
from agents.llm_triage import run as triage_run
from tools.summary import build_summary
from agents.llm_jira import run as jira_draft_run
from agents.llm_filter import run as filter_run
from agents.llm_confluence import run as conf_run
from agents.llm_orchestrator import plan_actions
from agents.llm_cluster_refiner import run as cluster_refine_run

def build_baseline_plan(summary: Dict[str, Any]) -> Dict[str, Any]:
    actions = []

    by_label = summary.get("by_label", {}) or {}
    internal_high_count = summary.get("internal_high_count", 0) or 0
    triaged_count = summary.get("triaged_cluster_count", 0) or 0

    has_external = by_label.get("external_service", 0) > 0
    has_noise = by_label.get("noise", 0) > 0

    run_jira = internal_high_count > 0
    run_filters = triaged_count > 0
    run_confluence = run_jira or run_filters

    include_sections = ["summary"]
    if run_jira:
        include_sections.append("jira_links")
    if run_filters or has_external or has_noise:
        include_sections.append("filters")

    run_jira = internal_high_count > 0
    actions.append({
        "agent": "JiraDrafts",
        "run": run_jira,
        "cluster_indices": None
    })

    actions.append({
        "agent": "FilterSuggestions",
        "run": run_filters
    })

    actions.append({
        "agent": "ConfluenceDraft",
        "run": run_confluence,
        "include_sections": include_sections,
    })

    plan = {
        "actions": actions,
        "global_policy": {
            "ticket_strategy": "baseline",
            "noise_handling": "basic_filters",
        },
        "reason": (
            "Static pipeline plan without LLM orchestration: "
            "always generate a KQL, Confluence summary, create Jira drafts "
            "for high-priority internal errors, and suggest filters for "
            "external_service noise."
        ),
    }
    return plan

def execute_actions(plan: Dict[str, Any], jira_mode: str = "mock", mode: str = "orchestrator") -> Dict[str, Any]:
    actions = plan.get("actions", [])
    results: Dict[str, Any] = {}

    for act in actions:
        agent = act.get("agent")
        run_flag = act.get("run", False)

        if not run_flag:
            print(f"[yellow]Skipping {agent} as per orchestrator plan[/yellow]")
            continue

        if agent == "JiraDrafts":
            print("[bold green]Running Jira Ticketing LLM Agent (drafts)...[/bold green]")
            cluster_indices = act.get("cluster_indices")

            res = jira_draft_run(
                cluster_indices=cluster_indices,
                mode=mode
            )
            results["jira_drafts"] = res

        elif agent == "FilterSuggestions":
            print("[bold green]Running Filter Generalization LLM Agent...[/bold green]")

            res = filter_run()
            results["filter_suggestions"] = res

        elif agent == "ConfluenceDraft":
            print("[bold green]Running Confluence Update LLM Agent (markdown draft)...[/bold green]")

            res = conf_run()
            results["confluence_draft"] = res

        else:
            print(f"[red]Unknown agent in plan: {agent}[/red]")


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

    print("[bold green]Step 1b: LLM Cluster Refinement Agent[/bold green]")
    refine_res = cluster_refine_run()
    print(f"[cyan]Refined clusters count: {refine_res.get('count')}[/cyan]")

    print("[bold green]Step 2: LLM Triage Agent[/bold green]")
    triage_run()
    triaged_items = load_triaged()
    print(f"[cyan]Triaged {len(triaged_items)} clusters[/cyan]")

    print("[bold green]Step 3: Build summary [/bold green]")
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
    exec_results = execute_actions(plan, jira_mode=jira_mode, mode=mode)

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
