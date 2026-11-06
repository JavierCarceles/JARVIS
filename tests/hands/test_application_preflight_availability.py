"""
Tests for ApplicationPreflight availability verification (3.5.2.1).
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from src.hands.application_preflight import ApplicationPreflight, PreflightResult


class TestApplicationPreflightAvailability(unittest.TestCase):
    def setUp(self):
        self.preflight = ApplicationPreflight()

    def test_available_app(self):
        """An app with a resolvable executable and no blocking factors is allowed."""
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            with patch.object(
                self.preflight, "resolve_executable", return_value=path
            ):
                app = {
                    "name": "Notepad",
                    "app_id": "Microsoft.Notepad",
                    "login_required": False,
                    "logged_in": None,
                    "resources_available": True,
                }
                result: PreflightResult = self.preflight.check_application(app)
                # Executable resolves and passes launch-destination validation;
                # no manifest found => allowed with availability "available".
                self.assertTrue(result.allowed)
                self.assertEqual(result.availability, "available")
        finally:
            os.unlink(path)

    def test_blocked_name(self):
        """An app with a blocked name should not be allowed."""
        # "Task Scheduler" is explicitly in BLOCKED_NAME_PARTS.
        app = {
            "name": "Task Scheduler",
            "app_id": "Microsoft.TaskScheduler",
            "login_required": False,
            "logged_in": None,
            "resources_available": True,
        }
        result: PreflightResult = self.preflight.check_application(app)
        self.assertFalse(result.allowed)
        self.assertEqual(result.availability, "unknown")

    def test_login_required_not_logged_in(self):
        """App requiring login and not logged in should be blocked."""
        app = {
            "name": "Calculator",
            "app_id": "Microsoft.Calc",
            "login_required": True,
            "logged_in": False,
            "resources_available": True,
        }
        result: PreflightResult = self.preflight.check_application(app)
        self.assertFalse(result.allowed)
        self.assertEqual(result.availability, "unknown")


if __name__ == "__main__":
    unittest.main()