# agents/log_preprocessor.py
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, List, Tuple
from rich import print

INPUT_FILE = Path("output") / "logs.json"
RAW_OUT   = Path("output") / "raw_logs.json"
CL_OUT    = Path("output") / "clusters.json"

def _load_es_export(path: Path) -> List[Dict[str, Any]]:
    """Load ES search response JSON and return _source list."""
    with path.open("r", encoding="utf-8") as f:
        es_data = json.load(f)
    hits = es_data.get("hits", {}).get("hits", [])
    return [h.get("_source", {}) or {} for h in hits]

def _normalize(src: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one log record to a minimal schema."""
    return {
        "timestamp": src.get("@timestamp") or src.get("timestamp"),
        "level": src.get("athena_level") or src.get("level"),
        "service": src.get("AthenaServiceName") or src.get("athena_service"),
        "message": src.get("athena_message") or src.get("log"),
        "java_class": src.get("athena_java_class"),
        "trace_id": src.get("athena_trace_id") or src.get("traceId"),
        "raw": src,
    }

def _cluster(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Simple grouping by (java_class, message)."""
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for e in logs:
        k = (e.get("java_class") or "<unknown_class>", (e.get("message") or "").strip())
        groups[k].append(e)

    clusters: List[Dict[str, Any]] = []
    for (java_class, message), items in groups.items():
        items_sorted = sorted(items, key=lambda x: x.get("timestamp") or "")
        clusters.append({
            "java_class": java_class,
            "message": message,
            "count": len(items),
            "sample": items_sorted[0],
            "timestamps": [x.get("timestamp") for x in items_sorted],
        })
    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters

def run(context: Dict[str, Any]) -> Dict[str, Any]:
    """Log Preprocessor Agent: load → normalize → cluster → write files → return context."""
    print(f"[green]Preprocessing logs from {INPUT_FILE}[/green]")
    sources = _load_es_export(INPUT_FILE)
    norm = [_normalize(s) for s in sources]

    RAW_OUT.parent.mkdir(parents=True, exist_ok=True)
    with RAW_OUT.open("w", encoding="utf-8") as f:
        json.dump({"count": len(norm), "items": norm}, f, indent=2)
    print(f"[cyan]Saved {len(norm)} normalized logs → {RAW_OUT}[/cyan]")

    clusters = _cluster(norm)
    with CL_OUT.open("w", encoding="utf-8") as f:
        json.dump({"cluster_count": len(clusters), "log_count": len(norm), "clusters": clusters}, f, indent=2)
    print(f"[cyan]Saved {len(clusters)} clusters → {CL_OUT}[/cyan]")

    context = dict(context or {})
    context["raw_logs"] = norm
    context["clusters"] = clusters
    return context
