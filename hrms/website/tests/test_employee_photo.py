"""
Employee photo upload on the employee form.

Run with: python manage.py test website.tests.test_employee_photo
"""
import io
import os
import shutil
import tempfile
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from website.forms import EmployeeForm
from website.models import Company, Employee

MEDIA = tempfile.mkdtemp(prefix="hrms_test_media_")


def image_file(fmt="PNG", size=(40, 40), name="me.png", noise=False):
    img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)) if noise else Image.new("RGB", size, "red")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


@override_settings(MEDIA_ROOT=MEDIA)
class EmployeePhotoTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.company = Company.objects.create(name="Photo Co", short_name="PHC")
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr.", first_name="Pic", last_name="Ture",
            gender="Male", employee_code="PH001", status="Active", date_of_joining=date(2020, 1, 1),
        )

    def _form(self, files, extra=None):
        data = {k: v for k, v in model_to_dict(self.employee).items() if v is not None and k != "photo"}
        data.update(extra or {})
        return EmployeeForm(data, files, instance=self.employee)

    def test_valid_photo_is_saved_under_a_random_name(self):
        form = self._form({"photo": image_file()})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.photo.name.startswith("employees/photos/"))
        self.assertNotIn("PH001", self.employee.photo.name)
        self.assertTrue(self.employee.photo.name.endswith(".png"))

    def test_rejects_too_large(self):
        big = image_file(size=(1200, 1200), noise=True)
        self.assertGreater(big.size, 2 * 1024 * 1024)
        form = self._form({"photo": big})
        self.assertFalse(form.is_valid())
        self.assertIn("2 MB", str(form.errors["photo"]))

    def test_rejects_other_image_formats(self):
        form = self._form({"photo": image_file(fmt="GIF", name="anim.gif")})
        self.assertFalse(form.is_valid())
        self.assertIn("JPG, PNG or WEBP", str(form.errors["photo"]))

    def test_rejects_non_images(self):
        fake = SimpleUploadedFile("evil.png", b"<script>alert(1)</script>", content_type="image/png")
        form = self._form({"photo": fake})
        self.assertFalse(form.is_valid())

    def test_remove_photo(self):
        form = self._form({"photo": image_file()})
        form.is_valid()
        form.save()
        form = self._form({}, extra={"photo-clear": "on"})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.photo)

    def test_photo_shown_on_detail_and_list(self):
        self.employee.photo = image_file()
        self.employee.save()
        admin = User.objects.create_superuser("ph_admin", "ph@test.com", "pass12345")
        client = Client()
        client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")
        url = self.employee.photo.url
        self.assertContains(client.get(reverse("employee_detail", args=[self.employee.pk])), url)
        self.assertContains(client.get(reverse("employee_create")), url)
        edit = client.get(reverse("employee_edit", args=[self.employee.pk]))
        self.assertContains(edit, 'name="photo"')
        self.assertContains(edit, 'name="photo-clear"')
