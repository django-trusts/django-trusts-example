"""Example-local Windows SID / descriptor / containment schema.

No Trust, Trustee adapter, Content, Junction, TrustGroup, Role, or
Django Group is used by this evaluator. SID is the relational identity.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .constants import (
    ACE_ALLOW,
    ACE_DENY,
    KIND_FILE,
    KIND_FOLDER,
    SID_OWNER_RIGHTS,
)


class WinSid(models.Model):
    """Canonical SID row: owner, ACE trustee, and token identity."""

    sid_string = models.TextField(unique=True)

    class Meta:
        db_table = "win_sid"

    def __str__(self):
        return self.sid_string


class WinPrincipal(models.Model):
    """Typed user-SID profile. Login mapping only; not a Trustee adapter."""

    sid = models.OneToOneField(
        WinSid,
        on_delete=models.RESTRICT,
        primary_key=True,
        related_name="principal",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="win_principal",
    )

    class Meta:
        db_table = "win_principal"

    def __str__(self):
        return "principal:%s" % self.sid.sid_string


class WinLocalGroup(models.Model):
    """Typed local-group profile. Not auth.Group."""

    sid = models.OneToOneField(
        WinSid,
        on_delete=models.RESTRICT,
        primary_key=True,
        related_name="local_group",
    )
    name = models.TextField(unique=True)

    class Meta:
        db_table = "win_local_group"

    def __str__(self):
        return self.name


class WinSidMember(models.Model):
    """Flat local membership. group_sid is a real FK to win_local_group."""

    group = models.ForeignKey(
        WinLocalGroup,
        on_delete=models.RESTRICT,
        related_name="memberships",
        db_column="group_sid_id",
    )
    member = models.ForeignKey(
        WinSid,
        on_delete=models.RESTRICT,
        related_name="group_memberships",
        db_column="member_sid_id",
    )

    class Meta:
        db_table = "win_sid_member"
        constraints = [
            models.UniqueConstraint(
                fields=("group", "member"),
                name="win_sid_member_pk_pair",
            ),
            models.CheckConstraint(
                condition=~models.Q(group_id=models.F("member_id")),
                name="win_sid_member_not_self",
            ),
        ]

    def clean(self):
        if self.group_id is not None and self.group_id == self.member_id:
            raise ValidationError("A SID cannot be a member of itself.")


class WinSecurityDescriptor(models.Model):
    """Context terminal: owner + SE_DACL_PROTECTED. DACL is ordered WinAce rows.

    Presence of this row is SE_DACL_PRESENT. Absence on a node is missing
    policy (deny). NULL DACL is not representable.
    """

    owner = models.ForeignKey(
        WinSid,
        on_delete=models.RESTRICT,
        related_name="owned_descriptors",
        db_column="owner_sid_id",
    )
    se_dacl_protected = models.BooleanField(default=False)

    class Meta:
        db_table = "win_security_descriptor"

    def __str__(self):
        return "sd:%s protected=%s" % (self.pk, self.se_dacl_protected)


class WinAce(models.Model):
    """One stored DACL entry. Evaluation walks ace_order, not deny-wins."""

    descriptor = models.ForeignKey(
        WinSecurityDescriptor,
        on_delete=models.RESTRICT,
        related_name="aces",
    )
    ace_order = models.IntegerField()
    ace_type = models.CharField(max_length=8)
    trustee = models.ForeignKey(
        WinSid,
        on_delete=models.RESTRICT,
        related_name="aces",
        db_column="trustee_sid_id",
    )
    access_mask = models.BigIntegerField()
    flag_oi = models.BooleanField(default=False)
    flag_ci = models.BooleanField(default=False)
    flag_np = models.BooleanField(default=False)
    flag_io = models.BooleanField(default=False)
    flag_inherited = models.BooleanField(default=False)

    class Meta:
        db_table = "win_ace"
        constraints = [
            models.UniqueConstraint(
                fields=("descriptor", "ace_order"),
                name="win_ace_descriptor_order",
            ),
            models.CheckConstraint(
                condition=models.Q(ace_type__in=(ACE_ALLOW, ACE_DENY)),
                name="win_ace_type",
            ),
            models.CheckConstraint(
                condition=models.Q(access_mask__gte=0),
                name="win_ace_mask_nonneg",
            ),
        ]
        indexes = [
            models.Index(fields=("descriptor", "ace_order")),
        ]

    def clean(self):
        if self.ace_type not in (ACE_ALLOW, ACE_DENY):
            raise ValidationError("ace_type must be allow or deny.")
        if self.access_mask is not None and self.access_mask < 0:
            raise ValidationError("access_mask must be a specific-bit field.")
        trustee = self.trustee
        if trustee is None and self.trustee_id is not None:
            trustee = WinSid.objects.filter(pk=self.trustee_id).first()
        if trustee is not None and trustee.sid_string == SID_OWNER_RIGHTS:
            raise ValidationError(
                "OWNER_RIGHTS (S-1-3-4) is excluded; refuse the write."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class WinVolume(models.Model):
    """One filesystem volume. Multiple volumes are allowed; one root each."""

    name = models.TextField(unique=True)

    class Meta:
        db_table = "win_volume"

    def __str__(self):
        return self.name


class WinNode(models.Model):
    """Resource tree. Hierarchy is WinNode.parent, not Trust.trust."""

    volume = models.ForeignKey(
        WinVolume,
        on_delete=models.RESTRICT,
        related_name="nodes",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="children",
    )
    kind = models.CharField(max_length=8)
    name = models.TextField()
    security_descriptor = models.OneToOneField(
        WinSecurityDescriptor,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="node",
    )

    class Meta:
        db_table = "win_node"
        constraints = [
            models.UniqueConstraint(
                fields=("volume", "parent", "name"),
                name="win_node_sibling_name",
            ),
            models.CheckConstraint(
                condition=~models.Q(id=models.F("parent")),
                name="win_node_not_self_parent",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=(KIND_FILE, KIND_FOLDER)),
                name="win_node_kind",
            ),
        ]
        indexes = [
            models.Index(fields=("parent",)),
            models.Index(fields=("security_descriptor",)),
            models.Index(fields=("volume",)),
        ]

    def __str__(self):
        return "%s:%s" % (self.kind, self.name)

    def clean(self):
        if self.kind not in (KIND_FILE, KIND_FOLDER):
            raise ValidationError("kind must be file or folder.")
        if self.parent_id is not None:
            if self.pk is not None and self.pk == self.parent_id:
                raise ValidationError("A node cannot be its own parent.")
            parent = self.parent
            if parent is None and self.parent_id is not None:
                parent = WinNode.objects.filter(pk=self.parent_id).first()
            if parent is None:
                raise ValidationError("parent_id does not resolve.")
            if parent.kind != KIND_FOLDER:
                raise ValidationError("Files cannot be parents.")
            if self.volume_id is not None and parent.volume_id != self.volume_id:
                raise ValidationError("Parent must share volume_id.")
            seen = {self.pk} if self.pk is not None else set()
            walk = parent
            hops = 0
            while walk is not None:
                if walk.pk in seen:
                    raise ValidationError("Parent cycle is refused.")
                seen.add(walk.pk)
                hops += 1
                if hops > 4096:
                    raise ValidationError("Parent walk exceeded write-time bound.")
                walk = walk.parent
        elif (
            self.volume_id is not None
            and WinNode.objects.filter(volume_id=self.volume_id, parent__isnull=True)
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError("Each volume has one root.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class WinStream(models.Model):
    """Optional sidecar that shares the node's security descriptor, not the parent."""

    node = models.ForeignKey(
        WinNode,
        on_delete=models.RESTRICT,
        related_name="streams",
    )
    name = models.TextField()

    class Meta:
        db_table = "win_stream"
        constraints = [
            models.UniqueConstraint(
                fields=("node", "name"),
                name="win_stream_node_name",
            ),
        ]

    def __str__(self):
        return "%s:%s" % (self.node_id, self.name)
