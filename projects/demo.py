"""Idempotent demo seed: users, groups/orgs, trusts, and owned projects."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.utils.text import slugify

from trusts.models import Role, Trust

from .grants import (
    CHANGE,
    PUBLIC_GROUP_NAME,
    READ,
    grant_user,
    public_readers_group,
    set_public,
)
from .models import Project

User = get_user_model()

DEMO_USERS = ("alice", "bob", "carol", "dave")
ACME_GROUP = "acme-staff"
PASSWORD = getattr(settings, "DEMO_PASSWORD", "demo")


def ensure_user(username):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@example.com"},
    )
    if created or not user.check_password(PASSWORD):
        user.set_password(PASSWORD)
        user.save()
    return user


def ensure_trust(settlor, title):
    trust, _ = Trust.objects.get_or_create(
        settlor=settlor,
        title=title,
        defaults={"trust": Trust.objects.get_root()},
    )
    return trust


def ensure_project(trust, title, description, owner, extra_readers=(), public=False):
    slug = slugify(title)
    project, created = Project.objects.get_or_create(
        slug=slug,
        defaults={"title": title, "description": description, "trust": trust},
    )
    if created:
        # trust is readonly after create; get_or_create already set it.
        pass
    grant_user(project, owner, READ, CHANGE)
    for reader in extra_readers:
        grant_user(project, reader, READ)
    set_public(project, public)
    return project


def seed_demo():
    call_command("create_trust_root", verbosity=0)
    call_command("update_roles_permissions", verbosity=0)

    users = {name: ensure_user(name) for name in DEMO_USERS}
    alice, bob, carol, dave = (users[n] for n in DEMO_USERS)

    public_group = public_readers_group()
    for user in users.values():
        user.groups.add(public_group)

    acme_group, _ = Group.objects.get_or_create(name=ACME_GROUP)
    acme_group.user_set.add(carol)
    Role.objects.get(name="reader").groups.add(acme_group)

    alice_private = ensure_trust(alice, "project:alice-private-notes")
    shared = ensure_trust(alice, "project:shared-roadmap")
    changelog = ensure_trust(alice, "project:public-changelog")
    acme = ensure_trust(alice, "org:acme")
    dave_notes = ensure_trust(dave, "project:dave-notes")

    acme.groups.add(acme_group)

    projects = {
        "alice-private-notes": ensure_project(
            alice_private,
            "Alice Private Notes",
            "Only Alice has trustee grants.",
            alice,
        ),
        "shared-roadmap": ensure_project(
            shared,
            "Shared Roadmap",
            "Alice can edit. Bob has a read trustee grant.",
            alice,
            extra_readers=(bob,),
        ),
        "public-changelog": ensure_project(
            changelog,
            "Public Changelog",
            "Read is granted through the public-readers group on this trust.",
            alice,
            public=True,
        ),
        "acme-handbook": ensure_project(
            acme,
            "Acme Handbook",
            "Carol reads via acme-staff + the reader role on the Acme trust.",
            alice,
        ),
        "dave-notes": ensure_project(
            dave_notes,
            "Dave Notes",
            "Dave's personal project. Isolated from Alice's organization.",
            dave,
        ),
    }
    return {
        "users": users,
        "projects": projects,
        "groups": {
            PUBLIC_GROUP_NAME: public_group,
            ACME_GROUP: acme_group,
        },
        "trusts": {
            "acme": acme,
            "alice_private": alice_private,
            "shared": shared,
            "changelog": changelog,
            "dave_notes": dave_notes,
        },
    }
