# agents/log_preprocessor.py
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, List, Tuple
from rich import print

from utils.log_source import load_logs

INPUT_FILE = Path("resources") / "test_logs.json"
RAW_LOGS_OUTPUT   = Path("output") / "raw_logs.json"
CLUSTERS_OUTPUT    = Path("output") / "clusters.json"

def _normalize(src: Dict[str, Any]) -> Dict[str, Any]:
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

def run(context: Dict[str, Any], source: str = "mock") -> Dict[str, Any]:
    print(f"[cyan]Loading logs (source={source})[/cyan]")
    raw_logs = load_logs(source=source)
    print(f"[cyan]Loaded {len(raw_logs)} raw logs[/cyan]")

    norm = [_normalize(s) for s in raw_logs]

    RAW_LOGS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with RAW_LOGS_OUTPUT.open("w", encoding="utf-8") as f:
        json.dump({"count": len(norm), "items": norm}, f, indent=2)
    print(f"[cyan]Saved {len(norm)} normalized logs → {RAW_LOGS_OUTPUT}[/cyan]")

    clusters = _cluster(norm)
    with CLUSTERS_OUTPUT.open("w", encoding="utf-8") as f:
        json.dump({"cluster_count": len(clusters), "log_count": len(norm), "clusters": clusters}, f, indent=2)
    print(f"[cyan]Saved {len(clusters)} clusters → {CLUSTERS_OUTPUT}[/cyan]")

    context = dict(context or {})
    context["raw_logs"] = norm
    context["clusters"] = clusters
    return context
