"""
ReadMark — Observability.

- Structured JSON logs to stdout (picked up by Docker → CloudWatch Logs).
- Prometheus metrics at /metrics (HTTP metrics + custom AI usage/cost counters).

Kept intentionally small: no external agents, no sidecars.
"""

import json
import logging
import sys
from datetime import datetime, timezone

from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

# ── Custom metrics (AI usage / cost — the FinOps signal) ──────────────────
AI_REQUESTS = Counter(
    "readmark_ai_requests_total", "AI summarization requests",
    ["provider", "model", "status"],
)
AI_TOKENS = Counter(
    "readmark_ai_tokens_total", "AI tokens consumed",
    ["provider", "model", "direction"],
)
AI_COST = Counter(
    "readmark_ai_cost_usd_total", "Estimated AI spend in USD",
    ["provider", "model"],
)


def record_ai_usage(provider, model, input_tokens, output_tokens, cost_usd, status="ok"):
    AI_REQUESTS.labels(provider, model, status).inc()
    if status == "ok":
        AI_TOKENS.labels(provider, model, "input").inc(input_tokens)
        AI_TOKENS.labels(provider, model, "output").inc(output_tokens)
        AI_COST.labels(provider, model).inc(cost_usd)


# ── Structured JSON logging ───────────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, val in getattr(record, "extra_fields", {}).items():
            payload[key] = val
        return json.dumps(payload)


def setup_logging(level="INFO"):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    return logging.getLogger("readmark")


def setup_metrics(app):
    """Expose Prometheus metrics at /metrics."""
    Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/metrics", "/api/health", "/api/ready"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
