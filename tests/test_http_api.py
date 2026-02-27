import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from proxytavern import InMemoryTokenVerifier, ProxyTavern, create_app


class HttpApiTests(unittest.TestCase):
    def make_client(self, *, auth_enabled=True, token_verifier=None, db_path=":memory:", upstream_impl=None):
        upstream_calls = []

        def default_upstream(payload):
            upstream_calls.append(payload)
            return {
                "id": "cmpl-http",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            }

        upstream = upstream_impl or default_upstream
        proxy = ProxyTavern(upstream, db_path=db_path)
        app = create_app(proxy, auth_enabled=auth_enabled, token_verifier=token_verifier)
        return TestClient(app), proxy, upstream_calls

    @staticmethod
    def auth_headers(token="test-token"):
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def protected_targets(queue_id="dummy-id"):
        return [
            ("post", "/v1/chat/completions", {"json": {"messages": [{"role": "user", "content": "hello"}]}}),
            ("get", "/api/config", {}),
            ("post", "/api/config", {"json": {"mode": "queued"}}),
            ("get", "/api/token", {}),
            ("post", "/api/token/generate", {"json": {"label": "ops"}}),
            ("post", "/api/token/revoke", {"json": {"token_id": "dummy-token"}}),
            ("post", "/api/token/rotate", {"json": {"token_id": "dummy-token"}}),
            ("get", "/api/sessions", {}),
            ("get", "/api/sessions/dummy-session", {}),
            ("get", "/api/queue", {}),
            ("post", f"/api/queue/{queue_id}/approve", {}),
            ("post", f"/api/queue/{queue_id}/reject", {}),
            ("post", f"/api/queue/{queue_id}/approve-with-edit", {"json": {"payload": {}}}),
        ]

    def test_healthz_is_public(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, _calls = self.make_client(token_verifier=verifier)

        response = client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_v1_chat_completions_inline_non_regression_authorized_flow(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, calls = self.make_client(token_verifier=verifier)

        payload = {"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]}
        response = client.post("/v1/chat/completions", json=payload, headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "forwarded")
        self.assertEqual(body["response"]["object"], "chat.completion")
        self.assertEqual(calls, [payload])

    def test_inline_streaming_returns_sse_frames_and_done_marker(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, _calls = self.make_client(token_verifier=verifier)

        payload = {
            "model": "gpt-test",
            "stream": True,
            "messages": [{"role": "user", "content": "hello"}],
        }
        with client.stream("POST", "/v1/chat/completions", json=payload, headers=self.auth_headers()) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("content-type"), "text/event-stream; charset=utf-8")
            body = "".join(response.iter_text())

        self.assertIn("data: ", body)
        self.assertIn('"object": "chat.completion.chunk"', body)
        self.assertIn("data: [DONE]", body)

    def test_inline_streaming_preserves_done_terminal_frame(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, _calls = self.make_client(token_verifier=verifier)

        payload = {
            "stream": True,
            "messages": [{"role": "user", "content": "terminal frame"}],
        }
        with client.stream("POST", "/v1/chat/completions", json=payload, headers=self.auth_headers()) as response:
            body = "".join(response.iter_text())

        self.assertTrue(body.strip().endswith("data: [DONE]"))

    def test_queue_mode_streaming_is_rejected_with_deterministic_409(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, proxy, calls = self.make_client(token_verifier=verifier)
        proxy.set_mode("queued")

        payload = {
            "stream": True,
            "messages": [{"role": "user", "content": "hello"}],
        }
        response = client.post("/v1/chat/completions", json=payload, headers=self.auth_headers())

        self.assertEqual(response.status_code, 409)
        error = response.json()["error"]
        self.assertEqual(error["type"], "queue_mode_streaming_unsupported")
        self.assertEqual(calls, [])

    def test_protected_endpoints_reject_missing_token(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, calls = self.make_client(token_verifier=verifier)

        for method, path, kwargs in self.protected_targets(queue_id="dummy-id"):
            with self.subTest(path=path):
                response = getattr(client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401)
                self.assertIn("missing bearer token", response.json()["detail"].lower())

        self.assertEqual(calls, [])

    def test_protected_endpoints_reject_malformed_authorization_header(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, calls = self.make_client(token_verifier=verifier)

        malformed_headers = [
            {"Authorization": "Token test-token"},
            {"Authorization": "Bearer"},
            {"Authorization": "Bearer\ttest-token"},
        ]

        for method, path, kwargs in self.protected_targets(queue_id="dummy-id"):
            for headers in malformed_headers:
                with self.subTest(path=path, header=headers["Authorization"]):
                    response = getattr(client, method)(path, headers=headers, **kwargs)
                    self.assertEqual(response.status_code, 401)
                    self.assertIn("expected authorization: bearer <token>", response.json()["detail"].lower())

        self.assertEqual(calls, [])

    def test_protected_endpoints_reject_invalid_token(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, calls = self.make_client(token_verifier=verifier)

        for method, path, kwargs in self.protected_targets(queue_id="dummy-id"):
            with self.subTest(path=path):
                response = getattr(client, method)(
                    path,
                    headers=self.auth_headers("bad-token"),
                    **kwargs,
                )
                self.assertEqual(response.status_code, 401)
                self.assertIn("invalid bearer token", response.json()["detail"].lower())

        self.assertEqual(calls, [])

    def test_get_and_update_config_authorized(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, _calls = self.make_client(token_verifier=verifier)

        current = client.get("/api/config", headers=self.auth_headers())
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["mode"], "inline")
        self.assertEqual(current.json()["rules"], [])

        updated = client.post(
            "/api/config",
            json={"mode": "queued", "rules": ["$.messages[0].content"]},
            headers=self.auth_headers(),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["mode"], "queued")
        self.assertEqual(updated.json()["rules"], ["$.messages[0].content"])

    def test_post_config_validation(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, _calls = self.make_client(token_verifier=verifier)

        bad_cases = [
            {},
            {"mode": 123},
            {"mode": "bad-mode"},
            {"rules": "$.messages[0]"},
            {"rules": ["not-jsonpath"]},
        ]

        for body in bad_cases:
            with self.subTest(body=body):
                response = client.post("/api/config", json=body, headers=self.auth_headers())
                self.assertEqual(response.status_code, 422)

    def test_token_endpoints_generate_list_revoke_rotate(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, proxy, _calls = self.make_client(token_verifier=verifier)

        generated = client.post(
            "/api/token/generate",
            json={"label": "ops"},
            headers=self.auth_headers(),
        )
        self.assertEqual(generated.status_code, 200)
        first = generated.json()
        self.assertEqual(first["label"], "ops")
        self.assertTrue(proxy.verify_token(first["token"]))

        listed = client.get("/api/token", headers=self.auth_headers())
        self.assertEqual(listed.status_code, 200)
        ids = {item["id"] for item in listed.json()["items"]}
        self.assertIn(first["id"], ids)

        rotated = client.post(
            "/api/token/rotate",
            json={"token_id": first["id"], "label": "ops-rotated"},
            headers=self.auth_headers(),
        )
        self.assertEqual(rotated.status_code, 200)
        second = rotated.json()
        self.assertEqual(second["rotated_from"], first["id"])
        self.assertFalse(proxy.verify_token(first["token"]))
        self.assertTrue(proxy.verify_token(second["token"]))

        revoked = client.post(
            "/api/token/revoke",
            json={"token_id": second["id"]},
            headers=self.auth_headers(),
        )
        self.assertEqual(revoked.status_code, 200)
        self.assertTrue(revoked.json()["revoked"])
        self.assertFalse(proxy.verify_token(second["token"]))

    def test_token_endpoint_validation_and_errors(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, _calls = self.make_client(token_verifier=verifier)

        self.assertEqual(client.post("/api/token/revoke", json={}, headers=self.auth_headers()).status_code, 422)
        self.assertEqual(client.post("/api/token/rotate", json={}, headers=self.auth_headers()).status_code, 422)
        self.assertEqual(
            client.post(
                "/api/token/generate",
                json={"label": 123},
                headers=self.auth_headers(),
            ).status_code,
            422,
        )

        missing_revoke = client.post(
            "/api/token/revoke",
            json={"token_id": "nope"},
            headers=self.auth_headers(),
        )
        self.assertEqual(missing_revoke.status_code, 404)

        missing_rotate = client.post(
            "/api/token/rotate",
            json={"token_id": "nope"},
            headers=self.auth_headers(),
        )
        self.assertEqual(missing_rotate.status_code, 404)

    def test_sessions_endpoints_authorized_include_lifecycle_payloads(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, _calls = self.make_client(token_verifier=verifier)

        payload = {"messages": [{"role": "user", "content": "session me"}]}
        created = client.post("/v1/chat/completions", json=payload, headers=self.auth_headers()).json()
        session_id = created["session_id"]

        listing = client.get("/api/sessions", headers=self.auth_headers())
        self.assertEqual(listing.status_code, 200)
        items = listing.json()["items"]
        by_id = {item["id"]: item for item in items}
        self.assertIn(session_id, by_id)
        self.assertEqual(by_id[session_id]["status"], "forwarded")
        self.assertEqual(by_id[session_id]["inbound"], payload)
        self.assertEqual(by_id[session_id]["transformed"], payload)
        self.assertIn("created_at", by_id[session_id])
        self.assertIn("updated_at", by_id[session_id])

        detail = client.get(f"/api/sessions/{session_id}", headers=self.auth_headers())
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], session_id)

    def test_get_session_returns_404_for_unknown_id(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, _proxy, _calls = self.make_client(token_verifier=verifier)

        response = client.get("/api/sessions/not-a-real-id", headers=self.auth_headers())
        self.assertEqual(response.status_code, 404)

    def test_get_queue_and_decision_endpoints_authorized(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, proxy, calls = self.make_client(token_verifier=verifier)
        proxy.set_mode("queued")

        queued = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "please queue"}]},
            headers=self.auth_headers(),
        ).json()
        queue_id = queued["queue_id"]

        queue_response = client.get("/api/queue", headers=self.auth_headers())
        self.assertEqual(queue_response.status_code, 200)
        items = queue_response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], queue_id)
        self.assertEqual(items[0]["state"], "pending")

        approve_response = client.post(f"/api/queue/{queue_id}/approve", headers=self.auth_headers())
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.json()["status"], "approved")
        self.assertEqual(len(calls), 1)

    def test_reject_endpoint_and_not_found_error_authorized(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, proxy, calls = self.make_client(token_verifier=verifier)
        proxy.set_mode("queued")
        queue_id = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "reject me"}]},
            headers=self.auth_headers(),
        ).json()["queue_id"]

        reject_response = client.post(
            f"/api/queue/{queue_id}/reject",
            json={"reason": "policy"},
            headers=self.auth_headers(),
        )
        self.assertEqual(reject_response.status_code, 200)
        self.assertEqual(reject_response.json()["status"], "rejected")
        self.assertEqual(calls, [])

        missing = client.post("/api/queue/not-a-real-id/reject", headers=self.auth_headers())
        self.assertEqual(missing.status_code, 404)

    def test_approve_with_edit_and_conflict_error_authorized(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, proxy, calls = self.make_client(token_verifier=verifier)
        proxy.set_mode("queued")
        queue_id = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "original"}]},
            headers=self.auth_headers(),
        ).json()["queue_id"]

        edited_payload = {"messages": [{"role": "user", "content": "edited"}]}
        response = client.post(
            f"/api/queue/{queue_id}/approve-with-edit",
            json={"payload": edited_payload},
            headers=self.auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "approve-with-edit")
        self.assertEqual(calls[0]["messages"][0]["content"], "edited")

        second_decision = client.post(f"/api/queue/{queue_id}/approve", headers=self.auth_headers())
        self.assertEqual(second_decision.status_code, 409)

    def test_approve_with_edit_validates_body_shape_authorized(self):
        verifier = InMemoryTokenVerifier({"test-token"})
        client, proxy, _calls = self.make_client(token_verifier=verifier)
        proxy.set_mode("queued")
        queue_id = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "original"}]},
            headers=self.auth_headers(),
        ).json()["queue_id"]

        response = client.post(
            f"/api/queue/{queue_id}/approve-with-edit",
            json={"payload": "bad"},
            headers=self.auth_headers(),
        )
        self.assertEqual(response.status_code, 422)

    def test_upstream_non_2xx_is_relayed_on_inline_and_queued_approve(self):
        verifier = InMemoryTokenVerifier({"test-token"})

        def failing_upstream(_payload):
            return (429, {"error": {"message": "rate_limited", "type": "upstream"}})

        client, proxy, _calls = self.make_client(token_verifier=verifier, upstream_impl=failing_upstream)

        inline = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "fail inline"}]},
            headers=self.auth_headers(),
        )
        self.assertEqual(inline.status_code, 429)
        self.assertEqual(inline.json()["error"]["message"], "rate_limited")

        proxy.set_mode("queued")
        queued = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "fail approve"}]},
            headers=self.auth_headers(),
        ).json()
        approve = client.post(f"/api/queue/{queued['queue_id']}/approve", headers=self.auth_headers())
        self.assertEqual(approve.status_code, 429)
        self.assertEqual(approve.json()["error"]["type"], "upstream")

    def test_auth_can_be_disabled_for_local_testing(self):
        client, _proxy, calls = self.make_client(auth_enabled=False, token_verifier=None)

        payload = {"messages": [{"role": "user", "content": "no auth in local test"}]}
        response = client.post("/v1/chat/completions", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [payload])

    def test_queue_list_persists_across_app_restart_with_sqlite(self):
        verifier = InMemoryTokenVerifier({"test-token"})

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"

            client1, proxy1, _calls1 = self.make_client(token_verifier=verifier, db_path=str(db_path))
            proxy1.set_mode("queued")
            queued = client1.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "persist queue"}]},
                headers=self.auth_headers(),
            ).json()
            queue_id = queued["queue_id"]
            proxy1.close()

            client2, _proxy2, _calls2 = self.make_client(token_verifier=verifier, db_path=str(db_path))
            queue_response = client2.get("/api/queue", headers=self.auth_headers())
            self.assertEqual(queue_response.status_code, 200)
            items = queue_response.json()["items"]
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], queue_id)
            self.assertEqual(items[0]["state"], "pending")

    def test_decided_queue_states_persist_across_http_app_restart(self):
        verifier = InMemoryTokenVerifier({"test-token"})

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"

            client1, proxy1, _calls1 = self.make_client(token_verifier=verifier, db_path=str(db_path))
            proxy1.set_mode("queued")
            approved_id = client1.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "approve me"}]},
                headers=self.auth_headers(),
            ).json()["queue_id"]
            rejected_id = client1.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "reject me"}]},
                headers=self.auth_headers(),
            ).json()["queue_id"]
            client1.post(f"/api/queue/{approved_id}/approve", headers=self.auth_headers())
            client1.post(
                f"/api/queue/{rejected_id}/reject",
                json={"reason": "policy"},
                headers=self.auth_headers(),
            )
            proxy1.close()

            client2, _proxy2, _calls2 = self.make_client(token_verifier=verifier, db_path=str(db_path))
            items = client2.get("/api/queue", headers=self.auth_headers()).json()["items"]
            by_id = {item["id"]: item for item in items}
            self.assertEqual(by_id[approved_id]["state"], "approved")
            self.assertEqual(by_id[approved_id]["decision"], "approve")
            self.assertEqual(by_id[rejected_id]["state"], "rejected")
            self.assertEqual(by_id[rejected_id]["decision"], "reject:policy")

    def test_config_and_token_metadata_persist_across_http_app_restart(self):
        verifier = InMemoryTokenVerifier({"test-token"})

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"

            client1, proxy1, _calls1 = self.make_client(token_verifier=verifier, db_path=str(db_path))
            client1.post(
                "/api/config",
                json={"mode": "queued", "rules": ["$.messages[0].content"]},
                headers=self.auth_headers(),
            )
            token = client1.post(
                "/api/token/generate",
                json={"label": "persisted"},
                headers=self.auth_headers(),
            ).json()
            proxy1.close()

            client2, proxy2, _calls2 = self.make_client(token_verifier=verifier, db_path=str(db_path))
            cfg = client2.get("/api/config", headers=self.auth_headers()).json()
            self.assertEqual(cfg["mode"], "queued")
            self.assertEqual(cfg["rules"], ["$.messages[0].content"])

            listing = client2.get("/api/token", headers=self.auth_headers()).json()["items"]
            by_id = {item["id"]: item for item in listing}
            self.assertIn(token["id"], by_id)
            self.assertEqual(by_id[token["id"]]["label"], "persisted")
            self.assertTrue(proxy2.verify_token(token["token"]))


if __name__ == "__main__":
    unittest.main()
