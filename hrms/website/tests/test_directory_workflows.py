from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from website.models import Branch, Company, Department, EmployeeChangeRequest, Feature, RoleFeaturePermission
from website.tests.test_employee_search_autocomplete import make_employee


class DirectoryWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("directory-review", is_staff=True)
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_duplicate_company_returns_bound_form(self):
        Company.objects.create(short_name="ORG", name="Existing")
        response = self.client.post(reverse("create-company"), {
            "name": "New name", "short_name": "ORG", "email": "hr@example.com",
            "address": "Main office", "phone": "0100", "status": "active",
        })
        self.assertEqual(response.status_code, 200)
        form = response.context["company_form"]
        self.assertIn("short_name", form.errors)
        self.assertEqual(form["address"].value(), "Main office")
        self.assertEqual(Company.objects.filter(short_name="ORG").count(), 1)

    def test_branch_name_required_and_address_optional(self):
        url = reverse("create-branch")
        response = self.client.post(url, {"branch_name": " ", "branch_address": "Suite 1"})
        self.assertIn("branch_name", response.context["branch_form"].errors)
        self.assertFalse(Branch.objects.exists())
        self.assertRedirects(self.client.post(url, {"branch_name": "South"}), url)
        self.assertTrue(Branch.objects.filter(branch_name="South").exists())

    def test_department_search_combines_query_with_archive_filter(self):
        Department.objects.bulk_create([
            Department(name="Customer Support"), Department(name="Operations"),
            Department(name="Former Support", is_active=False),
        ])
        response = self.client.get(reverse("department-list"), {"q": "support", "show": "archived"})
        self.assertEqual([dept.name for dept in response.context["departments"]], ["Former Support"])
        self.assertContains(response, "q=support")

    def test_read_only_directory_hides_write_controls(self):
        role = Group.objects.create(name="Directory Reader")
        RoleFeaturePermission.objects.create(role=role, feature=Feature.objects.get(key="employee_records"), can_view=True)
        reader = User.objects.create_user("directory-reader")
        reader.groups.add(role)
        self.client.force_login(reader, backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get(reverse("employee_list"))
        self.assertContains(response, 'id="employee-rows-data"')
        self.assertNotContains(response, 'data-bs-target="#employeeModal"')
        self.assertNotContains(response, 'data-bs-target="#importEmployeeModal"')
        self.assertNotContains(response, 'id="bulkToolbar"')

    def test_approval_search_reaches_records_beyond_old_limit(self):
        company = Company.objects.create(short_name="APR", name="Approvals")
        employee = make_employee(company, "APR100")
        first = EmployeeChangeRequest.objects.create(employee=employee)
        EmployeeChangeRequest.objects.bulk_create([EmployeeChangeRequest(employee=employee) for _ in range(200)])
        EmployeeChangeRequest.objects.create(employee=employee, status="rejected")
        response = self.client.get(reverse("employee_change_requests"), {
            "q": "APR100", "status": "pending", "page": 5,
        })
        self.assertEqual(response.context["page"].paginator.count, 201)
        self.assertEqual([change.pk for change in response.context["change_requests"]], [first.pk])
        self.assertContains(response, "Page 5 of 5")

    def test_invalid_branch_edit_keeps_staff_in_the_directory(self):
        branch = Branch.objects.create(branch_name="East")
        response = self.client.post(reverse("edit_branch", args=[branch.pk]), {"branch_name": ""})
        self.assertTemplateUsed(response, "branch/create-branch.html")
        self.assertIn("branch_name", response.context["edit_form"].errors)
        branch.refresh_from_db()
        self.assertEqual(branch.branch_name, "East")
