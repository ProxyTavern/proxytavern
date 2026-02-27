from __future__ import annotations

import os
from typing import Any

from .api import create_app
from .core import ProxyTavern


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_app() -> Any:
    env = os.getenv("PROXYTAVERN_ENV", "prod").strip().lower()
    auth_enabled = _env_bool("PROXYTAVERN_AUTH_ENABLED", True)

    if not auth_enabled and env not in {"dev", "local", "test"}:
        raise RuntimeError(
            "Refusing to start with PROXYTAVERN_AUTH_ENABLED=false outside dev/local/test environment"
        )

    token = os.getenv("PROXYTAVERN_BEARER_TOKEN", "")
    if auth_enabled and not token:
        raise RuntimeError("PROXYTAVERN_BEARER_TOKEN is required when auth is enabled")

    db_path = os.getenv("PROXYTAVERN_DB_PATH", "/data/proxytavern.db")

    def upstream_call(payload: dict[str, Any]) -> dict[str, Any]:
        # Phase B placeholder upstream. Real forwarding wiring arrives in later phase.
        return {
            "id": "cmpl-proxytavern-stub",
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": "upstream stub"}}],
            "echo": payload,
        }

    proxy = ProxyTavern(upstream_call, db_path=db_path)

    if auth_enabled and token and not proxy.verify_token(token):
        proxy.store_token(raw_token=token, label="bootstrap-env")

    return create_app(proxy, token_verifier=proxy.verify_token, auth_enabled=auth_enabled)

