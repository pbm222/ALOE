# agents/executor.py

from typing import Dict, Any
from rich import print

from agents.log_preprocessor import run as preprocess_run
from agents.llm_triage import run as triage_run
from agents.summary import build_summary, load_triaged
from agents.llm_jira import run as jira_draft_run
from agents.llm_filter import run as filter_run
from agents.llm_confluence import run as conf_run
from agents.llm_orchestrator import plan_actions

def execute_actions(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute actions chosen by LLM orchestrator.
    """
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
            cluster_indices = act.get("cluster_indices") or []
            res = jira_draft_run(cluster_indices=cluster_indices)
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

    return results


def run_full_pipeline(source: str = "mock") -> Dict[str, Any]:
    """
    Full multi-agent system execution:
    1. Preprocess logs
    2. LLM triage clusters
    3. Build summary
    4. Orchestrator decides next actions
    5. Execute selected agents
    """
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

    print("[bold green]Step 4: LLM Orchestrator Agent[/bold green]")
    plan = plan_actions(summary, triaged_items)
    print(f"[cyan]Orchestrator plan: {plan}[/cyan]")

    print("[bold green]Step 5: Executing plan[/bold green]")
    exec_results = execute_actions(plan)

    return {
        "summary": summary,
        "plan": plan,
        "results": exec_results,
    }
