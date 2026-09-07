from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import QuerySet
from django.forms import modelform_factory
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from trusts.models import Trust, TrustUserPermission

from .demo import seed_demo
from .grants import CHANGE, PUBLIC_GROUP_NAME, READ, grant_user, is_public, set_public
from .models import Project
from .query import editable_projects, readable_projects

User = get_user_model()


class SeededTrustsDemoTests(TestCase):
    def setUp(self):
        self.data = seed_demo()
        self.users = self.data["users"]
        self.projects = self.data["projects"]

    def _titles(self, user):
        return list(readable_projects(user).values_list("title", flat=True))

    def test_seeded_users_groups_and_owned_objects(self):
        self.assertEqual(set(self.users), {"alice", "bob", "carol", "dave"})
        self.assertGreaterEqual(Project.objects.count(), 5)
        self.assertTrue(Trust.objects.filter(title="org:acme").exists())
        self.assertTrue(self.users["carol"].groups.filter(name="acme-staff").exists())

    def test_seeded_readable_titles(self):
        self.assertEqual(
            self._titles(self.users["alice"]),
            [
                "Acme Handbook",
                "Alice Private Notes",
                "Public Changelog",
                "Shared Roadmap",
            ],
        )
        self.assertEqual(
            self._titles(self.users["bob"]),
            ["Public Changelog", "Shared Roadmap"],
        )
        self.assertEqual(
            self._titles(self.users["carol"]),
            ["Acme Handbook", "Public Changelog"],
        )
        self.assertEqual(
            self._titles(self.users["dave"]),
            ["Dave Notes", "Public Changelog"],
        )

    def test_list_filtering_and_direct_access_agree(self):
        for user in self.users.values():
            listed = set(readable_projects(user).values_list("pk", flat=True))
            self.client.force_login(user)
            for project in Project.objects.all():
                allowed = user.has_perm("projects.read_project", project)
                self.assertEqual(
                    project.pk in listed,
                    allowed,
                    f"{user.username} list/direct disagree on {project.title}",
                )
                response = self.client.get(project.get_absolute_url())
                if allowed:
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, project.title)
                else:
                    self.assertEqual(response.status_code, 403)

    def test_list_view_uses_filtered_titles(self):
        self.client.force_login(self.users["dave"])
        response = self.client.get(reverse("project-list"))
        self.assertContains(response, "Dave Notes")
        self.assertContains(response, "Public Changelog")
        self.assertNotContains(response, "Alice Private Notes")
        self.assertNotContains(response, "Acme Handbook")
        self.assertNotContains(response, "Shared Roadmap")

    def test_create_object_grants_owner_read_and_change(self):
        self.client.force_login(self.users["bob"])
        response = self.client.post(
            reverse("project-create"),
            {"title": "Bob Scratchpad", "description": "created in test"},
        )
        project = Project.objects.get(slug="bob-scratchpad")
        self.assertRedirects(response, project.get_absolute_url())
        bob = User.objects.get(username="bob")
        self.assertTrue(bob.has_perm("projects.read_project", project))
        self.assertTrue(bob.has_perm("projects.change_project", project))
        self.assertFalse(self.users["alice"].has_perm("projects.read_project", project))

    def test_change_visibility_then_other_user_view(self):
        notes = self.projects["alice-private-notes"]
        dave = self.users["dave"]
        self.assertFalse(dave.has_perm("projects.read_project", notes))

        self.client.force_login(self.users["alice"])
        response = self.client.post(
            reverse("project-visibility", kwargs={"pk": notes.pk}),
            {"is_public": "on"},
        )
        self.assertRedirects(response, notes.get_absolute_url())
        notes = Project.objects.get(pk=notes.pk)
        self.assertTrue(is_public(notes))
        dave = User.objects.get(username="dave")
        self.assertTrue(dave.has_perm("projects.read_project", notes))
        self.assertIn(notes.pk, readable_projects(dave).values_list("pk", flat=True))

        self.client.post(
            reverse("project-visibility", kwargs={"pk": notes.pk}),
            {},
        )
        notes = Project.objects.get(pk=notes.pk)
        self.assertFalse(is_public(notes))
        dave = User.objects.get(username="dave")
        self.assertFalse(dave.has_perm("projects.read_project", notes))

    def test_grant_and_revoke_access(self):
        notes = self.projects["alice-private-notes"]
        dave = self.users["dave"]
        self.client.force_login(self.users["alice"])
        self.client.post(
            reverse("project-grant", kwargs={"pk": notes.pk}),
            {"user": dave.pk, "permission": READ},
        )
        dave = User.objects.get(username="dave")
        self.assertTrue(dave.has_perm("projects.read_project", notes))
        self.assertFalse(dave.has_perm("projects.change_project", notes))

        self.client.post(
            reverse("project-revoke", kwargs={"pk": notes.pk}),
            {"user": dave.pk},
        )
        dave = User.objects.get(username="dave")
        self.assertFalse(dave.has_perm("projects.read_project", notes))

    def test_prevent_unauthorized_edits(self):
        notes = self.projects["alice-private-notes"]
        self.client.force_login(self.users["bob"])
        self.assertEqual(
            self.client.get(reverse("project-edit", kwargs={"pk": notes.pk})).status_code,
            403,
        )
        response = self.client.post(
            reverse("project-edit", kwargs={"pk": notes.pk}),
            {"title": "Hacked", "description": "no"},
        )
        self.assertEqual(response.status_code, 403)
        notes.refresh_from_db()
        self.assertEqual(notes.title, "Alice Private Notes")

        self.assertEqual(
            self.client.post(
                reverse("project-grant", kwargs={"pk": notes.pk}),
                {"user": self.users["dave"].pk, "permission": CHANGE},
            ).status_code,
            403,
        )
        self.assertFalse(
            TrustUserPermission.objects.filter(
                trust=notes.trust,
                entity=self.users["dave"],
            ).exists()
        )

    def test_nonseeded_user_reads_public_via_group(self):
        changelog = self.projects["public-changelog"]
        notes = self.projects["alice-private-notes"]
        erin = User.objects.create_user("erin", "erin@example.com", "demo")
        self.assertTrue(erin.groups.filter(name=PUBLIC_GROUP_NAME).exists())
        self.assertTrue(erin.has_perm("projects.read_project", changelog))
        self.assertIn(changelog.pk, readable_projects(erin).values_list("pk", flat=True))
        self.assertFalse(erin.has_perm("projects.read_project", notes))
        self.assertNotIn(notes.pk, readable_projects(erin).values_list("pk", flat=True))
        self.client.force_login(erin)
        response = self.client.get(reverse("project-list"))
        self.assertContains(response, "Public Changelog")
        self.assertNotContains(response, "Alice Private Notes")

    def test_removing_public_readers_is_restored_without_seed(self):
        changelog = self.projects["public-changelog"]
        erin = User.objects.create_user("erin-resync", "erin-resync@example.com", "demo")
        erin.groups.remove(*erin.groups.filter(name=PUBLIC_GROUP_NAME))
        erin = User.objects.get(pk=erin.pk)
        self.assertTrue(erin.groups.filter(name=PUBLIC_GROUP_NAME).exists())
        self.assertTrue(erin.has_perm("projects.read_project", changelog))

    def test_inactive_user_list_matches_has_perm(self):
        bob = self.users["bob"]
        shared = self.projects["shared-roadmap"]
        self.assertTrue(bob.has_perm("projects.read_project", shared))
        self.assertTrue(readable_projects(bob).filter(pk=shared.pk).exists())

        bob.is_active = False
        bob.save()
        bob = User.objects.get(pk=bob.pk)
        self.assertFalse(bob.has_perm("projects.read_project", shared))
        self.assertFalse(readable_projects(bob).filter(pk=shared.pk).exists())
        self.assertFalse(editable_projects(bob).filter(pk=shared.pk).exists())


class PaginationAndQueryTests(TestCase):
    def setUp(self):
        seed_demo()
        self.alice = User.objects.get(username="alice")
        self.bob = User.objects.get(username="bob")

    def _owned(self, title):
        trust = Trust(
            settlor=self.alice,
            title=f"project:{title.lower().replace(' ', '-')}",
            trust=Trust.objects.get_root(),
        )
        trust.save()
        project = Project.objects.create(title=title, slug=title.lower().replace(" ", "-"), trust=trust)
        grant_user(project, self.alice, READ, CHANGE)
        return project

    def test_readable_projects_is_a_queryset_not_a_python_predicate(self):
        qs = readable_projects(self.alice)
        self.assertIsInstance(qs, QuerySet)
        sql = str(qs.query).lower()
        self.assertIn("trusts_trustuserpermission", sql)
        self.assertNotIn(":own", sql)
        page = Paginator(qs, 2).page(1)
        self.assertTrue(all(self.alice.has_perm("projects.read_project", obj) for obj in page))

    @override_settings(PROJECT_PAGE_SIZE=2)
    def test_permission_filter_precedes_pagination(self):
        extras = [self._owned(f"Pad {n}") for n in ("A", "B", "C", "D", "E")]
        grant_user(extras[2], self.bob, READ)
        grant_user(extras[4], self.bob, READ)
        bob = User.objects.get(username="bob")

        filtered = list(readable_projects(bob).filter(title__startswith="Pad"))
        self.assertEqual([p.title for p in filtered], ["Pad C", "Pad E"])

        page = Paginator(readable_projects(bob).filter(title__startswith="Pad"), 2).page(1)
        self.assertEqual([p.title for p in page], ["Pad C", "Pad E"])

        naive = Paginator(Project.objects.filter(title__startswith="Pad").order_by("title"), 2).page(1)
        leaked_or_empty = [p for p in naive if bob.has_perm("projects.read_project", p)]
        self.assertEqual(
            leaked_or_empty,
            [],
            "Paginating the unfiltered table first would hide Pad C/E from page 1.",
        )

        self.client.force_login(bob)
        with override_settings(PROJECT_PAGE_SIZE=2):
            response = self.client.get(reverse("project-list"))
        self.assertContains(response, "Pad C")
        self.assertNotContains(response, "Pad A")
        self.assertNotContains(response, "Pad B")

    def test_public_visibility_uses_group_grant_not_a_condition_code(self):
        from trusts.models import Content

        changelog = Project.objects.get(slug="public-changelog")
        self.assertTrue(is_public(changelog))
        dave = User.objects.get(username="dave")
        self.assertTrue(dave.has_perm("projects.read_project", changelog))
        # :own is a Python predicate on Trust. Project does not register one;
        # public read is a group row, not a condition code.
        self.assertIsNone(Content.get_permission_condition_func(Project, "own"))
        self.assertFalse(dave.has_perm("projects.change_project", changelog))


class ExistingUserBeforeSeedTests(TestCase):
    def test_user_created_before_seed_reads_public(self):
        frank = User.objects.create_user("frank", "frank@example.com", "demo")
        seed_demo()
        frank = User.objects.get(username="frank")
        changelog = Project.objects.get(slug="public-changelog")
        self.assertTrue(frank.groups.filter(name=PUBLIC_GROUP_NAME).exists())
        self.assertTrue(frank.has_perm("projects.read_project", changelog))
        self.assertIn(changelog.pk, readable_projects(frank).values_list("pk", flat=True))


class CreateCollisionTests(TransactionTestCase):
    def setUp(self):
        seed_demo()
        self.bob = User.objects.get(username="bob")

    def test_duplicate_title_resolves_slug_without_500(self):
        trusts_before = Trust.objects.count()
        projects_before = Project.objects.count()
        self.client.force_login(self.bob)
        response = self.client.post(
            reverse("project-create"),
            {"title": "Alice Private Notes", "description": "bob copy"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Trust.objects.count(), trusts_before + 1)
        self.assertEqual(Project.objects.count(), projects_before + 1)
        created = Project.objects.get(description="bob copy")
        self.assertEqual(created.title, "Alice Private Notes")
        self.assertNotEqual(created.slug, "alice-private-notes")
        self.assertTrue(created.slug.startswith("alice-private-notes"))
        self.assertRedirects(response, created.get_absolute_url())
        bob = User.objects.get(username="bob")
        self.assertTrue(bob.has_perm("projects.read_project", created))
        self.assertTrue(bob.has_perm("projects.change_project", created))

    def test_titles_that_normalize_to_the_same_slug(self):
        self.client.force_login(self.bob)
        response = self.client.post(
            reverse("project-create"),
            {"title": "alice  private notes", "description": "normalized"},
        )
        self.assertEqual(response.status_code, 302)
        created = Project.objects.get(description="normalized")
        self.assertEqual(created.slug, "alice-private-notes-2")
        self.assertNotEqual(created.slug, "alice-private-notes")

    def test_failed_create_rolls_back_trust(self):
        trusts_before = Trust.objects.count()
        projects_before = Project.objects.count()
        self.client.force_login(self.bob)
        with patch("projects.create.Project.save", side_effect=IntegrityError("forced")):
            response = self.client.post(
                reverse("project-create"),
                {"title": "Unique Enough Title", "description": "should roll back"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Could not create a unique project identifier")
        self.assertEqual(Trust.objects.count(), trusts_before)
        self.assertEqual(Project.objects.count(), projects_before)
        self.assertFalse(Project.objects.filter(title="Unique Enough Title").exists())

    def test_empty_slug_title_is_rejected(self):
        trusts_before = Trust.objects.count()
        self.client.force_login(self.bob)
        response = self.client.post(
            reverse("project-create"),
            {"title": "!!!", "description": "no slug"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "letters or numbers")
        self.assertEqual(Trust.objects.count(), trusts_before)


class PublicReadersFormAndAdminTests(TestCase):
    def setUp(self):
        seed_demo()
        self.changelog = Project.objects.get(slug="public-changelog")
        self.UserForm = modelform_factory(User, fields=("username", "groups"))

    def _assert_public_read(self, user):
        user = User.objects.get(pk=user.pk)
        self.assertTrue(user.groups.filter(name=PUBLIC_GROUP_NAME).exists())
        self.assertTrue(user.has_perm("projects.read_project", self.changelog))
        self.assertIn(self.changelog.pk, readable_projects(user).values_list("pk", flat=True))

    def test_modelform_create_without_selecting_public_group(self):
        form = self.UserForm(data={"username": "form-created-user", "groups": []})
        self.assertTrue(form.is_valid())
        user = form.save()
        self._assert_public_read(user)

    def test_modelform_edit_without_selecting_public_group(self):
        user = User.objects.create_user("form-edited-user", "fe@example.com", "demo")
        form = self.UserForm(
            data={"username": user.username, "groups": []},
            instance=user,
        )
        self.assertTrue(form.is_valid())
        form.save()
        self._assert_public_read(user)

    def test_useradmin_save_related_create_and_edit(self):
        from projects.admin import UserAdmin

        factory = RequestFactory()
        request = factory.post("/admin/auth/user/add/", {})
        request.user = User.objects.create_superuser("rootadmin", "root@example.com", "demo")
        admin = UserAdmin(User, AdminSite())

        form = self.UserForm(data={"username": "via-admin", "groups": []})
        self.assertTrue(form.is_valid())
        obj = form.save(commit=False)
        admin.save_model(request, obj, form, change=False)
        admin.save_related(request, form, [], change=False)
        self._assert_public_read(User.objects.get(username="via-admin"))

        obj = User.objects.get(username="via-admin")
        edit = self.UserForm(data={"username": obj.username, "groups": []}, instance=obj)
        self.assertTrue(edit.is_valid())
        obj = edit.save(commit=False)
        admin.save_model(request, obj, edit, change=True)
        admin.save_related(request, edit, [], change=True)
        self._assert_public_read(User.objects.get(username="via-admin"))

    def test_groups_set_empty_keeps_public_readers(self):
        user = User.objects.create_user("cleared-groups", "cg@example.com", "demo")
        user.groups.set([])
        self._assert_public_read(user)

    def test_group_admin_cannot_drop_public_readers_member(self):
        user = User.objects.create_user("group-admin-target", "gat@example.com", "demo")
        group = Group.objects.get(name=PUBLIC_GROUP_NAME)
        group.user_set.remove(user)
        self._assert_public_read(user)
