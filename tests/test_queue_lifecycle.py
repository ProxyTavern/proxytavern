import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from proxytavern import ProxyTavern, QueueDecisionError, SchemaVersionError, SelectorValidationError, TokenLifecycleError


class QueueLifecycleTests(unittest.TestCase):
    def test_inline_chat_completion_no_regression_flow(self):
        seen = []

        def upstream(payload):
            seen.append(payload)
            return {"id": "cmpl-1", "object": "chat.completion", "choices": [{"message": {"role": "assistant", "content": "ok"}}]}

        app = ProxyTavern(upstream)
        payload = {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
        }

        result = app.chat_completions(payload)

        self.assertEqual(result["status"], "forwarded")
        self.assertIn("session_id", result)
        self.assertEqual(result["response"]["object"], "chat.completion")
        self.assertEqual(seen[0], payload)

    def test_queue_pending_creation_when_queued_mode_enabled(self):
        calls = []

        def upstream(payload):
            calls.append(payload)
            return {"ok": True}

        app = ProxyTavern(upstream)
        app.set_mode("queued")

        payload = {"messages": [{"role": "user", "content": "queued please"}]}
        result = app.chat_completions(payload)

        self.assertEqual(result["status"], "queued")
        self.assertIn(result["queue_id"], app.queue)
        self.assertEqual(calls, [])

    def test_queue_approve_as_is_forwards_payload(self):
        calls = []

        def upstream(payload):
            calls.append(payload)
            return {"id": "u-1", "ok": True}

        app = ProxyTavern(upstream)
        app.set_mode("queued")
        queue_id = app.chat_completions({"messages": [{"role": "user", "content": "approve me"}]})["queue_id"]

        result = app.approve(queue_id)

        self.assertEqual(result["status"], "approved")
        self.assertEqual(len(calls), 1)
        self.assertEqual(app.queue[queue_id].state.value, "approved")

    def test_queue_reject_marks_rejected_without_forwarding(self):
        calls = []

        def upstream(payload):
            calls.append(payload)
            return {"ok": True}

        app = ProxyTavern(upstream)
        app.set_mode("queued")
        queue_id = app.chat_completions({"messages": [{"role": "user", "content": "reject me"}]})["queue_id"]

        result = app.reject(queue_id, reason="policy")

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(app.queue[queue_id].state.value, "rejected")
        self.assertEqual(calls, [])

    def test_queue_approve_with_edit_forwards_edited_payload(self):
        calls = []

        def upstream(payload):
            calls.append(payload)
            return {"id": "u-edit", "ok": True}

        app = ProxyTavern(upstream)
        app.set_mode("queued")
        queue_id = app.chat_completions({"messages": [{"role": "user", "content": "original"}]})["queue_id"]

        edited = {"messages": [{"role": "user", "content": "edited"}]}
        result = app.approve_with_edit(queue_id, edited)

        self.assertEqual(result["decision"], "approve-with-edit")
        self.assertEqual(calls[0]["messages"][0]["content"], "edited")
        self.assertEqual(app.queue[queue_id].forwarded_payload, edited)

    def test_cannot_decide_same_queue_item_twice(self):
        app = ProxyTavern(lambda payload: {"ok": True})
        app.set_mode("queued")
        queue_id = app.chat_completions({"messages": [{"role": "user", "content": "once"}]})["queue_id"]

        app.approve(queue_id)

        with self.assertRaises(QueueDecisionError):
            app.reject(queue_id)

    def test_selector_validation_rejects_invalid_selector(self):
        app = ProxyTavern(lambda payload: {"ok": True})
        with self.assertRaises(SelectorValidationError):
            app.set_rules(["messages[0].content"])

    def test_deterministic_transform_same_input_same_output(self):
        app = ProxyTavern(lambda payload: {"ok": True})
        app.set_rules(["$.messages[0].content"])

        payload = {
            "messages": [
                {"role": "user", "content": "secret"},
                {"role": "assistant", "content": "reply"},
            ]
        }

        a = app._transform(payload)
        b = app._transform(payload)

        self.assertEqual(a, b)
        self.assertNotIn("content", a["messages"][0])

    def test_queue_and_mode_persist_after_reloading_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"

            first = ProxyTavern(lambda payload: {"ok": True}, db_path=str(db_path))
            first.set_mode("queued")
            queued = first.chat_completions({"messages": [{"role": "user", "content": "persist me"}]})
            queue_id = queued["queue_id"]
            first.close()

            second = ProxyTavern(lambda payload: {"ok": True}, db_path=str(db_path))
            self.assertEqual(second.mode.value, "queued")
            self.assertIn(queue_id, second.queue)
            self.assertEqual(second.queue[queue_id].state.value, "pending")

    def test_decided_queue_states_persist_across_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"

            first = ProxyTavern(lambda payload: {"ok": True}, db_path=str(db_path))
            first.set_mode("queued")
            approved_queue_id = first.chat_completions({"messages": [{"role": "user", "content": "approve"}]})["queue_id"]
            rejected_queue_id = first.chat_completions({"messages": [{"role": "user", "content": "reject"}]})["queue_id"]
            first.approve(approved_queue_id)
            first.reject(rejected_queue_id, reason="policy")
            first.close()

            second = ProxyTavern(lambda payload: {"ok": True}, db_path=str(db_path))
            self.assertEqual(second.queue[approved_queue_id].state.value, "approved")
            self.assertEqual(second.queue[approved_queue_id].decision, "approve")
            self.assertEqual(second.queue[rejected_queue_id].state.value, "rejected")
            self.assertEqual(second.queue[rejected_queue_id].decision, "reject:policy")

    def test_schema_user_version_is_set_and_guarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            first = ProxyTavern(lambda payload: {"ok": True}, db_path=str(db_path))
            self.assertEqual(first.schema_version, 2)
            first.close()

            app = ProxyTavern(lambda payload: {"ok": True}, db_path=str(db_path))
            app.state.conn.execute("PRAGMA user_version = 99")
            app.close()

            with self.assertRaises(SchemaVersionError):
                ProxyTavern(lambda payload: {"ok": True}, db_path=str(db_path))

    def test_schema_guard_rejects_unsupported_future_db_with_contract_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA user_version = 999")
            conn.commit()
            conn.close()

            with self.assertRaises(SchemaVersionError) as ctx:
                ProxyTavern(lambda payload: {"ok": True}, db_path=str(db_path))

            self.assertIn("newer than supported", str(ctx.exception).lower())

    def test_token_lifecycle_issue_revoke_rotate_with_hashed_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            app = ProxyTavern(lambda payload: {"ok": True}, db_path=str(db_path))

            issued = app.issue_token(label="ops")
            self.assertTrue(app.verify_token(str(issued["token"])))

            stored = app.state.get_api_token(str(issued["id"]))
            self.assertNotEqual(stored.token_hash, issued["token"])

            app.revoke_token(str(issued["id"]))
            self.assertFalse(app.verify_token(str(issued["token"])))

            active = app.issue_token(label="active")
            rotated = app.rotate_token(str(active["id"]))
            self.assertFalse(app.verify_token(str(active["token"])))
            self.assertTrue(app.verify_token(str(rotated["token"])))

            rotated_meta = app.state.get_api_token(str(rotated["id"]))
            self.assertEqual(rotated_meta.rotated_from, active["id"])

            with self.assertRaises(TokenLifecycleError):
                app.rotate_token(str(issued["id"]))

    def test_token_metadata_audit_timestamps_and_lineage_integrity(self):
        app = ProxyTavern(lambda payload: {"ok": True})

        first = app.issue_token(label="ops")
        rotated = app.rotate_token(str(first["id"]))
        app.revoke_token(str(rotated["id"]))

        metadata = {row["id"]: row for row in app.list_token_metadata()}
        first_meta = metadata[str(first["id"])]
        rotated_meta = metadata[str(rotated["id"])]

        first_created = datetime.fromisoformat(str(first_meta["created_at"]))
        first_revoked = datetime.fromisoformat(str(first_meta["revoked_at"]))
        rotated_created = datetime.fromisoformat(str(rotated_meta["created_at"]))
        rotated_revoked = datetime.fromisoformat(str(rotated_meta["revoked_at"]))

        self.assertEqual(first_meta["rotated_from"], None)
        self.assertEqual(rotated_meta["rotated_from"], first_meta["id"])
        self.assertIsNotNone(first_meta["revoked_at"])
        self.assertIsNotNone(rotated_meta["revoked_at"])
        self.assertLessEqual(first_created, first_revoked)
        self.assertLessEqual(first_revoked, rotated_created)
        self.assertLessEqual(rotated_created, rotated_revoked)


if __name__ == "__main__":
    unittest.main()
