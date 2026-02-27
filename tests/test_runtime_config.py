import os
import unittest

from proxytavern.app import build_app


class RuntimeConfigTests(unittest.TestCase):
    def setUp(self):
        self._old_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_refuses_auth_disabled_outside_dev(self):
        os.environ["PROXYTAVERN_ENV"] = "prod"
        os.environ["PROXYTAVERN_AUTH_ENABLED"] = "false"

        with self.assertRaises(RuntimeError):
            build_app()

    def test_requires_token_when_auth_enabled(self):
        os.environ["PROXYTAVERN_ENV"] = "prod"
        os.environ["PROXYTAVERN_AUTH_ENABLED"] = "true"
        os.environ.pop("PROXYTAVERN_BEARER_TOKEN", None)

        with self.assertRaises(RuntimeError):
            build_app()

    def test_allows_dev_auth_disabled(self):
        os.environ["PROXYTAVERN_ENV"] = "dev"
        os.environ["PROXYTAVERN_AUTH_ENABLED"] = "false"
        os.environ["PROXYTAVERN_DB_PATH"] = ":memory:"

        app = build_app()
        self.assertEqual(app.title, "ProxyTavern")


if __name__ == "__main__":
    unittest.main()
