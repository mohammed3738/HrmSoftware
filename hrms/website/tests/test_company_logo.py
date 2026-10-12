"""
Company logo: uploaded when adding or editing a company, shown in the
company list and at the top of salary slips (screen and PDF).

Run with: python manage.py test website.tests.test_company_logo
"""
import io
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from website.models import Company, Employee, PayrollRecord, PayrollRun

MEDIA = tempfile.mkdtemp(prefix="hrms_test_media_")


def png(name="logo.png", fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", (120, 40), "navy").save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


@override_settings(MEDIA_ROOT=MEDIA)
class CompanyLogoTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        admin = User.objects.create_user(username="logo_sa", password="pass12345")
        admin.groups.add(Group.objects.get(name="Super Admin"))
        self.client = Client()
        self.client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")

    def _add(self, logo):
        return self.client.post(reverse("create-company"), {
            "short_name": "LGO", "name": "Logo Co", "address": "Addr", "phone": "1",
            "email": "l@test.com", "status": "active", "logo": logo,
        })

    def test_add_company_with_logo(self):
        self._add(png())
        company = Company.objects.get(short_name="LGO")
        self.assertTrue(company.logo.name.startswith("company_logos/"))
        self.assertContains(self.client.get(reverse("create-company")), company.logo.url)

    def test_rejects_non_image_logo(self):
        self._add(SimpleUploadedFile("evil.png", b"<script>", content_type="image/png"))
        self.assertFalse(Company.objects.filter(short_name="LGO").exists())

    def test_rejects_unsupported_format(self):
        self._add(png("logo.gif", fmt="GIF"))
        self.assertFalse(Company.objects.filter(short_name="LGO").exists())

    def test_edit_company_adds_logo(self):
        company = Company.objects.create(short_name="EDL", name="Edit Logo", phone="1", email="e@test.com",
                                         address="Addr", status="active")
        self.client.post(reverse("edit_company", args=[company.pk]), {
            "short_name": "EDL", "name": "Edit Logo", "phone": "1", "email": "e@test.com",
            "address": "Addr", "status": "active", "logo": png(),
        })
        company.refresh_from_db()
        self.assertTrue(company.logo)

    def test_logo_on_salary_slip_and_pdf(self):
        self._add(png())
        company = Company.objects.get(short_name="LGO")
        emp = Employee.objects.create(company=company, first_name="Pay", last_name="Slip", employee_code="LG1",
                                      status="Active")
        run = PayrollRun.objects.create(company=company, month=date(2026, 1, 1), start_date=date(2026, 1, 1),
                                        end_date=date(2026, 1, 31), status=PayrollRun.STATUS_FINALIZED)
        rec = PayrollRecord.objects.create(payroll=run, employee=emp, employee_code="LG1", employee_name="Pay Slip",
                                           total_days=31, basic_processed=Decimal(1000), net_salary=Decimal(1000))
        url = reverse("salary-slip", args=[rec.pk])
        self.assertContains(self.client.get(url), company.logo.url)
        pdf = self.client.get(url + "?format=pdf")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertIn(b"/Image", pdf.content)  # the logo is embedded in the PDF
        statement = self.client.get(reverse("salary-slip-statement"), {"ids": [rec.pk], "format": "pdf"})
        self.assertIn(b"/Image", statement.content)
