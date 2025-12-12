from datetime import date
from django.test import TestCase
from website.services import create_advance, apply_payment, skip_month
from website.tests.factories import create_test_employee

class TestAdvanceServices(TestCase):

    def setUp(self):
        self.emp = create_test_employee()

    def test_create_advance_creates_correct_schedule(self):
        adv = create_advance(self.emp, 1000, 4, start_date=date(2025, 1, 1))
        self.assertEqual(adv.advance_amount, 1000)
        self.assertEqual(adv.outstanding_amount, 1000)

        schedules = adv.schedules.order_by("due_month")
        self.assertEqual(len(schedules), 4)
        self.assertEqual(
            [s.scheduled_amount for s in schedules],
            [250, 250, 250, 250]
        )

    def test_partial_payment_updates_schedule(self):
        adv = create_advance(self.emp, 1000, 4, start_date=date(2025, 1, 1))
        apply_payment(adv, 100)
        adv.refresh_from_db()

        schedules = adv.schedules.order_by("due_month")

        # Because outstanding=900 spread across 4 pending months => 225 each
        self.assertEqual(schedules[0].scheduled_amount, 225)
        self.assertEqual(schedules[1].scheduled_amount, 225)
        self.assertEqual(schedules[2].scheduled_amount, 225)
        self.assertEqual(schedules[3].scheduled_amount, 225)

    def test_skip_month_extends_tenure(self):
        adv = create_advance(self.emp, 1000, 4, start_date=date(2025, 1, 1))
        skip_month(adv, date(2025, 2, 1))

        schedules = adv.schedules.order_by("due_month")
        self.assertEqual(len(schedules), 5)
        self.assertEqual(schedules[1].status, "skipped")

    def test_overpayment_reduces_tenure(self):
        adv = create_advance(self.emp, 1000, 4, start_date=date(2025, 1, 1))
        apply_payment(adv, 500)

        adv.refresh_from_db()
        self.assertEqual(adv.outstanding_amount, 500)

    def test_full_settlement_closes_advance(self):
        adv = create_advance(self.emp, 1000, 4, start_date=date(2025, 1, 1))
        apply_payment(adv, 1000)

        adv.refresh_from_db()
        self.assertEqual(adv.outstanding_amount, 0)
        self.assertEqual(adv.status, "completed")
