"""Declarative list filters against Trusts relational tables.

Trusts evaluates User.has_perm(perm, obj) in SQL/ORM for a single object or
as an all-must-match check on a QuerySet. It does not ship a filter that
returns "objects this user may see". This helper is that missing list filter:
it JOINs the same trustee / group / role tables the backend reads.

It is not a Python predicate over each row (no list-comprehension of
has_perm). Paginator must wrap the returned QuerySet, not the unfiltered
table.
"""

from django.contrib.auth.models import AnonymousUser
from django.db.models import Q, QuerySet

from .grants import project_permission
from .models import Project


def projects_with_perm(user, codename) -> QuerySet[Project]:
    # Match User.has_perm: anonymous and inactive principals are denied.
    # Superuser short-circuit on has_perm is a Django limitation (documented).
    if (
        user is None
        or isinstance(user, AnonymousUser)
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return Project.objects.none()

    perm = project_permission(codename)
    return (
        Project.objects.filter(
            Q(trust__trustees__entity=user, trust__trustees__permission=perm)
            | Q(trust__groups__user=user, trust__groups__permissions=perm)
            | Q(
                trust__groups__user=user,
                trust__groups__roles__permissions=perm,
            )
        )
        .distinct()
        .order_by("title", "pk")
    )


def readable_projects(user) -> QuerySet[Project]:
    return projects_with_perm(user, "read_project")


def editable_projects(user) -> QuerySet[Project]:
    return projects_with_perm(user, "change_project")
