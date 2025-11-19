import os

class Settings:
    ES_URL: str = os.environ.get("ES_URL", "https://your-es-host:9200")
    ES_USER: str = os.environ.get("ES_USER", "")
    ES_PASS: str = os.environ.get("ES_PASS", "")
    ES_INDEX: str = os.environ.get("ES_INDEX", "app-logs-*")  # adjust to your index pattern
    VERIFY_SSL: bool = os.environ.get("ES_VERIFY_SSL", "true").lower() == "true"

settings = Settings()