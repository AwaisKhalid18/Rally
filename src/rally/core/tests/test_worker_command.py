"""The worker as the demo and CI actually run it - plan.md S2 AC2."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from rally.modules.identity.api import facade as identity
from rally.modules.notification.api import facade as notification

EMAIL = "worker-command@example.com"
PASSWORD = "longenough"


class RunWorkerTests(TestCase):
    def setUp(self):
        self.adapter = notification.RecordingEmailAdapter()
        previous = notification.set_email_adapter(self.adapter)
        self.addCleanup(notification.set_email_adapter, previous)

    def _run(self) -> str:
        out = StringIO()
        call_command("run_worker", "--once", stdout=out)
        return out.getvalue()

    def test_one_pass_dispatches_what_registration_queued(self):
        identity.register(EMAIL, PASSWORD)

        output = self._run()

        self.assertIn("claimed=1 sent=1", output)
        self.assertEqual(self.adapter.sent[0]["to"], EMAIL)

    def test_a_pass_with_nothing_due_is_quiet_and_harmless(self):
        output = self._run()

        self.assertIn("worker started", output)
        self.assertNotIn("claimed=", output)
        self.assertEqual(self.adapter.sent, [])

    def test_the_worker_prints_no_contact_address(self):
        identity.register(EMAIL, PASSWORD)
        self.assertNotIn(EMAIL, self._run())
