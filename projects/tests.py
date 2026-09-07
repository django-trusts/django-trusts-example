from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import QuerySet
from django.test import TestCase, override_settings
from django.urls import reverse

from trusts.models import Trust, TrustUserPermission

from .demo import seed_demo
from .grants import CHANGE, READ, grant_user, is_public, set_public
from .models import Project
from .query import readable_projects

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
