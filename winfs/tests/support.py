from unittest import SkipTest

from django.db import connection
from django.test import TestCase, TransactionTestCase

from winfs.constants import R
from winfs.evaluate import access_check
from winfs.fixtures import standard_tree


def skip_unless_postgres():
    if connection.vendor != "postgresql":
        raise SkipTest(
            "winfs AccessCheck is the PostgreSQL 14+ reference implementation."
        )


class PostgresTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        skip_unless_postgres()
        super().setUpClass()


class PostgresTransactionTestCase(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        skip_unless_postgres()
        super().setUpClass()


class FixtureMixin:
    def setUp(self):
        super().setUp()
        self.data = standard_tree()
        self.alice = self.data["users"]["alice"]
        self.bob = self.data["users"]["bob"]
        self.carol = self.data["users"]["carol"]
        self.admin = self.data["users"]["admin"]
        self.eng = self.data["eng"]
        self.vol = self.data["vol"]
        self.proj = self.data["proj"]
        self.secret = self.data["secret"]
        self.notes = self.data["notes"]
        self.readme = self.data["readme"]

    def decide(self, user, node, mask, **kwargs):
        return access_check(user, node, mask, **kwargs)

    def assert_allow(self, user, node, mask, msg=None):
        decision = self.decide(user, node, mask)
        self.assertTrue(
            decision.allowed,
            msg or "expected ALLOW, got %s remaining=%s" % (decision, decision.remaining),
        )
        self.assertIsNone(decision.error)

    def assert_deny(self, user, node, mask, error=None, msg=None):
        decision = self.decide(user, node, mask)
        self.assertFalse(decision.allowed, msg or "expected DENY, got %s" % (decision,))
        if error is None:
            self.assertIsNone(decision.error, "silent DENY must not set error")
        else:
            self.assertEqual(decision.error, error)

    def chain(self, parent_links, *, leaf_file=True, grant_root=True):
        """Build a vertical chain with ``parent_links`` edges to the leaf.

        The grant folder is a volume root so a valid root may sit at
        dist = parent_links (including 64). Overflow is parent_links = 65.
        """
        from winfs.fixtures import allow, file, folder
        from winfs.models import WinVolume as Volume

        admin = self.data["admin"]
        alice = self.data["alice"]
        volume = Volume.objects.create(name="depth-%s" % parent_links)
        current = folder(volume, "d0", admin)
        if grant_root:
            allow(current, alice, R, oi=True, ci=True)
        for i in range(1, parent_links):
            current = folder(volume, "d%s" % i, admin, parent=current)
        if leaf_file:
            leaf = file(volume, "leaf.txt", alice, parent=current)
        else:
            leaf = folder(volume, "leaf", alice, parent=current)
        return leaf
