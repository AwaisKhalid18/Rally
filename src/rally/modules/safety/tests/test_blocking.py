"""M6 blocking, unblocking and reporting - plan.md S12 AC1, AC2, AC3, AC4, AC5.

These are M6's own tests. They reach other modules only through facades, and the one
thing they must never do is import M5 into M6's production code - the contract in
`.importlinter` enforces that, and `test_wiring.py` proves the port is bound.
"""
from django.test import TestCase

from rally.modules.identity.api import facade as identity
from rally.modules.safety.api import facade as safety
from rally.modules.safety.internal.models import Block, Report, ReportCategory

PASSWORD = "longenough"


class SafetyCase(TestCase):
    def setUp(self):
        self.first = identity.register("first@example.com", PASSWORD).account_id
        self.second = identity.register("second@example.com", PASSWORD).account_id
        self.third = identity.register("third@example.com", PASSWORD).account_id


class BlockingTests(SafetyCase):
    """AC1 - the rule M6 publishes."""

    def test_blocking_records_it(self):
        result = safety.block(self.first, self.second)

        self.assertTrue(result.ok, result.error)
        self.assertTrue(
            Block.objects.filter(
                blocker_account_id=self.first, blocked_account_id=self.second
            ).exists()
        )

    def test_the_rule_is_symmetric_whichever_way_it_is_asked(self):
        """PRD 12.5: the pair is hidden from each other, both directions."""
        safety.block(self.first, self.second)

        self.assertTrue(safety.is_blocked_between(self.first, self.second))
        self.assertTrue(safety.is_blocked_between(self.second, self.first))

    def test_it_says_nothing_about_a_pair_that_is_not_blocked(self):
        safety.block(self.first, self.second)

        self.assertFalse(safety.is_blocked_between(self.first, self.third))

    def test_you_cannot_block_yourself(self):
        result = safety.block(self.first, self.first)

        self.assertEqual(result.error, safety.CANNOT_BLOCK_YOURSELF)
        self.assertEqual(Block.objects.count(), 0)

    def test_blocking_twice_is_refused(self):
        safety.block(self.first, self.second)

        result = safety.block(self.first, self.second)

        self.assertEqual(result.error, safety.ALREADY_BLOCKED)
        self.assertEqual(Block.objects.count(), 1)

    def test_the_other_player_may_still_place_their_own_block(self):
        """The row is directed even though the effect is not: both may block."""
        safety.block(self.first, self.second)

        self.assertTrue(safety.block(self.second, self.first).ok)
        self.assertEqual(Block.objects.count(), 2)


class UnblockingTests(SafetyCase):
    """AC3."""

    def test_unblocking_removes_your_own_block(self):
        safety.block(self.first, self.second)

        result = safety.unblock(self.first, self.second)

        self.assertTrue(result.ok, result.error)
        self.assertFalse(safety.is_blocked_between(self.first, self.second))

    def test_you_cannot_unblock_a_block_you_did_not_place(self):
        safety.block(self.first, self.second)

        result = safety.unblock(self.second, self.first)

        self.assertEqual(result.error, safety.NOT_BLOCKED)
        self.assertTrue(safety.is_blocked_between(self.first, self.second))

    def test_unblocking_what_was_never_blocked_says_the_same(self):
        self.assertEqual(safety.unblock(self.first, self.third).error, safety.NOT_BLOCKED)

    def test_the_pair_stays_hidden_while_the_other_block_remains(self):
        safety.block(self.first, self.second)
        safety.block(self.second, self.first)

        safety.unblock(self.first, self.second)

        self.assertTrue(
            safety.is_blocked_between(self.first, self.second),
            "one side's block still hides the pair",
        )


class TheBlockedListTests(SafetyCase):
    """AC3 - the list unblocking happens from."""

    def test_it_holds_the_players_you_blocked(self):
        safety.block(self.first, self.second)
        safety.block(self.first, self.third)

        blocked = safety.list_blocked(self.first)

        self.assertEqual(
            sorted(row.blocked_account_id for row in blocked), sorted([self.second, self.third])
        )

    def test_it_never_shows_that_somebody_blocked_you(self):
        """Being told you were blocked would defeat the point (PRD 12.5)."""
        safety.block(self.second, self.first)

        self.assertEqual(safety.list_blocked(self.first), [])

    def test_it_is_empty_before_you_block_anybody(self):
        self.assertEqual(safety.list_blocked(self.first), [])

    def test_unblocking_removes_the_row_from_it(self):
        safety.block(self.first, self.second)

        safety.unblock(self.first, self.second)

        self.assertEqual(safety.list_blocked(self.first), [])


class ReportingTests(SafetyCase):
    """AC4."""

    def test_a_report_with_a_category_is_stored(self):
        result = safety.report(self.first, self.second, ReportCategory.HARASSMENT)

        self.assertTrue(result.ok, result.errors)
        row = Report.objects.get()
        self.assertEqual(row.reporter_account_id, self.first)
        self.assertEqual(row.reported_account_id, self.second)
        self.assertEqual(row.category, ReportCategory.HARASSMENT)

    def test_the_details_are_optional(self):
        self.assertTrue(safety.report(self.first, self.second, ReportCategory.OTHER).ok)
        self.assertEqual(Report.objects.get().details, "")

    def test_the_details_are_kept_when_given(self):
        safety.report(self.first, self.second, ReportCategory.OTHER, "They never turned up.")

        self.assertEqual(Report.objects.get().details, "They never turned up.")

    def test_every_offered_category_is_accepted(self):
        """The form offers exactly what M6 accepts, so each one must work."""
        for value, _ in safety.REPORT_CATEGORIES:
            Report.objects.all().delete()

            result = safety.report(self.first, self.second, value)

            self.assertTrue(result.ok, f"{value}: {result.errors}")

    def test_a_category_is_required(self):
        result = safety.report(self.first, self.second, "")

        self.assertEqual(result.errors, {"category": safety.CATEGORY_REQUIRED})
        self.assertEqual(Report.objects.count(), 0)

    def test_a_category_that_is_not_offered_is_refused(self):
        result = safety.report(self.first, self.second, "something-else")

        self.assertEqual(result.errors, {"category": safety.CATEGORY_UNKNOWN})

    def test_you_cannot_report_yourself(self):
        result = safety.report(self.first, self.first, ReportCategory.OTHER)

        self.assertEqual(result.errors["reported"], safety.CANNOT_REPORT_YOURSELF)
        self.assertEqual(Report.objects.count(), 0)

    def test_details_at_the_limit_are_accepted(self):
        """BVA on the one real bound this has."""
        details = "x" * safety.REPORT_DETAILS_MAX_LENGTH

        self.assertTrue(safety.report(self.first, self.second, ReportCategory.OTHER, details).ok)

    def test_details_one_character_over_the_limit_are_refused(self):
        details = "x" * (safety.REPORT_DETAILS_MAX_LENGTH + 1)

        result = safety.report(self.first, self.second, ReportCategory.OTHER, details)

        self.assertEqual(result.errors, {"details": safety.DETAILS_TOO_LONG})

    def test_reporting_the_same_player_twice_is_allowed(self):
        """Nothing in the PRD limits it, and a second incident is a second report."""
        safety.report(self.first, self.second, ReportCategory.HARASSMENT)
        safety.report(self.first, self.second, ReportCategory.OTHER)

        self.assertEqual(Report.objects.count(), 2)

    def test_reporting_does_not_block(self):
        """Two separate actions: the PRD never couples them."""
        safety.report(self.first, self.second, ReportCategory.HARASSMENT)

        self.assertFalse(safety.is_blocked_between(self.first, self.second))

    def test_m6_publishes_no_way_to_read_a_report_back(self):
        """AC4 - 'reporters cannot read reports'.

        Asserted against the facade itself: there is no operation to call. A report a
        player could read back would become a channel between the two of them.
        """
        safety.report(self.first, self.second, ReportCategory.HARASSMENT)

        # Every callable operation the facade publishes about reports. `report` writes
        # one; anything else would be a way to get one back.
        operations = [
            name
            for name in dir(safety)
            if not name.startswith("_")
            and "report" in name.lower()
            and callable(getattr(safety, name))
            and not isinstance(getattr(safety, name), type)
        ]

        self.assertEqual(
            operations, ["report"], f"M6 publishes more than a writer: {operations}"
        )
