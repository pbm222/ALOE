# agents/llm_triage.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List

from utils.file_loader import load_refined_clusters
from utils.llm import ask_json
import re
import hashlib

TRIAGED_LOGS_OUTPUT = Path("output") / "triaged_logs.json"

# None = triage all clusters
TRIAGE_TOP_N: int | None = None

# How many clusters per LLM call
BATCH_SIZE: int = 10


SYSTEM = """You are a senior backend engineer helping with log triage in an enterprise web application.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.

You will receive a LIST of log clusters. For EACH cluster, decide:
- label: one of "timeout", "external_service", "internal_error", or "noise"
- priority: "high", "medium", or "low" from the perspective of what is worth developer attention
- severity: "low", "medium", or "high" impact if this issue is real
- confidence: 0.0–1.0, how sure you are about label and priority
- reason: 1–3 sentences explaining your judgement
- service: echo back the exact service name as provided in the input cluster

Use these domain heuristics:
- Errors in core business flows (e.g. document generation, migrated policy mapping, payment flow) tend to be higher priority.
- Rare but severe exceptions (NullPointerException, mapping failures) are usually "internal_error" with at least medium priority.
- Repeated noisy logs, debug messages, or non-fatal warnings are "noise" with low priority.
- Integration failures with external systems are "external_service"; priority depends on how critical the integration is.
- Timeouts and transient network errors are "timeout"; usually low or medium priority unless they happen very often.
- Polaris 'No output' errors are "external_error".
- Error in runtime-service (frontend service) is usually connected with a backend error, so no need to check both, but need to identify the one from backend that was propagated to frontend.

Always consider the 'count' field (how many times this cluster occurred) when deciding priority and severity.

You must return a single JSON object with key "items".
Each element in "items" must correspond to one input cluster and contain:
- "idx": the same idx value as in the input cluster
- "triage": an object with keys:
    - "label": one of "timeout", "external_service", "internal_error", "noise"
    - "service": the exact service name as provided in the input cluster
    - "priority": "high", "medium", or "low"
    - "severity": "high", "medium", or "low"
    - "confidence": a float between 0.0 and 1.0
    - "reason": short explanation (1–3 sentences)
"""

USER_TEMPLATE = """You will receive multiple log clusters to triage.

Each cluster has:
- idx: numeric cluster index
- service: container or service name
- java_class: Java class or component name
- message: representative log message
- log: a stack trace or log excerpt of the error
- count: number of occurrences

Clusters:
{clusters_json}

Triage ALL clusters and return a single JSON object with key "items", as described in the system prompt.
"""


def make_cluster_signature(java_class: str | None, message: str | None) -> str:
    base = (java_class or "") + "|" + (message or "")
    normalized = re.sub(r"\d+", "#", base)
    h = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return h


def _chunked(seq: List[Any], size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def run() -> Dict[str, Any]:
    clusters: List[Dict[str, Any]] = load_refined_clusters()

    if TRIAGE_TOP_N is not None:
        clusters = clusters[:TRIAGE_TOP_N]

    if not clusters:
        TRIAGED_LOGS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        TRIAGED_LOGS_OUTPUT.write_text(
            json.dumps({"items": []}, indent=2),
            encoding="utf-8",
        )
        return {"count": 0, "output": str(TRIAGED_LOGS_OUTPUT)}

    compact_clusters: List[Dict[str, Any]] = []
    for i, c in enumerate(clusters):
        idx = c.get("idx")
        if idx is None:
            idx = i

        sample = c.get("sample") or {}
        sample_source = sample.get("_source") or sample

        service = (
                sample_source.get("AthenaServiceName")
                or sample_source.get("service")
                or c.get("athena_service")
        )
        full_log = sample_source.get("log") or c.get("message") or ""

        compact_clusters.append(
            {
                "idx": idx,
                "service": service,
                "java_class": c.get("java_class"),
                "message": c.get("message"),
                "log": full_log,
                "count": c.get("count"),
            }
        )

    triage_by_idx: Dict[int, Dict[str, Any]] = {}

    for batch in _chunked(compact_clusters, BATCH_SIZE):
        user = USER_TEMPLATE.format(
            clusters_json=json.dumps(batch, ensure_ascii=False, indent=2)
        )

        out = ask_json(SYSTEM, user)

        if not isinstance(out, dict):
            continue

        triaged_items = out.get("items") or []
        for item in triaged_items:
            if not isinstance(item, dict):
                continue
            idx = item.get("idx")
            if idx is None:
                continue

            triage = item.get("triage")
            if not isinstance(triage, dict) or not triage:
                triage = {
                    "label": item.get("label"),
                    "service": item.get("service"),
                    "priority": item.get("priority"),
                    "severity": item.get("severity"),
                    "confidence": item.get("confidence"),
                    "reason": item.get("reason"),
                }

            triage_by_idx[int(idx)] = triage

    results: List[Dict[str, Any]] = []

    for i, c in enumerate(clusters):
        idx = c.get("idx")
        if idx is None:
            idx = i

        triage = triage_by_idx.get(int(idx), {}) or {}

        sample = c.get("sample") or {}
        sample_source = sample.get("raw") or sample
        service = (
                sample_source.get("AthenaServiceName")
                or sample_source.get("service")
                or c.get("athena_service")
        )

        full_log = sample_source.get("log", "") or ""
        stack_lines = full_log.splitlines()
        stack_excerpt = "\n".join(stack_lines[:15])

        java_class = c.get("java_class")
        message = c.get("message")
        signature = make_cluster_signature(java_class, message)

        if "service" not in triage or triage.get("service") is None:
            triage["service"] = service

        results.append(
            {
                "idx": idx,
                "signature": signature,
                "service": service,
                "java_class": java_class,
                "message": message,
                "count": c.get("count"),
                "stack_excerpt": stack_excerpt,
                "triage": triage,
            }
        )

    TRIAGED_LOGS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    TRIAGED_LOGS_OUTPUT.write_text(
        json.dumps({"items": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {"count": len(results), "output": str(TRIAGED_LOGS_OUTPUT)}
