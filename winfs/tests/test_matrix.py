"""Complete approved V1–V43 matrix (documentation-derived)."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection

from winfs.constants import (
    ACE_ALLOW,
    MAX_ACE_SCAN,
    MAX_PARENT_DEPTH,
    R,
    RC,
    SID_OWNER_RIGHTS,
    W,
    WD,
)
from winfs.evaluate import (
    ERR_ACE_OVERFLOW,
    ERR_CONTEXT,
    ERR_CYCLE,
    ERR_MISSING_PRINCIPAL,
    ERR_MISSING_SD,
    ERR_OVERFLOW,
    ERR_OWNER_RIGHTS,
    access_check,
)
from winfs.fixtures import add_ace_raw, allow, deny, empty_dacl, file, sid
from winfs.inherit import set_dacl_protected
from winfs.models import WinAce, WinNode

from .support import FixtureMixin, PostgresTestCase

User = get_user_model()


class MatrixTests(FixtureMixin, PostgresTestCase):
    def test_v1_empty_dacl_denies_read(self):
        self.assert_deny(self.alice, self.notes, R)

    def test_v2_missing_descriptor_denies(self):
        self.notes.security_descriptor = None
        self.notes.save()
        self.assert_deny(self.alice, self.notes, R, error=ERR_MISSING_SD)

    def test_v3_explicit_allow(self):
        allow(self.notes, self.data["alice"], R)
        self.assert_allow(self.alice, self.notes, R)

    def test_v4_canonical_deny_then_allow(self):
        deny(self.notes, self.data["alice"], R)
        allow(self.notes, self.data["alice"], R)
        self.assert_deny(self.alice, self.notes, R)

    def test_v5_noncanonical_allow_then_deny_not_deny_wins(self):
        allow(self.notes, self.data["alice"], R)
        deny(self.notes, self.data["alice"], R)
        self.assert_allow(self.alice, self.notes, R)

    def test_v6_user_deny_before_group_allow(self):
        deny(self.notes, self.data["alice"], R)
        allow(self.notes, self.eng, R)
        self.assert_deny(self.alice, self.notes, R)

    def test_v7_group_allow_for_other_member(self):
        deny(self.notes, self.data["alice"], R)
        allow(self.notes, self.eng, R)
        self.assert_allow(self.bob, self.notes, R)

    def test_v8_non_member_implicit_deny(self):
        deny(self.notes, self.data["alice"], R)
        allow(self.notes, self.eng, R)
        self.assert_deny(self.carol, self.notes, R)

    def test_v9_partial_bits_denied(self):
        allow(self.notes, self.data["alice"], R)
        self.assert_deny(self.alice, self.notes, R | W)

    def test_v10_allow_bits_accumulate(self):
        allow(self.notes, self.data["alice"], R)
        allow(self.notes, self.data["alice"], W)
        self.assert_allow(self.alice, self.notes, R | W)

    def test_v11_noncanonical_allow_clears_denied_bit(self):
        allow(self.notes, self.data["alice"], R | W)
        deny(self.notes, self.data["alice"], W)
        self.assert_allow(self.alice, self.notes, W)

    def test_v12_same_as_v11_combined_request(self):
        allow(self.notes, self.data["alice"], R | W)
        deny(self.notes, self.data["alice"], W)
        self.assert_allow(self.alice, self.notes, R | W)

    def test_v13_remaining_write_denied(self):
        allow(self.notes, self.data["alice"], R)
        deny(self.notes, self.data["alice"], W)
        self.assert_deny(self.alice, self.notes, R | W)

    def test_v14_owner_write_dac(self):
        self.assert_allow(self.alice, self.notes, WD)

    def test_v15_owner_is_not_file_read(self):
        self.assert_deny(self.alice, self.notes, R)

    def test_v16_owner_pregrant_before_owner_sid_deny(self):
        deny(self.notes, self.data["alice"], WD)
        self.assert_allow(self.alice, self.notes, WD)

    def test_v17_file_inherits_oi(self):
        allow(self.proj, self.eng, R, oi=True, ci=True)
        self.assert_allow(self.alice, self.readme, R)

    def test_v18_container_ci_effective(self):
        allow(self.proj, self.eng, R, oi=True, ci=True)
        self.assert_allow(self.alice, self.proj, R)

    def test_v19_ci_only_does_not_reach_file(self):
        allow(self.proj, self.eng, R, ci=True)
        self.assert_deny(self.alice, self.readme, R)

    def test_v20_oi_without_io_is_effective_on_container(self):
        allow(self.proj, self.eng, R, oi=True)
        self.assert_allow(self.alice, self.proj, R)

    def test_v21_oi_only_file_inherits(self):
        allow(self.proj, self.eng, R, oi=True)
        self.assert_allow(self.alice, self.readme, R)

    def test_v22_oi_only_child_container_is_inherit_only(self):
        allow(self.proj, self.eng, R, oi=True)
        self.assert_deny(self.alice, self.secret, R)

    def test_v23_oi_only_grandchild_file_inherits(self):
        allow(self.proj, self.eng, R, oi=True)
        self.assert_allow(self.alice, self.notes, R)

    def test_v24_np_immediate_container(self):
        allow(self.proj, self.eng, R, oi=True, ci=True, np=True)
        self.assert_allow(self.alice, self.secret, R)

    def test_v25_np_does_not_reach_grandchild(self):
        allow(self.proj, self.eng, R, oi=True, ci=True, np=True)
        self.assert_deny(self.alice, self.notes, R)

    def test_v26_protected_empty_secret(self):
        allow(self.proj, self.eng, R, oi=True, ci=True)
        sd = self.secret.security_descriptor
        sd.se_dacl_protected = True
        sd.save(update_fields=["se_dacl_protected"])
        self.assert_deny(self.alice, self.secret, R)

    def test_v27_protect_stops_walk_to_notes(self):
        allow(self.proj, self.eng, R, oi=True, ci=True)
        sd = self.secret.security_descriptor
        sd.se_dacl_protected = True
        sd.save(update_fields=["se_dacl_protected"])
        self.assert_deny(self.alice, self.notes, R)

    def test_v28_preserve_converts_inherited_on_secret(self):
        allow(self.proj, self.eng, R, oi=True, ci=True)
        set_dacl_protected(self.secret, preserve=True)
        self.assert_allow(self.alice, self.secret, R)

    def test_v29_preserve_children_inherit_from_secret(self):
        allow(self.proj, self.eng, R, oi=True, ci=True)
        set_dacl_protected(self.secret, preserve=True)
        self.assert_allow(self.alice, self.notes, R)

    def test_v30_io_skipped_on_proj(self):
        allow(self.proj, self.eng, R, oi=True, ci=True, io=True)
        self.assert_deny(self.alice, self.proj, R)

    def test_v31_io_on_proj_still_inheritable(self):
        allow(self.proj, self.eng, R, oi=True, ci=True, io=True)
        self.assert_allow(self.alice, self.readme, R)

    def test_v32_child_read_is_not_parent_list(self):
        allow(self.notes, self.data["alice"], R)
        self.assert_deny(self.alice, self.secret, R)

    def test_v33_folder_list_allowed(self):
        allow(self.proj, self.data["bob"], R)
        deny(self.readme, self.data["bob"], R)
        self.assert_allow(self.bob, self.proj, R)

    def test_v34_name_visibility_is_not_read(self):
        allow(self.proj, self.data["bob"], R)
        deny(self.readme, self.data["bob"], R)
        self.assert_deny(self.bob, self.readme, R)

    def test_v35_group_allow_before_user_deny(self):
        allow(self.notes, self.eng, R)
        deny(self.notes, self.data["alice"], R)
        self.assert_allow(self.alice, self.notes, R)

    def test_v36_cycle_fail_closed(self):
        allow(self.proj, self.eng, R, oi=True, ci=True)
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL session_replication_role = replica")
            WinNode.objects.filter(pk=self.proj.pk).update(parent=self.secret)
            cursor.execute("SET LOCAL session_replication_role = origin")
        self.assert_deny(self.alice, self.notes, R, error=ERR_CYCLE)

    def test_v37_unregistered_resource_denies(self):
        decision = access_check(self.alice, self.data["alice"].sid, R)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.error, ERR_CONTEXT)

    def test_v38_prime_missing_principal(self):
        user = User.objects.create_user("noprincipal", password="demo")
        self.assert_deny(user, self.notes, R, error=ERR_MISSING_PRINCIPAL)

    def test_v39_new_child_inherits_from_proj(self):
        allow(self.proj, self.eng, R, oi=True, ci=True)
        new = file(self.data["volume"], "new.txt", self.data["admin"], parent=self.proj)
        self.assert_allow(self.alice, new, R)

    def test_v40_explicit_owner_rights_rejected(self):
        owner_rights = sid(SID_OWNER_RIGHTS)
        add_ace_raw(
            self.notes.security_descriptor,
            ACE_ALLOW,
            owner_rights,
            WD,
        )
        self.assert_deny(self.alice, self.notes, WD, error=ERR_OWNER_RIGHTS)
        # Owner pre-grant must not run.
        self.assertFalse(self.decide(self.alice, self.notes, WD).allowed)

    def test_v41_group_owner_pregrant(self):
        sd = self.notes.security_descriptor
        sd.owner = self.eng.sid
        sd.save(update_fields=["owner"])
        self.assert_allow(self.alice, self.notes, WD)

    def test_v42_non_member_group_owner(self):
        sd = self.notes.security_descriptor
        sd.owner = self.eng.sid
        sd.save(update_fields=["owner"])
        self.assert_deny(self.carol, self.notes, WD)

    def test_v43_inherited_owner_rights_rejected(self):
        owner_rights = sid(SID_OWNER_RIGHTS)
        add_ace_raw(
            self.proj.security_descriptor,
            ACE_ALLOW,
            owner_rights,
            WD,
            oi=True,
            ci=True,
        )
        empty_dacl(self.notes)
        self.assert_deny(self.alice, self.notes, WD, error=ERR_OWNER_RIGHTS)

    def test_owner_write_is_not_all_permissions(self):
        self.assert_allow(self.alice, self.notes, RC)
        self.assert_deny(self.alice, self.notes, R)
        self.assert_deny(self.alice, self.notes, W)

    def test_write_refuses_owner_rights_ace(self):
        with self.assertRaises(ValidationError):
            allow(self.notes, sid(SID_OWNER_RIGHTS), WD)

    def test_depth_63_valid(self):
        self.assertEqual(MAX_PARENT_DEPTH, 64)
        leaf = self.chain(63)
        self.assert_allow(self.alice, leaf, R)

    def test_depth_64_valid_root_at_cap(self):
        leaf = self.chain(64)
        self.assert_allow(self.alice, leaf, R)

    def test_depth_65_overflow(self):
        leaf = self.chain(65)
        self.assert_deny(self.alice, leaf, R, error=ERR_OVERFLOW)

    def test_ace_count_not_capped_at_64(self):
        for _ in range(65):
            allow(self.notes, self.data["alice"], R)
        self.assertGreater(WinAce.objects.filter(descriptor=self.notes.security_descriptor).count(), 64)
        self.assert_allow(self.alice, self.notes, R)
        self.assertGreater(MAX_ACE_SCAN, 64)

    def test_ace_scan_limit_independent(self):
        allow(self.notes, self.data["alice"], R)
        allow(self.notes, self.data["alice"], W)
        allow(self.notes, self.data["bob"], R)
        decision = self.decide(self.alice, self.notes, R, max_ace_scan=2)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.error, ERR_ACE_OVERFLOW)
        self.assert_allow(self.alice, self.notes, R)
