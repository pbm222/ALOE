# agents/llm_cluster_refiner.py
import json
from pathlib import Path
from typing import Dict, Any, List

from utils.file_loader import load_clusters
from utils.llm import ask_json

CLUSTERS_REFINED = Path("output") / "clusters_refined.json"

SYSTEM = """You are a log clustering assistant for an enterprise Java backend.

You MUST respond with ONLY a single valid JSON object. No markdown, no backticks, no comments.

You will receive a LIST of log clusters. Each cluster has:
- idx: numeric cluster index
- service: service name (if available)
- java_class: Java class or component name
- message: representative log message
- count: number of occurrences

Your job:
- Group clusters that represent the SAME underlying logical error.
- Compare service name and log message: errors that occurred in the same service and have the same message 
  (just different parameters) are treated as being the same
- Treat dynamic parts like IDs, numbers, filenames, UUIDs, and similar variations as the SAME error,
  as long as the core message and root cause seem the same.
- For example, messages that differ only in a file name or ID suffix should usually be grouped together.
- Messages that occurred in the same service line but with different parameters are treated as the same

You MUST return a single JSON object with key "groups".

"groups" must be a list where each element has:
- "canonical_idx": the idx of the cluster that best represents the group
- "member_idxs": a list of all idx values that belong to this group (including canonical_idx)

Every input cluster idx must appear in exactly one "member_idxs" list in the output.
Do NOT invent new idx values.
"""

USER_TEMPLATE = """You will receive multiple log clusters to refine.

Each cluster has:
- idx
- service
- java_class
- message
- count

Clusters (JSON list):
{clusters_json}

Group clusters that represent the same underlying logical error as described in the system prompt.

Return a single JSON object with key "groups", where each element has:
- "canonical_idx": one of the input idx values
- "member_idxs": a list of idx values that belong to that group (including canonical_idx)
"""


def run() -> Dict[str, Any]:

    clusters: List[Dict[str, Any]] = load_clusters()

    if not clusters:
        CLUSTERS_REFINED.parent.mkdir(parents=True, exist_ok=True)
        CLUSTERS_REFINED.write_text(json.dumps({"clusters": []}, indent=2), encoding="utf-8")
        return {"count": 0, "output": str(CLUSTERS_REFINED)}

    # Prepare compact view for the LLM
    compact: List[Dict[str, Any]] = []
    for i, c in enumerate(clusters):
        idx = i
        compact.append(
            {
                "idx": idx,
                "service": c.get("service") or c.get("athena_service"),
                "java_class": c.get("java_class"),
                "message": c.get("message"),
                "count": c.get("count"),
            }
        )

    user = USER_TEMPLATE.format(
        clusters_json=json.dumps(compact, ensure_ascii=False, indent=2)
    )

    out = ask_json(SYSTEM, user)

    # Fallback: if LLM output is bad, just copy original clusters
    if not isinstance(out, dict):
        CLUSTERS_REFINED.parent.mkdir(parents=True, exist_ok=True)
        CLUSTERS_REFINED.write_text(
            json.dumps({"clusters": clusters}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"count": len(clusters), "output": str(CLUSTERS_REFINED)}

    groups = out.get("groups")
    if not isinstance(groups, list) or not groups:
        CLUSTERS_REFINED.parent.mkdir(parents=True, exist_ok=True)
        CLUSTERS_REFINED.write_text(
            json.dumps({"clusters": clusters}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"count": len(clusters), "output": str(CLUSTERS_REFINED)}

    cluster_by_idx: Dict[int, Dict[str, Any]] = {}
    for i, c in enumerate(clusters):
        idx = c.get("idx")
        if idx is None:
            idx = i
            c["idx"] = idx
        cluster_by_idx[int(idx)] = c

    used_idxs = set()
    merged_clusters: List[Dict[str, Any]] = []

    for g in groups:
        if not isinstance(g, dict):
            continue

        canonical_idx = g.get("canonical_idx")
        member_idxs = g.get("member_idxs") or []

        if canonical_idx is None:
            continue

        try:
            canonical_idx = int(canonical_idx)
            member_idxs = [int(x) for x in member_idxs]
        except (TypeError, ValueError):
            continue

        member_idxs = [idx for idx in member_idxs if idx in cluster_by_idx and idx not in used_idxs]
        if not member_idxs:
            continue

        used_idxs.update(member_idxs)

        canonical = cluster_by_idx.get(canonical_idx) or cluster_by_idx[member_idxs[0]]

        total_count = 0
        for idx in member_idxs:
            c = cluster_by_idx[idx]
            total_count += c.get("count") or 0

        merged = dict(canonical)
        merged["count"] = total_count
        merged["merged_member_idxs"] = member_idxs

        merged_clusters.append(merged)

    all_idxs = set(cluster_by_idx.keys())
    remaining = all_idxs - used_idxs
    for idx in sorted(remaining):
        merged_clusters.append(cluster_by_idx[idx])

    for new_idx, c in enumerate(merged_clusters):
        c["idx"] = new_idx

    CLUSTERS_REFINED.parent.mkdir(parents=True, exist_ok=True)
    CLUSTERS_REFINED.write_text(
        json.dumps({"clusters": merged_clusters}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {"count": len(merged_clusters), "output": str(CLUSTERS_REFINED)}
