from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import json

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from .core import (
    Mode,
    ProxyTavern,
    QueueDecisionError,
    SelectorValidationError,
    SessionLookupError,
    TokenLifecycleError,
    UpstreamRelayError,
)


TokenVerifier = Callable[[str], bool]


@dataclass
class InMemoryTokenVerifier:
    """Simple injectable token verifier for local testing and dev wiring."""

    tokens: set[str] = field(default_factory=set)

    def add(self, token: str) -> None:
        self.tokens.add(token)

    def remove(self, token: str) -> None:
        self.tokens.discard(token)

    def __call__(self, token: str) -> bool:
        return token in self.tokens


def _queue_item_to_dict(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "session_id": item.session_id,
        "payload": item.payload,
        "state": item.state.value,
        "decision": item.decision,
        "forwarded_payload": item.forwarded_payload,
    }


def _map_queue_error(exc: QueueDecisionError) -> HTTPException:
    message = str(exc)
    if "not found" in message.lower():
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=409, detail=message)


def _map_token_error(exc: TokenLifecycleError) -> HTTPException:
    message = str(exc)
    if "not found" in message.lower():
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=409, detail=message)


def _map_session_error(exc: SessionLookupError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _session_to_dict(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "status": item.status.value,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "inbound": item.inbound,
        "transformed": item.transformed,
        "response": item.response,
    }


def _parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: expected Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


def _streaming_not_supported_error() -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "message": "Streaming is not supported while queue mode is enabled",
                "type": "queue_mode_streaming_unsupported",
            }
        },
    )


def _completion_to_stream_chunk(response: dict[str, Any]) -> dict[str, Any]:
    choices_out: list[dict[str, Any]] = []
    for idx, choice in enumerate(response.get("choices") or []):
        if not isinstance(choice, dict):
            continue
        choice_index = choice.get("index", idx)
        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
        if not delta and isinstance(choice.get("message"), dict):
            message = choice["message"]
            delta = {
                key: message[key]
                for key in ("role", "content", "tool_calls", "function_call")
                if key in message
            }

        converted_choice = {
            "index": choice_index,
            "delta": delta,
            "finish_reason": choice.get("finish_reason"),
        }
        if "logprobs" in choice:
            converted_choice["logprobs"] = choice["logprobs"]
        choices_out.append(converted_choice)

    if not choices_out:
        choices_out = [{"index": 0, "delta": {}, "finish_reason": "stop"}]

    return {
        "id": response.get("id", "chatcmpl-proxytavern"),
        "object": "chat.completion.chunk",
        "created": response.get("created"),
        "model": response.get("model"),
        "choices": choices_out,
    }


def _sse_payloads_from_completion(response: dict[str, Any]) -> list[str]:
    chunk = _completion_to_stream_chunk(response)
    return [f"data: {json.dumps(chunk)}\n\n", "data: [DONE]\n\n"]


def create_app(
    proxy: ProxyTavern,
    *,
    token_verifier: TokenVerifier | None = None,
    auth_enabled: bool = True,
) -> FastAPI:
    app = FastAPI(title="ProxyTavern")

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if not auth_enabled:
            return
        if token_verifier is None:
            raise HTTPException(
                status_code=500,
                detail="Server auth misconfiguration: token verifier is not configured",
            )
        token = _parse_bearer_token(authorization)
        if not token_verifier(token):
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    v1_router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])
    api_router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])

    @v1_router.post("/chat/completions")
    def chat_completions(payload: dict[str, Any]) -> Any:
        stream = payload.get("stream") is True

        try:
            if stream:
                result = proxy.chat_completions(payload, reject_if_mode=Mode.INLINE)
            else:
                result = proxy.chat_completions(payload)
        except UpstreamRelayError as exc:
            return JSONResponse(status_code=exc.status_code, content=exc.body)

        if not stream:
            return result

        if result.get("status") == "rejected_mode":
            return _streaming_not_supported_error()

        if result.get("status") != "forwarded":
            return JSONResponse(
                status_code=502,
                content={"error": {"message": "Streaming fallback unavailable", "type": "upstream_stream_unavailable"}},
            )

        sse_payloads = _sse_payloads_from_completion(result["response"])
        return StreamingResponse(iter(sse_payloads), media_type="text/event-stream")

    @api_router.get("/config")
    def get_config() -> dict[str, Any]:
        return {
            "mode": proxy.mode.value,
            "rules": proxy.rules,
        }

    @api_router.post("/config")
    def set_config(body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="Request body must be an object")

        has_mode = "mode" in body
        has_rules = "rules" in body
        if not has_mode and not has_rules:
            raise HTTPException(status_code=422, detail="body must include mode and/or rules")

        if has_mode:
            mode = body.get("mode")
            if not isinstance(mode, str):
                raise HTTPException(status_code=422, detail="body.mode must be a string")
            try:
                proxy.set_mode(mode)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"Invalid mode: {mode}") from exc

        if has_rules:
            rules = body.get("rules")
            if not isinstance(rules, list) or any(not isinstance(item, str) for item in rules):
                raise HTTPException(status_code=422, detail="body.rules must be an array of selector strings")
            try:
                proxy.set_rules(rules)
            except SelectorValidationError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        return {
            "mode": proxy.mode.value,
            "rules": proxy.rules,
        }

    @api_router.get("/token")
    def list_tokens() -> dict[str, Any]:
        return {"items": proxy.list_token_metadata()}

    @api_router.post("/token/generate")
    def generate_token(body: dict[str, Any] | None = None) -> dict[str, Any]:
        label: str | None = None
        if body is not None:
            if not isinstance(body, dict):
                raise HTTPException(status_code=422, detail="Request body must be an object")
            raw_label = body.get("label")
            if raw_label is not None and not isinstance(raw_label, str):
                raise HTTPException(status_code=422, detail="body.label must be a string when provided")
            label = raw_label
        return proxy.issue_token(label=label)

    @api_router.post("/token/revoke")
    def revoke_token(body: dict[str, Any]) -> dict[str, Any]:
        token_id = body.get("token_id") if isinstance(body, dict) else None
        if not isinstance(token_id, str) or not token_id:
            raise HTTPException(status_code=422, detail="body.token_id must be a non-empty string")
        try:
            return proxy.revoke_token(token_id)
        except TokenLifecycleError as exc:
            raise _map_token_error(exc) from exc

    @api_router.post("/token/rotate")
    def rotate_token(body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="Request body must be an object")
        token_id = body.get("token_id")
        label = body.get("label")
        if not isinstance(token_id, str) or not token_id:
            raise HTTPException(status_code=422, detail="body.token_id must be a non-empty string")
        if label is not None and not isinstance(label, str):
            raise HTTPException(status_code=422, detail="body.label must be a string when provided")
        try:
            rotated = proxy.rotate_token(token_id, label=label)
            rotated["rotated_from"] = token_id
            return rotated
        except TokenLifecycleError as exc:
            raise _map_token_error(exc) from exc

    @api_router.get("/sessions")
    def list_sessions() -> dict[str, list[dict[str, Any]]]:
        items = [_session_to_dict(item) for item in proxy.list_sessions()]
        return {"items": items}

    @api_router.get("/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        try:
            return _session_to_dict(proxy.get_session(session_id))
        except SessionLookupError as exc:
            raise _map_session_error(exc) from exc

    @api_router.get("/queue")
    def list_queue() -> dict[str, list[dict[str, Any]]]:
        items = [_queue_item_to_dict(item) for item in proxy.queue.values()]
        return {"items": items}

    @api_router.post("/queue/{queue_id}/approve")
    def approve(queue_id: str) -> Any:
        try:
            return proxy.approve(queue_id)
        except QueueDecisionError as exc:
            raise _map_queue_error(exc) from exc
        except UpstreamRelayError as exc:
            return JSONResponse(status_code=exc.status_code, content=exc.body)

    @api_router.post("/queue/{queue_id}/reject")
    def reject(queue_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        reason = None
        if body:
            reason = body.get("reason")
        try:
            return proxy.reject(queue_id, reason=reason)
        except QueueDecisionError as exc:
            raise _map_queue_error(exc) from exc

    @api_router.post("/queue/{queue_id}/approve-with-edit")
    def approve_with_edit(queue_id: str, body: dict[str, Any]) -> Any:
        edited_payload = body.get("payload")
        if not isinstance(edited_payload, dict):
            raise HTTPException(status_code=422, detail="body.payload must be an object")
        try:
            return proxy.approve_with_edit(queue_id, edited_payload=edited_payload)
        except QueueDecisionError as exc:
            raise _map_queue_error(exc) from exc
        except UpstreamRelayError as exc:
            return JSONResponse(status_code=exc.status_code, content=exc.body)

    app.include_router(v1_router)
    app.include_router(api_router)
    return app
