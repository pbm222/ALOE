# agents/log_source.py
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

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


def load_logs_from_elasticsearch(
        es_url: str,
        index: str,
        username: str | None = None,
        password: str | None = None,
        size: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Real mode: fetch logs from Elasticsearch using the query stored
    in resources/elastic_query.json.
    """
    if Elasticsearch is None:
        raise RuntimeError(
            "Elasticsearch client not installed. "
            "Run `pip install elasticsearch` or adjust dependencies."
        )

    # Load query from file
    query_file = Path("resources/elastic_query.json")
    if not query_file.exists():
        raise FileNotFoundError("Missing resources/elastic_query.json")

    query = json.loads(query_file.read_text(encoding="utf-8"))

    print(f"[cyan]Connecting to Elasticsearch at {es_url}[/cyan]")
    es_kwargs: Dict[str, Any] = {"hosts": [es_url]}

    if username and password:
        es_kwargs["basic_auth"] = (username, password)

    es = Elasticsearch(**es_kwargs)

    print(f"[cyan]Querying index '{index}'[/cyan]")
    resp = es.search(
        index=index,
        body=query
    )

    hits = resp.get("hits", {}).get("hits", [])
    logs: List[Dict[str, Any]] = []

    for h in hits:
        source = h.get("_source", {})
        logs.append(source)

    print(f"[green]Fetched {len(logs)} logs from Elasticsearch[/green]")
    return logs


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
