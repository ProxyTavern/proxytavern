from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
import hashlib
import json
import re
import secrets
import sqlite3
import uuid


SCHEMA_VERSION = 2


class QueueDecisionError(ValueError):
    pass


class SelectorValidationError(ValueError):
    pass


class SchemaVersionError(RuntimeError):
    pass


class TokenLifecycleError(ValueError):
    pass


class SessionLookupError(ValueError):
    pass


class UpstreamRelayError(RuntimeError):
    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Upstream returned status {status_code}")


class Mode(str, Enum):
    INLINE = "inline"
    QUEUED = "queued"


class SessionStatus(str, Enum):
    RECEIVED = "received"
    QUEUED = "queued"
    APPROVED = "approved"
    FORWARDED = "forwarded"
    REJECTED = "rejected"


class QueueState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class Session:
    id: str
    inbound: dict[str, Any]
    transformed: dict[str, Any]
    status: SessionStatus
    created_at: str
    updated_at: str
    response: dict[str, Any] | None = None


@dataclass
class QueueItem:
    id: str
    session_id: str
    payload: dict[str, Any]
    state: QueueState = QueueState.PENDING
    decision: str | None = None
    forwarded_payload: dict[str, Any] | None = None


@dataclass
class ApiToken:
    id: str
    label: str | None
    token_hash: str
    salt: str
    created_at: str
    revoked_at: str | None = None
    rotated_from: str | None = None


SELECTOR_RE = re.compile(r"^\$((\.[A-Za-z_][A-Za-z0-9_]*)|(\[[0-9]+\]))+$")


def validate_selector(selector: str) -> None:
    if not isinstance(selector, str) or not SELECTOR_RE.match(selector):
        raise SelectorValidationError(
            f"Unsupported selector '{selector}'. Supported subset: $.foo.bar[0].baz"
        )


def _tokenize(selector: str) -> list[str | int]:
    # selector format already validated
    tokens: list[str | int] = []
    i = 1  # skip $
    while i < len(selector):
        if selector[i] == ".":
            j = i + 1
            while j < len(selector) and selector[j] not in ".[":
                j += 1
            tokens.append(selector[i + 1 : j])
            i = j
        elif selector[i] == "[":
            j = selector.index("]", i)
            tokens.append(int(selector[i + 1 : j]))
            i = j + 1
        else:
            i += 1
    return tokens


def _drop_selector(payload: Any, selector: str) -> Any:
    out = deepcopy(payload)
    tokens = _tokenize(selector)
    if not tokens:
        return out

    parent = out
    for token in tokens[:-1]:
        if isinstance(token, int):
            if not isinstance(parent, list) or token >= len(parent):
                return out
            parent = parent[token]
        else:
            if not isinstance(parent, dict) or token not in parent:
                return out
            parent = parent[token]

    leaf = tokens[-1]
    if isinstance(leaf, int):
        if isinstance(parent, list) and 0 <= leaf < len(parent):
            parent.pop(leaf)
    else:
        if isinstance(parent, dict):
            parent.pop(leaf, None)

    return out


class SQLiteState:
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        current_version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if current_version > SCHEMA_VERSION:
            raise SchemaVersionError(
                f"Database schema user_version {current_version} is newer than supported {SCHEMA_VERSION}"
            )

        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY,
                  inbound_json TEXT NOT NULL,
                  transformed_json TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  response_json TEXT
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue_items (
                  id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  state TEXT NOT NULL,
                  decision TEXT,
                  forwarded_payload_json TEXT,
                  created_order INTEGER NOT NULL UNIQUE
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_tokens (
                  id TEXT PRIMARY KEY,
                  label TEXT,
                  token_hash TEXT NOT NULL,
                  salt TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  revoked_at TEXT,
                  rotated_from TEXT
                )
                """
            )
            if current_version < 2:
                session_columns = {
                    row["name"]
                    for row in self.conn.execute("PRAGMA table_info(sessions)").fetchall()
                }
                if "created_at" not in session_columns:
                    self.conn.execute("ALTER TABLE sessions ADD COLUMN created_at TEXT")
                if "updated_at" not in session_columns:
                    self.conn.execute("ALTER TABLE sessions ADD COLUMN updated_at TEXT")
                now = datetime.now(timezone.utc).isoformat()
                self.conn.execute(
                    "UPDATE sessions SET created_at = COALESCE(created_at, ?), updated_at = COALESCE(updated_at, ?)",
                    (now, now),
                )

            if current_version < SCHEMA_VERSION:
                self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self.conn.close()

    def get_mode(self) -> Mode:
        row = self.conn.execute("SELECT value FROM kv WHERE key='mode'").fetchone()
        return Mode(row["value"]) if row else Mode.INLINE

    def set_mode(self, mode: Mode) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO kv(key, value) VALUES('mode', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (mode.value,),
            )

    def get_rules(self) -> list[str]:
        row = self.conn.execute("SELECT value FROM kv WHERE key='rules'").fetchone()
        return json.loads(row["value"]) if row else []

    def set_rules(self, rules: list[str]) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO kv(key, value) VALUES('rules', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(rules),),
            )

    def upsert_session(self, session: Session) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO sessions(id, inbound_json, transformed_json, status, created_at, updated_at, response_json)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  inbound_json=excluded.inbound_json,
                  transformed_json=excluded.transformed_json,
                  status=excluded.status,
                  updated_at=excluded.updated_at,
                  response_json=excluded.response_json
                """,
                (
                    session.id,
                    json.dumps(session.inbound),
                    json.dumps(session.transformed),
                    session.status.value,
                    session.created_at,
                    session.updated_at,
                    json.dumps(session.response) if session.response is not None else None,
                ),
            )

    def get_session(self, session_id: str) -> Session:
        row = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise SessionLookupError(f"Session not found: {session_id}")
        return Session(
            id=row["id"],
            inbound=json.loads(row["inbound_json"]),
            transformed=json.loads(row["transformed_json"]),
            status=SessionStatus(row["status"]),
            created_at=row["created_at"] or datetime.now(timezone.utc).isoformat(),
            updated_at=row["updated_at"] or datetime.now(timezone.utc).isoformat(),
            response=json.loads(row["response_json"]) if row["response_json"] else None,
        )

    def list_sessions(self) -> dict[str, Session]:
        rows = self.conn.execute("SELECT * FROM sessions ORDER BY rowid").fetchall()
        return {row["id"]: self._row_to_session(row) for row in rows}

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            inbound=json.loads(row["inbound_json"]),
            transformed=json.loads(row["transformed_json"]),
            status=SessionStatus(row["status"]),
            created_at=row["created_at"] or datetime.now(timezone.utc).isoformat(),
            updated_at=row["updated_at"] or datetime.now(timezone.utc).isoformat(),
            response=json.loads(row["response_json"]) if row["response_json"] else None,
        )

    def insert_queue_item(self, item: QueueItem) -> None:
        row = self.conn.execute("SELECT COALESCE(MAX(created_order), 0) + 1 AS next_order FROM queue_items").fetchone()
        next_order = row["next_order"]
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO queue_items(id, session_id, payload_json, state, decision, forwarded_payload_json, created_order)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.session_id,
                    json.dumps(item.payload),
                    item.state.value,
                    item.decision,
                    json.dumps(item.forwarded_payload) if item.forwarded_payload is not None else None,
                    next_order,
                ),
            )

    def update_queue_item(self, item: QueueItem) -> None:
        with self.conn:
            self.conn.execute(
                """
                UPDATE queue_items
                SET state=?, decision=?, forwarded_payload_json=?
                WHERE id=?
                """,
                (
                    item.state.value,
                    item.decision,
                    json.dumps(item.forwarded_payload) if item.forwarded_payload is not None else None,
                    item.id,
                ),
            )

    def get_queue_item(self, queue_id: str) -> QueueItem:
        row = self.conn.execute("SELECT * FROM queue_items WHERE id = ?", (queue_id,)).fetchone()
        if row is None:
            raise QueueDecisionError(f"Queue item not found: {queue_id}")
        return self._row_to_queue_item(row)

    def list_queue_items(self) -> dict[str, QueueItem]:
        rows = self.conn.execute("SELECT * FROM queue_items ORDER BY created_order").fetchall()
        return {row["id"]: self._row_to_queue_item(row) for row in rows}

    def _row_to_queue_item(self, row: sqlite3.Row) -> QueueItem:
        return QueueItem(
            id=row["id"],
            session_id=row["session_id"],
            payload=json.loads(row["payload_json"]),
            state=QueueState(row["state"]),
            decision=row["decision"],
            forwarded_payload=json.loads(row["forwarded_payload_json"]) if row["forwarded_payload_json"] else None,
        )

    def insert_api_token(self, token: ApiToken) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO api_tokens(id, label, token_hash, salt, created_at, revoked_at, rotated_from)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token.id,
                    token.label,
                    token.token_hash,
                    token.salt,
                    token.created_at,
                    token.revoked_at,
                    token.rotated_from,
                ),
            )

    def revoke_api_token(self, token_id: str, revoked_at: str) -> bool:
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE api_tokens
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE id = ?
                """,
                (revoked_at, token_id),
            )
        return cursor.rowcount > 0

    def list_api_tokens(self) -> list[ApiToken]:
        rows = self.conn.execute("SELECT * FROM api_tokens ORDER BY rowid").fetchall()
        return [self._row_to_api_token(row) for row in rows]

    def get_api_token(self, token_id: str) -> ApiToken:
        row = self.conn.execute("SELECT * FROM api_tokens WHERE id = ?", (token_id,)).fetchone()
        if row is None:
            raise TokenLifecycleError(f"Token not found: {token_id}")
        return self._row_to_api_token(row)

    def find_active_api_token_by_hash(self, token_hash: str) -> ApiToken | None:
        row = self.conn.execute(
            "SELECT * FROM api_tokens WHERE token_hash = ? AND revoked_at IS NULL LIMIT 1",
            (token_hash,),
        ).fetchone()
        return self._row_to_api_token(row) if row else None

    def set_token_rotated_from(self, token_id: str, rotated_from: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE api_tokens SET rotated_from = ? WHERE id = ?",
                (rotated_from, token_id),
            )

    def _row_to_api_token(self, row: sqlite3.Row) -> ApiToken:
        return ApiToken(
            id=row["id"],
            label=row["label"],
            token_hash=row["token_hash"],
            salt=row["salt"],
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
            rotated_from=row["rotated_from"],
        )


class ProxyTavern:
    def __init__(self, upstream_call: Callable[[dict[str, Any]], dict[str, Any]], db_path: str = ":memory:"):
        self.upstream_call = upstream_call
        self.state = SQLiteState(db_path=db_path)

    @property
    def mode(self) -> Mode:
        return self.state.get_mode()

    @property
    def rules(self) -> list[str]:
        return self.state.get_rules()

    @property
    def sessions(self) -> dict[str, Session]:
        return self.state.list_sessions()

    @property
    def queue(self) -> dict[str, QueueItem]:
        return self.state.list_queue_items()

    @property
    def schema_version(self) -> int:
        return self.state.conn.execute("PRAGMA user_version").fetchone()[0]

    def close(self) -> None:
        self.state.close()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _hash_token(raw_token: str, salt: str) -> str:
        return hashlib.sha256(f"{salt}:{raw_token}".encode("utf-8")).hexdigest()

    def issue_token(self, label: str | None = None) -> dict[str, str | None]:
        raw_token = secrets.token_urlsafe(32)
        return self.store_token(raw_token=raw_token, label=label)

    def store_token(self, raw_token: str, label: str | None = None) -> dict[str, str | None]:
        token_id = str(uuid.uuid4())
        salt = secrets.token_hex(16)
        token_hash = self._hash_token(raw_token, salt)
        created_at = self._utc_now_iso()
        self.state.insert_api_token(
            ApiToken(
                id=token_id,
                label=label,
                token_hash=token_hash,
                salt=salt,
                created_at=created_at,
            )
        )
        return {
            "id": token_id,
            "token": raw_token,
            "label": label,
            "created_at": created_at,
        }

    def revoke_token(self, token_id: str) -> dict[str, Any]:
        revoked_at = self._utc_now_iso()
        updated = self.state.revoke_api_token(token_id, revoked_at=revoked_at)
        if not updated:
            raise TokenLifecycleError(f"Token not found: {token_id}")
        return {"id": token_id, "revoked": True, "revoked_at": revoked_at}

    def rotate_token(self, token_id: str, label: str | None = None) -> dict[str, str | None]:
        existing = self.state.get_api_token(token_id)
        if existing.revoked_at is not None:
            raise TokenLifecycleError("Cannot rotate revoked token")
        self.revoke_token(token_id)
        issued = self.issue_token(label=label if label is not None else existing.label)
        self.state.set_token_rotated_from(str(issued["id"]), token_id)
        return issued

    def verify_token(self, raw_token: str) -> bool:
        for token in self.state.list_api_tokens():
            if token.revoked_at is not None:
                continue
            if self._hash_token(raw_token, token.salt) == token.token_hash:
                return True
        return False

    def list_token_metadata(self) -> list[dict[str, Any]]:
        return [
            {
                "id": token.id,
                "label": token.label,
                "created_at": token.created_at,
                "revoked_at": token.revoked_at,
                "rotated_from": token.rotated_from,
            }
            for token in self.state.list_api_tokens()
        ]

    def set_mode(self, mode: str) -> None:
        self.state.set_mode(Mode(mode))

    def set_rules(self, selectors: list[str]) -> None:
        for selector in selectors:
            validate_selector(selector)
        self.state.set_rules(list(selectors))

    def _transform(self, payload: dict[str, Any]) -> dict[str, Any]:
        out = deepcopy(payload)
        for selector in self.rules:
            out = _drop_selector(out, selector)
        return out

    def _call_upstream(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.upstream_call(payload)
        if isinstance(result, tuple) and len(result) == 2:
            status_code, body = result
            if isinstance(status_code, int) and status_code >= 400:
                raise UpstreamRelayError(status_code=status_code, body=body)
            return body
        return result

    def list_sessions(self) -> list[Session]:
        return list(self.sessions.values())

    def get_session(self, session_id: str) -> Session:
        return self.state.get_session(session_id)

    def chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        transformed = self._transform(payload)
        now = self._utc_now_iso()
        session = Session(
            id=session_id,
            inbound=deepcopy(payload),
            transformed=deepcopy(transformed),
            status=SessionStatus.RECEIVED,
            created_at=now,
            updated_at=now,
        )
        self.state.upsert_session(session)

        if self.mode == Mode.INLINE:
            response = self._call_upstream(transformed)
            session.response = deepcopy(response)
            session.status = SessionStatus.FORWARDED
            session.updated_at = self._utc_now_iso()
            self.state.upsert_session(session)
            return {"status": "forwarded", "session_id": session_id, "response": response}

        queue_id = str(uuid.uuid4())
        queue_item = QueueItem(id=queue_id, session_id=session_id, payload=deepcopy(transformed))
        self.state.insert_queue_item(queue_item)
        session.status = SessionStatus.QUEUED
        session.updated_at = self._utc_now_iso()
        self.state.upsert_session(session)
        return {
            "status": "queued",
            "session_id": session_id,
            "queue_id": queue_id,
        }

    def get_queue_item(self, queue_id: str) -> QueueItem:
        return self.state.get_queue_item(queue_id)

    def approve(self, queue_id: str) -> dict[str, Any]:
        item = self.get_queue_item(queue_id)
        if item.state != QueueState.PENDING:
            raise QueueDecisionError("Queue item already decided")

        session = self.state.get_session(item.session_id)
        response = self._call_upstream(item.payload)
        item.state = QueueState.APPROVED
        item.decision = "approve"
        item.forwarded_payload = deepcopy(item.payload)
        self.state.update_queue_item(item)

        session.status = SessionStatus.FORWARDED
        session.transformed = deepcopy(item.payload)
        session.response = deepcopy(response)
        session.updated_at = self._utc_now_iso()
        self.state.upsert_session(session)
        return {"status": "approved", "queue_id": queue_id, "response": response}

    def reject(self, queue_id: str, reason: str | None = None) -> dict[str, Any]:
        item = self.get_queue_item(queue_id)
        if item.state != QueueState.PENDING:
            raise QueueDecisionError("Queue item already decided")

        item.state = QueueState.REJECTED
        item.decision = "reject" + (f":{reason}" if reason else "")
        self.state.update_queue_item(item)

        session = self.state.get_session(item.session_id)
        session.status = SessionStatus.REJECTED
        session.updated_at = self._utc_now_iso()
        self.state.upsert_session(session)
        return {"status": "rejected", "queue_id": queue_id}

    def approve_with_edit(self, queue_id: str, edited_payload: dict[str, Any]) -> dict[str, Any]:
        item = self.get_queue_item(queue_id)
        if item.state != QueueState.PENDING:
            raise QueueDecisionError("Queue item already decided")

        response = self._call_upstream(edited_payload)
        item.state = QueueState.APPROVED
        item.decision = "approve-with-edit"
        item.forwarded_payload = deepcopy(edited_payload)
        self.state.update_queue_item(item)

        session = self.state.get_session(item.session_id)
        session.status = SessionStatus.FORWARDED
        session.transformed = deepcopy(edited_payload)
        session.response = deepcopy(response)
        session.updated_at = self._utc_now_iso()
        self.state.upsert_session(session)

        return {
            "status": "approved",
            "decision": "approve-with-edit",
            "queue_id": queue_id,
            "response": response,
        }
