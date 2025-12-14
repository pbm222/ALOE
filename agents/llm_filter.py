# agents/llm_filter.py
import json
from pathlib import Path
from typing import Dict, Any, List

from utils.file_loader import load_jira_drafts
from utils.llm import ask_json

FILTER_OUTPUT = Path("output") / "filter_suggestions.json"

BATCH_SIZE = 12

SYSTEM = """You are a log filtering assistant for an enterprise backend system.

Your task is to propose precise regex or Kibana KQL filters that:
- Match the given error cluster reliably.
- Generalize dynamic parts such as IDs, UUIDs, timestamps, numeric values.
- Avoid over-matching unrelated logs.
- Filter can contain a phrase fromt he error message
- DO NOT include into KQL filter log the Java class name or exception name (e.g., com.knowledgeprice.athena.documents.api.DocumentGenerationService)
- The filter should be specific to this error 
  (i.e., don't exclude the whole class name from the stack trace as some other error can occur in this class just in another place)
- Include error message
- Do NOT produce filters with the same log

Additionally, you must generate an Elasticsearch filter clause that can be inserted
directly into the 'must_not' array of an existing query. This clause should usually be:

- A simple match_phrase on the 'log' field, e.g.:
  { "match_phrase": { "log": "Some stable error text" } }

or, if necessary, a bool with multiple match_phrase subclauses, e.g.:
  {
    "bool": {
      "must": [
        { "match_phrase": { "log": "Part 1 of message" } },
        { "match_phrase": { "log": "Part 2 of message" } }
      ]
    }
  }

You will receive a LIST of clusters (derived from Jira drafts), and you must propose
at most one filter clause per cluster.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.

Return JSON with this exact schema:
{
  "items": [
    {
      "idx": <int>,
      "es_filter_clause": {
        "match_phrase": { "log": "..." }
      }
    },
    ...
  ]
}
"""

USER_TEMPLATE = """You will receive multiple log clusters that had Jira drafts created.

Each cluster has:
- cluster_idx: identifier of the cluster
- java_class: Java class
- message: representative message
- count: how many times it occurred
- triage: label, severity, priority, confidence

Clusters:
{clusters_json}

For EACH cluster, decide if you can propose an Elasticsearch filter clause that
would safely suppress these logs when added to the 'must_not' section of a query.

Return a single JSON object with key "items" as described in the system prompt.
If you cannot propose a safe filter for a cluster, you may omit it from the items list.
"""

def _chunked(seq: List[Any], size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def run() -> Dict[str, Any]:

    drafts = load_jira_drafts()

    if not drafts:
        FILTER_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        FILTER_OUTPUT.write_text(json.dumps({"suggestions": []}, indent=2), encoding="utf-8")
        return {"count": 0, "output": str(FILTER_OUTPUT)}

    clauses_by_idx: Dict[Any, Any] = {}

    for batch in _chunked(drafts, BATCH_SIZE):
        cluster_payloads: List[Dict[str, Any]] = []

        for d in batch:
            cluster_payload = d.get("cluster") or {
                "idx": d.get("idx"),
                "service": d.get("service"),
                "java_class": d.get("java_class"),
                "message": d.get("message"),
                "count": d.get("count"),
                "triage": d.get("triage"),
            }

            cluster_idx = d.get("idx") or cluster_payload.get("idx")

            cluster_payloads.append(
                {
                    "idx": cluster_idx,
                    "service": cluster_payload.get("service"),
                    "java_class": cluster_payload.get("java_class"),
                    "message": cluster_payload.get("message"),
                    "count": cluster_payload.get("count"),
                    "triage": cluster_payload.get("triage"),
                }
            )

        user = USER_TEMPLATE.format(
            clusters_json=json.dumps(cluster_payloads, ensure_ascii=False, indent=2)
        )

        out = ask_json(SYSTEM, user)

        if not isinstance(out, dict):
            continue

        items = out.get("items") or []
        if not isinstance(items, list):
            continue

        for it in items:
            if not isinstance(it, dict):
                continue
            idx = it.get("idx")
            if idx is None:
                continue
            es_clause = it.get("es_filter_clause")
            if es_clause is None:
                continue
            clauses_by_idx[idx] = es_clause

    suggestions: List[Dict[str, Any]] = []

    for d in drafts:
        cluster_payload = d.get("cluster") or {
            "idx": d.get("idx"),
            "service": d.get("service"),
            "java_class": d.get("java_class"),
            "message": d.get("message"),
            "count": d.get("count"),
            "triage": d.get("triage"),
        }

        cluster_idx = d.get("idx") or cluster_payload.get("idx")
        es_clause = clauses_by_idx.get(cluster_idx)

        if not es_clause:
            continue

        suggestions.append(
            {
                "idx": cluster_idx,
                "service": cluster_payload.get("service"),
                "count": cluster_payload.get("count"),
                "es_filter_clause": es_clause,
            }
        )

    FILTER_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    FILTER_OUTPUT.write_text(
        json.dumps({"suggestions": suggestions}, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return {"count": len(suggestions), "output": str(FILTER_OUTPUT)}