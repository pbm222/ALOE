# agents/executor.py

import time
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from rich import print

from utils.file_loader import load_triaged, load_feedback
from utils.metrics import LLM_USAGE, reset_llm_usage

from tools.log_preprocessor import run as preprocess_run
from agents.llm_triage import run as triage_run
from tools.summary import build_summary
from agents.llm_jira import run as jira_draft_run
from agents.llm_filter import run as filter_run
from agents.llm_confluence import run as conf_run
from agents.llm_orchestrator import plan_actions
from agents.llm_cluster_refiner import run as cluster_refine_run


JIRA_DRAFTS_PATH = Path("output") / "jira_drafts.json"
FILTER_SUGGESTIONS_PATH = Path("output") / "filter_suggestions.json"
JIRA_REVIEW_PATH = Path("output") / "jira_review.json"

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _safe_load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _hash_config(obj: Dict[str, Any]) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


def _normalize_json(obj: Any) -> Optional[str]:
    try:
        return json.dumps(obj, sort_keys=True, ensure_ascii=False)
    except Exception:
        return None


def _enrich_jira_drafts_result(
        base: Dict[str, Any],
        use_feedback: bool,
) -> Dict[str, Any]:
    data = _safe_load_json(JIRA_DRAFTS_PATH, {})
    drafts = data.get("drafts") or []
    if not isinstance(drafts, list):
        drafts = []

    sigs: List[str] = []
    for d in drafts:
        if isinstance(d, dict) and d.get("signature"):
            sigs.append(d["signature"])

    unique_sigs = sorted(set(sigs))
    base["signatures"] = unique_sigs
    base["unique_signature_count"] = len(unique_sigs)

    if use_feedback:
        fb = load_feedback()
        seen = {e.get("signature") for e in fb if isinstance(e, dict) and e.get("signature")}
        base["count_seen_before"] = len([s for s in unique_sigs if s in seen])
        base["count_new"] = len([s for s in unique_sigs if s not in seen])

    return base


def _enrich_filter_result(base: Dict[str, Any]) -> Dict[str, Any]:
    data = _safe_load_json(FILTER_SUGGESTIONS_PATH, {})
    suggestions = data.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = []

    clauses: List[str] = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        clause = s.get("es_filter_clause")
        norm = _normalize_json(clause)
        if norm:
            clauses.append(norm)

    unique = set(clauses)
    base["unique_count"] = len(unique)
    base["duplicate_count"] = max(0, len(clauses) - len(unique))
    return base


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

    actions.append({
        "agent": "JIRA_AGENT",
        "run": run_jira,
        "cluster_indices": None
    })

    actions.append({
        "agent": "FILTER_AGENT",
        "run": run_filters
    })

    actions.append({
        "agent": "CONFLUENCE_AGENT",
        "run": run_confluence,
    })

    plan = {
        "actions": actions,
        "global_policy": {
            "ticket_strategy": "baseline",
            "noise_handling": "basic_filters",
        },
        "reason": (
            "Static pipeline plan without LLM orchestration: "
            "create Jira drafts for high-priority internal errors; "
            "suggest filters for processed errors; update Confluence when something ran."
        ),
    }
    return plan


def execute_actions(
        plan: Dict[str, Any],
        jira_mode: str = "mock",
        mode: str = "orchestrator",
        use_feedback: bool = True,
) -> Dict[str, Any]:
    actions = plan.get("actions", [])
    results: Dict[str, Any] = {}
    errors: List[Dict[str, Any]] = []

    for act in actions:
        agent = act.get("agent")
        run_flag = bool(act.get("run", False))

        if not run_flag:
            print(f"[yellow]Skipping {agent} as per plan[/yellow]")
            continue

        try:
            if agent == "JIRA_AGENT":
                print("[bold green]Running Jira Ticketing LLM Agent (drafts)...[/bold green]")
                cluster_indices = act.get("cluster_indices")

                res = jira_draft_run(
                    cluster_indices=cluster_indices,
                    mode=mode
                )
                res = _enrich_jira_drafts_result(res, use_feedback=use_feedback)
                results["jira_drafts"] = res

            elif agent == "FILTER_AGENT":
                print("[bold green]Running Filter Generalization LLM Agent...[/bold green]")
                res = filter_run()
                res = _enrich_filter_result(res)
                results["filter_suggestions"] = res

            elif agent == "CONFLUENCE_AGENT":
                print("[bold green]Running Confluence Update LLM Agent (markdown draft)...[/bold green]")
                res = conf_run()
                results["confluence_draft"] = res

            else:
                print(f"[red]Unknown agent in plan: {agent}[/red]")
                errors.append({"agent": agent, "error": "unknown_agent"})

        except Exception as e:
            print(f"[red]{agent} failed: {e}[/red]")
            errors.append({"agent": agent, "error": str(e)})

    jira_review = _safe_load_json(JIRA_REVIEW_PATH, None)
    if isinstance(jira_review, dict):
        results["jira_review"] = jira_review

    results["errors"] = errors
    return results


def run_full_pipeline(
        source: str = "mock",
        jira_mode: str = "mock",
        mode: str = "orchestrator",
        use_feedback: bool = True,
        dataset_id: Optional[str] = None,
) -> Dict[str, Any]:
    reset_llm_usage()
    start_ts = time.time()
    start_iso = _now_iso()

    # record time window even if query hardcodes it
    time_window = {"gte": "now-1d", "lte": "now"}

    dataset_id = dataset_id or f"{source}-{datetime.utcnow().date().isoformat()}"
    run_config = {
        "mode": mode,
        "use_feedback": use_feedback,
        "source": source,
        "jira_mode": jira_mode,
        "dataset_id": dataset_id,
        "time_window": time_window,
    }
    config_hash = _hash_config(run_config)

    context: Dict[str, Any] = {}

    print("[bold green]Step 1: Log Preprocessor Agent[/bold green]")
    context = preprocess_run(context, source=source)

    log_count = len(context.get("raw_logs", []))
    print(f"[cyan]Preprocessed {log_count} logs[/cyan]")

    if log_count == 0:
        print("[yellow]No logs found. Stopping pipeline early.[/yellow]")
        end_ts = time.time()
        end_iso = _now_iso()
        return {
            "meta": {
                "mode": mode,
                "use_feedback": use_feedback,
                "dataset_id": dataset_id,
                "time_window": time_window,
                "config_hash": config_hash,
                "date": datetime.utcnow().date().isoformat(),
                "start_time": start_iso,
                "end_time": end_iso,
                "duration_seconds": end_ts - start_ts,
                "llm_usage": LLM_USAGE.to_dict(),
            },
            "summary": {"log_count": 0},
            "plan": None,
            "results": {"errors": [{"agent": "Pipeline", "error": "no_logs"}]},
        }

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
    exec_results = execute_actions(plan, jira_mode=jira_mode, mode=mode, use_feedback=use_feedback)

    end_ts = time.time()
    end_iso = _now_iso()
    duration_seconds = end_ts - start_ts

    meta = {
        "mode": mode,
        "use_feedback": use_feedback,
        "dataset_id": dataset_id,
        "time_window": time_window,
        "config_hash": config_hash,
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
