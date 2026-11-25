"""Shared configuration, client factories, JSONL logging, and validation helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jsonschema import Draft7Validator
from moss import MossClient, MossInference
from moss.inference import Response, Task

ROOT_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT_DIR / "logs"
INFERENCE_LOG = LOGS_DIR / "inference_runs.jsonl"
TASKS_LOG = LOGS_DIR / "tasks_runs.jsonl"
DEMO_LOG = LOGS_DIR / "demo_runs.jsonl"
CHAT_LOG = LOGS_DIR / "chat_runs.jsonl"


def load_config() -> dict[str, str]:
    """Load and validate Moss configuration from .env / environment."""
    load_dotenv(ROOT_DIR / ".env", override=False)
    project_id = os.environ.get("MOSS_PROJECT_ID", "").strip()
    project_key = os.environ.get("MOSS_PROJECT_KEY", "").strip()
    inference_url = os.environ.get("MOSS_INFERENCE_URL", "https://inference.moss.dev/v1").strip()
    index_name = os.environ.get("MOSS_INDEX_NAME", "Company factuals").strip()

    if not project_id or not project_key or "your-project" in project_key:
        raise RuntimeError(
            "Missing valid MOSS_PROJECT_ID / MOSS_PROJECT_KEY in .env or environment."
        )
    return {
        "project_id": project_id,
        "project_key": project_key,
        "inference_url": inference_url,
        "index_name": index_name,
    }


def make_inference_client(
    cfg: dict[str, str] | None = None,
    *,
    timeout: float | None = 120.0,
    idle_timeout: float | None = 60.0,
    max_retries: int = 1,
) -> MossInference:
    """Create an async MossInference client from loaded config."""
    cfg = cfg or load_config()
    return MossInference(
        cfg["project_id"],
        cfg["project_key"],
        timeout=timeout,
        idle_timeout=idle_timeout,
        max_retries=max_retries,
    )


def make_moss_client(cfg: dict[str, str] | None = None) -> MossClient:
    """Create an async MossClient for index management and retrieval checks."""
    cfg = cfg or load_config()
    return MossClient(cfg["project_id"], cfg["project_key"])


def scrub_secrets(value: Any, secrets: list[str] | None = None) -> Any:
    """Recursively redact secret strings from logged payloads."""
    secrets = [s for s in (secrets or []) if s]
    if isinstance(value, str):
        out = value
        for s in secrets:
            if s in out:
                out = out.replace(s, "[REDACTED]")
        return out
    if isinstance(value, dict):
        return {k: scrub_secrets(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_secrets(v, secrets) for v in value]
    return value


def append_jsonl(path: Path, record: dict[str, Any], secrets: list[str] | None = None) -> None:
    """Append a single timestamped JSON record to a .jsonl file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **record,
    }
    clean = scrub_secrets(payload, secrets)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(clean, ensure_ascii=False, default=str) + "\n")


def extract_response_summary(resp: Response) -> dict[str, Any]:
    """Extract key telemetry fields from a Moss Inference Response."""
    usage = resp.usage
    return {
        "response_id": resp.id,
        "model": resp.model,
        "status": resp.status,
        "request_id": resp.request_id,
        "output_text": resp.output_text,
        "output_types": [getattr(item, "type", type(item).__name__) for item in resp.output],
        "incomplete_reason": resp.incomplete_details.reason if resp.incomplete_details else None,
        "usage": {
            "input_tokens": usage.input_tokens if usage else None,
            "output_tokens": usage.output_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None,
            "cached_tokens": (
                usage.input_tokens_details.cached_tokens
                if usage and usage.input_tokens_details
                else None
            ),
            "reasoning_tokens": (
                usage.output_tokens_details.reasoning_tokens
                if usage and usage.output_tokens_details
                else None
            ),
        },
    }


def extract_task_summary(task: Task[Any]) -> dict[str, Any]:
    """Extract key telemetry fields from a Moss Tasks API Task."""
    return {
        "task_id": task.id,
        "status": task.status,
        "model": task.model,
        "effort": task.effort,
        "limits": task.limits,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "trace_available": task.trace_available,
        "live_url": task.live_url,
        "cancel_requested": task.cancel_requested,
        "result": (
            {
                "output_text": task.result.output_text,
                "output": task.result.output,
            }
            if task.result
            else None
        ),
        "verification": (
            {
                "method": task.verification.method,
                "passed": task.verification.passed,
                "problems": task.verification.problems,
            }
            if task.verification
            else None
        ),
        "usage": (
            {
                "model_calls": task.usage.model_calls,
                "input_tokens": task.usage.input_tokens,
                "cached_input_tokens": task.usage.cached_input_tokens,
                "output_tokens": task.usage.output_tokens,
                "cost_usd": task.usage.cost_usd,
                "raw": task.usage.raw,
            }
            if task.usage
            else None
        ),
        "error": (
            {"code": task.error.code, "message": task.error.message}
            if task.error
            else None
        ),
    }


def validate_schema(instance: Any, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate structured output locally using JSON Schema Draft 7."""
    if instance is None:
        return False, ["output is None"]
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if not errors:
        return True, []
    messages = [
        f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
        for err in errors
    ]
    return False, messages
