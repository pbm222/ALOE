# agents/log_source.py
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich import print

try:
    from elasticsearch import Elasticsearch
except ImportError:
    Elasticsearch = None

def load_logs_from_file(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        es_data = json.load(f)
    hits = es_data.get("hits", {}).get("hits", [])
    return [h.get("_source", {}) or {} for h in hits]

try:
    from elasticsearch import Elasticsearch
except ImportError:
    Elasticsearch = None


def _ensure_last_24h_range(query: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures the query contains @timestamp range now-1d..now.
    Adds it if missing. Keeps existing bool structure if present.
    """
    q = dict(query)  # shallow copy

    base = q.get("query", {})
    if not base:
        base = {"bool": {"must": []}}
        q["query"] = base

    bool_q = base.get("bool")
    if not bool_q:
        base["bool"] = {"must": []}
        bool_q = base["bool"]

    must = bool_q.get("must")
    if must is None:
        bool_q["must"] = []
        must = bool_q["must"]

    # Add range only if not already present
    has_range = any(
        isinstance(c, dict) and "range" in c and "@timestamp" in c.get("range", {})
        for c in must
    )
    if not has_range:
        must.append({
            "range": {
                "@timestamp": {
                    "gte": "now-1d",
                    "lte": "now"
                }
            }
        })

    return q

def load_logs_from_elasticsearch(
        es_url: str,
        index: str,
        username: str | None = None,
        password: str | None = None,
        size: int = 1000,
) -> List[Dict[str, Any]]:
    if Elasticsearch is None:
        raise RuntimeError(
            "Elasticsearch client not installed. "
            "Run `pip install elasticsearch` or adjust dependencies."
        )
    if not es_url:
        raise ValueError("ALOE_ES_URL is not set")
    if not index:
        raise ValueError("ALOE_ES_INDEX is not set")

    query_file = Path("resources/elastic_query.json")
    if not query_file.exists():
        raise FileNotFoundError("Missing resources/elastic_query.json")

    query = json.loads(query_file.read_text(encoding="utf-8"))
    query = _ensure_last_24h_range(query)

    query["sort"] = [
        {"@timestamp": {"order": "desc"}},
        {"_shard_doc": {"order": "desc"}}
    ]
    query["size"] = size

    print(f"[cyan]Connecting to Elasticsearch at {es_url}[/cyan]")
    es_kwargs: Dict[str, Any] = {"hosts": [es_url]}
    if username and password:
        es_kwargs["basic_auth"] = (username, password)
    es = Elasticsearch(**es_kwargs)

    print(f"[cyan]Opening PIT for index '{index}'[/cyan]")
    pit = es.open_point_in_time(index=index, keep_alive="2m")
    pit_id = pit["id"]

    logs: List[Dict[str, Any]] = []
    search_after: Optional[List[Any]] = None

    try:
        while True:
            body = dict(query)
            body["pit"] = {"id": pit_id, "keep_alive": "2m"}

            if search_after is not None:
                body["search_after"] = search_after

            resp = es.search(body=body)
            hits = resp.get("hits", {}).get("hits", [])
            if not hits:
                break

            for h in hits:
                logs.append(h.get("_source", {}) or {})

            search_after = hits[-1].get("sort")
            if not search_after:
                # If sort values are missing, pagination can't continue safely
                break

        print(f"[green]Fetched {len(logs)} logs from Elasticsearch (last 24h)[/green]")
        return logs

    finally:
        try:
            es.close_point_in_time(body={"id": pit_id})
        except Exception:
            pass

def load_logs(source: str = "mock") -> List[Dict[str, Any]]:
    source = source.lower()

    if source == "mock":
        mock_path = os.getenv("ALOE_MOCK_LOG_FILE", "resources/test_logs.json")
        return load_logs_from_file(Path(mock_path))

    if source == "elastic":
        es_url = os.getenv("ALOE_ES_URL")
        es_index = os.getenv("ALOE_ES_INDEX", "logstash-*")
        es_username = os.getenv("ALOE_ES_USERNAME")
        es_password = os.getenv("ALOE_ES_PASSWORD")

        return load_logs_from_elasticsearch(
            es_url=es_url,
            index=es_index,
            username=es_username,
            password=es_password,
        )

    raise ValueError(f"Unknown log source: {source}")
