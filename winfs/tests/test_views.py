from django.urls import reverse

from winfs.constants import R
from winfs.fixtures import allow

from .support import FixtureMixin, PostgresTestCase


class BrowserTests(FixtureMixin, PostgresTestCase):
    def test_authorized_browse_and_forbidden_child(self):
        allow(self.vol, self.eng, R, ci=True)
        allow(self.proj, self.eng, R, oi=True, ci=True)
        self.client.force_login(self.alice)
        volumes = self.client.get(reverse("winfs-volumes"))
        self.assertEqual(volumes.status_code, 200)
        self.assertContains(volumes, "vol")
        root = self.client.get(reverse("winfs-volume", args=[self.data["volume"].pk]))
        self.assertEqual(root.status_code, 200)
        proj = self.client.get(reverse("winfs-node", args=[self.proj.pk]))
        self.assertEqual(proj.status_code, 200)
        self.assertContains(proj, "readme.txt")
        self.assertContains(proj, "secret")
        notes = self.client.get(reverse("winfs-node", args=[self.notes.pk]))
        self.assertEqual(notes.status_code, 200)
        self.client.force_login(self.carol)
        denied = self.client.get(reverse("winfs-node", args=[self.notes.pk]))
        self.assertEqual(denied.status_code, 403)
