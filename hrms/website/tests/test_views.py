import json
from datetime import date
from django.test import TestCase, Client
from website.services import create_advance
from website.tests.factories import create_test_employee


class TestAdvanceViews(TestCase):

    def setUp(self):
        self.client = Client()
        self.emp = create_test_employee()
        self.advance = create_advance(self.emp, 1000, 4, start_date=date(2025, 1, 1))

    def test_list_page(self):
        response = self.client.get("/advances/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "₹1000")

    def test_detail_page(self):
        response = self.client.get(f"/advances/{self.advance.id}/")
        self.assertEqual(response.status_code, 200)

    def test_pay_advance_ajax(self):
        url = f"/advances/{self.advance.id}/pay/"
        response = self.client.post(url, {"amount": 200}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["outstanding"], 800)

    def test_skip_month_ajax(self):
        url = f"/advances/{self.advance.id}/skip/"
        response = self.client.post(
            url,
            {"due_month": "2025-02-01"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data["success"])
        self.assertGreater(len(data["schedules"]), 4)
