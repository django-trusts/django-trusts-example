"""Schema integrity that does not require the PostgreSQL evaluator."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from winfs.constants import SID_OWNER_RIGHTS, W
from winfs.fixtures import allow, file, folder, sid, standard_tree
from winfs.models import WinLocalGroup, WinSidMember, WinVolume


class SchemaTests(TestCase):
    def setUp(self):
        self.data = standard_tree(volume_name="schema-vol")

    def test_membership_group_fk_is_local_group(self):
        field = WinSidMember._meta.get_field("group")
        self.assertIs(field.remote_field.model, WinLocalGroup)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WinSidMember.objects.create(
                    group_id=self.data["alice"].sid_id,
                    member=self.data["bob"].sid,
                )
                connection.check_constraints()

    def test_one_root_per_volume(self):
        with self.assertRaises(ValidationError):
            folder(self.data["volume"], "other-root", self.data["admin"])

    def test_file_cannot_be_parent(self):
        with self.assertRaises(ValidationError):
            file(
                self.data["volume"],
                "orphan.txt",
                self.data["admin"],
                parent=self.data["notes"],
            )

    def test_parent_must_share_volume(self):
        other = WinVolume.objects.create(name="other-vol")
        with self.assertRaises(ValidationError):
            folder(other, "x", self.data["admin"], parent=self.data["proj"])

    def test_self_membership_refused(self):
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                WinSidMember(
                    group=self.data["eng"],
                    member=self.data["eng"].sid,
                ).full_clean()

    def test_owner_rights_write_refused(self):
        with self.assertRaises(ValidationError):
            allow(self.data["notes"], sid(SID_OWNER_RIGHTS), W)

    def test_principal_is_not_django_group(self):
        self.assertFalse(hasattr(self.data["eng"], "permissions"))
        self.assertEqual(self.data["alice"].user.username, "alice")

    def test_unique_string_fields_are_varchar_not_text(self):
        # MySQL 8 errno 1170: UNIQUE on TEXT/BLOB requires a prefix length.
        from django.db.models import CharField

        from winfs.models import WinLocalGroup, WinNode, WinSid, WinStream, WinVolume

        for model, name in (
            (WinSid, "sid_string"),
            (WinLocalGroup, "name"),
            (WinVolume, "name"),
            (WinNode, "name"),
            (WinStream, "name"),
        ):
            field = model._meta.get_field(name)
            self.assertIsInstance(field, CharField, "%s.%s" % (model.__name__, name))
            self.assertLessEqual(field.max_length, 255)
