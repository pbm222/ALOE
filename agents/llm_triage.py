# agents/llm_triage.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List
from utils.llm import ask_json
import re
import hashlib

CLUSTERS = Path("output") / "clusters.json"
OUT = Path("output") / "triaged_llm.json"

# limit for cost-control
TRIAGE_TOP_N = 2

SYSTEM = """You are a senior backend engineer helping with log triage in an enterprise web application.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.

For each log cluster, decide:
- label: one of "timeout", "external_service", "internal_error", or "noise"
- priority: "high", "medium", or "low" from the perspective of what is worth developer attention
- severity: "low", "medium", or "high" impact if this issue is real
- confidence: 0.0–1.0, how sure you are about label and priority
- reason: 1–3 sentences explaining your judgement

Use these domain heuristics:
- Errors in core business flows (e.g. document generation, migrated policy mapping, payment flow) tend to be higher priority.
- Rare but severe exceptions (NullPointerException, mapping failures) are usually "internal_error" with at least medium priority.
- Repeated noisy logs, debug messages, or non-fatal warnings are "noise" with low priority.
- Integration failures with external systems are "external_service"; priority depends on how critical the integration is.
- Timeouts and transient network errors are "timeout"; usually low or medium priority unless they happen very often.

Always consider the 'count' field (how many times this cluster occurred) when deciding priority and severity.
"""

USER_TEMPLATE = """You will receive one log cluster at a time in JSON.
Fields:
- java_class: Java class or component name
- message: representative log message
- count: number of occurrences
- sample: one example item (may include timestamp, trace)

Return JSON with this exact schema:
{{
  "label": "timeout|external_service|internal_error|noise",
  "priority": "high|medium|low",
  "severity": "high|medium|low",
  "confidence": 0.0,
  "reason": "short explanation"
}}

Cluster:
```json
{cluster_json}
```"""

def make_cluster_signature(java_class: str | None, message: str | None) -> str:
    base = (java_class or "") + "|" + (message or "")
    normalized = re.sub(r"\d+", "#", base)
    h = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return h


def run() -> Dict[str, Any]:

    data = json.loads(CLUSTERS.read_text(encoding="utf-8"))
    clusters: List[Dict[str, Any]] = data.get("clusters", [])
    # limit for now (top N clusters by frequency)
    clusters = clusters[:TRIAGE_TOP_N]

    results: List[Dict[str, Any]] = []

    for idx, c in enumerate(clusters):
        user = USER_TEMPLATE.format(cluster_json=json.dumps(c, ensure_ascii=False, indent=2))
        out = ask_json(SYSTEM, user)

        service = c.get("service") or c.get("athena_service")
        sample = c.get("sample") or {}
        sample_source = sample.get("_source") or sample
        full_log = sample_source.get("log", "")

        stack_lines = full_log.splitlines()
        stack_excerpt = "\n".join(stack_lines[:15])

        java_class = c.get("java_class")
        message = c.get("message")
        signature = make_cluster_signature(java_class, message)

        results.append({
            "idx": idx,
            "signature": signature,
            "service": service,
            "java_class": c.get("java_class"),
            "message": c.get("message"),
            "count": c.get("count"),
            "stack_excerpt": stack_excerpt,
            "triage": out,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"items": results}, indent=2), encoding="utf-8")
    return {"count": len(results), "output": str(OUT)}
