# auth_backend.py
from django.contrib.auth.backends import ModelBackend

class EmployeeStatusBackend(ModelBackend):
    def user_can_authenticate(self, user):
        try:
            return user.employee.status == "Active"
        except:
            return False
