# app.py
import argparse
from rich import print

from agents.log_preprocessor import run as preprocess_run
from agents.llm_triage import run as triage_run
from agents.llm_jira import run as jira_draft_run
from agents.llm_filter import run as filter_run
from agents.llm_confluence import run as conf_run
from agents.executor import run_full_pipeline
from agents.feedback_review import run as feedback_review_run

def main():
    parser = argparse.ArgumentParser(description="ALOE - Adaptive Log Orchestration Engine")
    parser.add_argument(
        "command",
        choices=["preprocess", "triage", "jira_drafts", "filter_suggestions",
             "conf_draft", "run_all", "review_jira"],
    )

    parser.add_argument(
        "--source",
        choices=["mock", "elastic"],
        default="mock",
        help="Log source: 'mock' (file) or 'elastic' (Elasticsearch API)",
    )

    args = parser.parse_args()

    if args.command == "preprocess":
        print("[bold green]Log Preprocessor Agent...[/bold green]")
        ctx = {}
        ctx = preprocess_run(ctx, source=args.source)

    elif args.command == "triage":
        print("[bold green]LLM Triage Agent...[/bold green]")
        res = triage_run()
        print(f"[bold cyan]Triaged {res['count']} clusters → output/triaged_llm.json[/bold cyan]")

    elif args.command == "jira_drafts":
        print("[bold green]Jira Ticketing LLM Agent (drafts)...[/bold green]")
        res = jira_draft_run()
        print(f"[bold cyan]Drafted {res['count']} tickets → output/jira_drafts.json[/bold cyan]")

    elif args.command == "filter_suggestions":
        print("[bold green]Filter Generalization LLM Agent...[/bold green]")
        res = filter_run()
        print(f"[bold cyan]Created {res['count']} suggestions → output/filter_suggestions.json[/bold cyan]")

    elif args.command == "conf_draft":
        print("[bold green]Confluence Update LLM Agent (markdown draft)...[/bold green]")
        res = conf_run()
        print(f"[bold cyan]Wrote markdown → output/confluence_draft.md[/bold cyan]")

    elif args.command == "review_jira":
        print("[bold green]Interactive Jira feedback review...[/bold green]")
        res = feedback_review_run()
        print(f"[bold cyan]Reviewed {res['reviewed']} drafts, "
          f"wrote {res['written_feedback']} feedback entries → output/feedback.json[/bold cyan]")

    elif args.command == "run_all":
        print("[bold magenta]Running full ALOE pipeline with LLM orchestration...[/bold magenta]")
        res = run_full_pipeline(source=args.source)
        print("[bold magenta]Pipeline finished.[/bold magenta]")
        print(res)

if __name__ == "__main__":
    main()
