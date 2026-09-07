"""Application helpers around Trusts tables.

Trusts 1.0.0.dev0 has no Content.grant / Content.revoke / QuerySet.permitted
API. The historical permission-UI branch called those helpers; they lived on
an unmerged trusts checkout and are not in modernized master. These wrappers
write TrustUserPermission and Trust.groups rows only.

public-readers is a system-maintained audience: every User row is kept in
that group so Trusts can grant public read through ordinary group membership.
Forms and admin must not be able to drop it; see signals and UserAdmin.
"""

import threading

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.utils import OperationalError, ProgrammingError

_enrolling = threading.local()

from trusts.models import TrustUserPermission

from .models import Project

PUBLIC_GROUP_NAME = "public-readers"
READ = "read_project"
CHANGE = "change_project"


def project_permission(codename):
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Project),
        codename=codename,
    )


def grant_user(project, user, *codenames):
    """Grant trustee rows on the project's trust (object-level via Trusts)."""
    for codename in codenames:
        TrustUserPermission.objects.get_or_create(
            trust=project.trust,
            entity=user,
            permission=project_permission(codename),
        )


def revoke_user(project, user, *codenames):
    """Remove trustee rows. Empty codenames removes every grant for the user."""
    qs = TrustUserPermission.objects.filter(trust=project.trust, entity=user)
    if codenames:
        qs = qs.filter(permission__codename__in=codenames)
    qs.delete()


def public_readers_group():
    group, _ = Group.objects.get_or_create(name=PUBLIC_GROUP_NAME)
    group.permissions.add(project_permission(READ))
    return group


def enroll_in_public_readers(user):
    """Attach one account to public-readers so Trusts group grants apply."""
    if user is None or not getattr(user, "pk", None):
        return
    if getattr(_enrolling, "busy", False):
        return
    _enrolling.busy = True
    try:
        public_readers_group().user_set.add(user)
    except (ProgrammingError, OperationalError, Permission.DoesNotExist, ContentType.DoesNotExist):
        # Migrations / early User inserts before Project permissions exist.
        return
    finally:
        _enrolling.busy = False


def sync_public_readers():
    """Enroll every existing user. Complements the post_save signal for new ones."""
    try:
        group = public_readers_group()
    except (ProgrammingError, OperationalError, Permission.DoesNotExist, ContentType.DoesNotExist):
        return None
    User = get_user_model()
    group.user_set.add(*User.objects.all())
    return group


def is_public(project):
    return project.trust.groups.filter(name=PUBLIC_GROUP_NAME).exists()


def set_public(project, make_public):
    """Visibility is trust-scoped: attach or detach the public-readers group.

    Trust.trust / Trust.settlor are readonly after create, so a project cannot
    be moved to another trust. Public read is modeled as a group grant on the
    existing trust — the same tables has_perm reads.
    """
    group = public_readers_group()
    if make_public:
        project.trust.groups.add(group)
    else:
        project.trust.groups.remove(group)


def trustee_rows(project):
    return (
        TrustUserPermission.objects.filter(trust=project.trust)
        .select_related("entity", "permission")
        .order_by("entity__username", "permission__codename")
    )
