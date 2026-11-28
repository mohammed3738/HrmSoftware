from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render

from .models import Employee
from .utils.permissions import department_member_ids, has_feature_permission


@login_required
def org_chart(request):
    user = request.user
    own = getattr(user, "employee_profile", None)
    browse = user.is_staff or user.is_superuser or has_feature_permission(user, "employee_records", "view")
    if not own and not browse:
        raise PermissionDenied

    people = Employee.objects.filter(status="Active").only(
        "id", "company_id", "employee_code", "first_name", "last_name", "photo",
        "designation", "department", "reporting_person_id", "manager_id",
    ).order_by("first_name", "last_name", "pk")
    selected_id = request.GET.get("employee")
    employee = own
    if selected_id:
        if not browse and selected_id != str(getattr(own, "pk", "")):
            raise PermissionDenied
        if not selected_id.isascii() or not selected_id.isdecimal() or len(selected_id) > 18:
            raise Http404
        if not own or selected_id != str(own.pk):
            employee = people.filter(pk=int(selected_id)).first()
            if employee is None:
                raise Http404
    elif employee is None:
        employee = people.filter(reporting_person=None, manager=None).first() or people.first()

    context = {"browse": browse, "subject": employee, "choices": people if browse else ()}
    if not employee:
        return render(request, "employee/org_chart.html", context)

    company = people.filter(company_id=employee.company_id) if employee.company_id else people.none()
    company = company.filter(Q(pk__in=department_member_ids(employee)) |
                             Q(pk__in=[employee.pk, employee.manager_id, employee.reporting_person_id]))
    context["choices"] = company if browse else ()
    members = {person.pk: person for person in company}
    members[employee.pk] = employee
    reports = defaultdict(list)
    parent_of = {}
    for person in members.values():
        parent = person.reporting_person_id or person.manager_id
        if parent in members and parent != person.pk:
            parent_of[person.pk] = parent
            reports[parent].append(person)

    path = [employee.pk]
    visited = set(path)
    while path[-1] in parent_of:
        parent = parent_of[path[-1]]
        if parent in visited:
            context["cycle"] = True
            break
        visited.add(parent)
        path.append(parent)

    # Expand the selected reporting line. Sibling branches stay compact.
    def node(person, children=()):
        return {"person": person, "children": children, "count": len(reports[person.pk]),
                "on_path": person.pk in visited}

    branch = node(employee, [node(person) for person in reports[employee.pk] if person.pk not in visited])
    for child_id, parent_id in zip(path, path[1:]):
        children = [branch if person.pk == child_id else node(person)
                    for person in reports[parent_id] if person.pk == child_id or person.pk not in visited]
        branch = node(members[parent_id], children)

    # Emit nested-list boundaries iteratively so long reporting lines do not
    # depend on Python or template recursion limits.
    events = []
    stack = [("node", branch)]
    while stack:
        kind, value = stack.pop()
        events.append((kind, value))
        if kind == "node":
            stack.append(("end_node", None))
            if value["children"]:
                stack.append(("end_children", None))
                stack.extend(("node", child) for child in reversed(value["children"]))
                stack.append(("children", None))
    chart_ids = {value["person"].pk for kind, value in events if kind == "node"}
    context.update(events=events,
                   additional_manager=members.get(employee.manager_id) if employee.manager_id not in chart_ids else None,
                   remaining_team=[person for pk, person in members.items()
                                   if pk not in chart_ids and pk != employee.manager_id])
    return render(request, "employee/org_chart.html", context)
