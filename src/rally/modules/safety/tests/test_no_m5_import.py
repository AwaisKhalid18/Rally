"""M6 holds no import of M5 - plan.md S12 AC5, rule 15.

The real guard is the `safety-depends-on-nothing` contract in `.importlinter`, which
names `rally.modules.invitations` in M6's forbidden list and runs in CI. This states the
same thing in the test suite, where a reader of M6 will come across it, and it reads
M6's own internals - which only M6's tests may do (rule 2).
"""
from django.test import SimpleTestCase

from rally.modules.safety.api import facade, ports
from rally.modules.safety.internal import blocking, models

M5 = "rally.modules.invitations"


class NoImportOfM5Tests(SimpleTestCase):
    def test_no_m6_module_has_m5_in_its_namespace(self):
        for module in (facade, ports, blocking, models):
            leaked = sorted(
                f"{name} -> {getattr(value, '__name__', value)}"
                for name, value in vars(module).items()
                if getattr(value, "__module__", "").startswith(M5)
                or getattr(value, "__name__", "").startswith(M5)
            )

            self.assertEqual(leaked, [], f"{module.__name__} imports M5: {leaked}")

    def test_the_cascade_reaches_m5_through_the_port_instead(self):
        """What M6 does hold is the port it declares itself."""
        self.assertIs(blocking.pending_invitation_canceller, ports.pending_invitation_canceller)
        self.assertEqual(ports.PENDING_INVITATION_CANCELLER, "PendingInvitationCanceller")
