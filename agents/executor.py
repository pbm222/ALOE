# agents/executor.py

from typing import Dict, Any, List
from rich import print

# Tool agents / LLM agents
from agents.log_preprocessor import run as preprocess_run
from agents.llm_triage import run as triage_run
from agents.summary import build_summary, load_triaged
from agents.jira_drafts import run as jira_draft_run
from agents.filter_suggestions import run as filter_run
from agents.confluence_draft import run as conf_run
from agents.llm_orchestrator import plan_actions


# ---------------------------------------------------------
# EXECUTE SINGLE ACTION DYNAMICALLY (LLM-DRIVEN)
# ---------------------------------------------------------

def execute_actions(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute actions chosen by LLM orchestrator.
    Supports dynamic agent parameters.
    """
    actions = plan.get("actions", [])
    results: Dict[str, Any] = {}

    for act in actions:
        agent = act.get("agent")
        run_flag = act.get("run", False)

        if not run_flag:
            print(f"[yellow]Skipping {agent} as per orchestrator plan[/yellow]")
            continue

        # -----------------------------------------
        # JiraDrafts Agent (LLM Ticket Generation)
        # -----------------------------------------
        if agent == "JiraDrafts":
            print("[bold green]Running Jira Ticketing LLM Agent (drafts)...[/bold green]")

            # Dynamic policy parameters
            max_tickets = act.get("max_tickets")
            min_severity = act.get("min_severity")
            min_confidence = act.get("min_confidence")

            res = jira_draft_run(
                max_tickets=max_tickets,
                min_severity=min_severity,
                min_confidence=min_confidence,
            )
            results["jira_drafts"] = res

        # -----------------------------------------
        # Filter Suggestions Agent
        # -----------------------------------------
        elif agent == "FilterSuggestions":
            print("[bold green]Running Filter Generalization LLM Agent...[/bold green]")

            labels = act.get("for_labels")
            min_count = act.get("min_count")

            res = filter_run(
                for_labels=labels,
                min_count=min_count,
            )
            results["filter_suggestions"] = res

        # -----------------------------------------
        # Confluence Draft Agent
        # -----------------------------------------
        elif agent == "ConfluenceDraft":
            print("[bold green]Running Confluence Update LLM Agent (markdown draft)...[/bold green]")

            sections = act.get("include_sections")

            res = conf_run(include_sections=sections)
            results["confluence_draft"] = res

        else:
            print(f"[red]Unknown agent in plan: {agent}[/red]")

    return results


# ---------------------------------------------------------
# FULL PIPELINE EXECUTION
# ---------------------------------------------------------

def run_full_pipeline() -> Dict[str, Any]:
    """
    Full multi-agent system execution:
    1. Preprocess logs
    2. LLM triage clusters
    3. Build summary
    4. Orchestrator decides next actions
    5. Execute selected agents
    """
    context: Dict[str, Any] = {}

    # -----------------------------
    # Step 1: Preprocess logs
    # -----------------------------
    print("[bold green]Step 1: Log Preprocessor Agent[/bold green]")
    context = preprocess_run(context)

    log_count = len(context.get("raw_logs", []))
    print(f"[cyan]Preprocessed {log_count} logs[/cyan]")

    if log_count == 0:
        print("[yellow]No logs found. Stopping pipeline early.[/yellow]")
        return {"log_count": 0, "stopped": "no_logs"}

    # -----------------------------
    # Step 2: LLM Triage
    # -----------------------------
    print("[bold green]Step 2: LLM Triage Agent[/bold green]")
    triage_run()
    triaged_items = load_triaged()
    print(f"[cyan]Triaged {len(triaged_items)} clusters[/cyan]")

    # -----------------------------
    # Step 3: Build summary
    # -----------------------------
    print("[bold green]Step 3: Build summary for Orchestrator[/bold green]")
    summary = build_summary()
    print(f"[cyan]Summary: {summary}[/cyan]")

    # -----------------------------
    # Step 4: Orchestrator LLM
    # -----------------------------
    print("[bold green]Step 4: LLM Orchestrator Agent[/bold green]")
    plan = plan_actions(summary)
    print(f"[cyan]Orchestrator plan: {plan}[/cyan]")

    # -----------------------------
    # Step 5: Execute plan
    # -----------------------------
    print("[bold green]Step 5: Executing plan[/bold green]")
    exec_results = execute_actions(plan)

    # -----------------------------
    # Return final state
    # -----------------------------
    return {
        "summary": summary,
        "plan": plan,
        "results": exec_results,
    }
