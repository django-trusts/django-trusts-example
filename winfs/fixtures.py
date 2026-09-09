"""Builders for the documentation-derived V1–V43 fixture tree."""

from django.contrib.auth import get_user_model

from .constants import (
    ACE_ALLOW,
    ACE_DENY,
    KIND_FILE,
    KIND_FOLDER,
    SID_CREATOR_OWNER,
    SID_OWNER_RIGHTS,
)
from .models import (
    WinAce,
    WinLocalGroup,
    WinNode,
    WinPrincipal,
    WinSecurityDescriptor,
    WinSid,
    WinSidMember,
    WinVolume,
)

User = get_user_model()

SID_ALICE = "S-1-5-21-1000-1-1-1001"
SID_BOB = "S-1-5-21-1000-1-1-1002"
SID_CAROL = "S-1-5-21-1000-1-1-1003"
SID_ADMIN = "S-1-5-21-1000-1-1-500"
SID_ENG = "S-1-5-21-1000-1-1-512"


def sid(sid_string):
    obj, _created = WinSid.objects.get_or_create(sid_string=sid_string)
    return obj


def well_known_sids():
    return {
        "creator_owner": sid(SID_CREATOR_OWNER),
        "owner_rights": sid(SID_OWNER_RIGHTS),
    }


def principal(username, sid_string, *, password="demo"):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"is_active": True},
    )
    if created:
        user.set_password(password)
        user.save(update_fields=["password"])
    row, _created = WinPrincipal.objects.get_or_create(
        sid=sid(sid_string),
        defaults={"user": user},
    )
    if row.user_id != user.pk:
        row.user = user
        row.save(update_fields=["user"])
    return row


def local_group(name, sid_string, members=()):
    group, _created = WinLocalGroup.objects.get_or_create(
        sid=sid(sid_string),
        defaults={"name": name},
    )
    if group.name != name:
        group.name = name
        group.save(update_fields=["name"])
    for member in members:
        member_sid = member.sid if isinstance(member, WinPrincipal) else member
        WinSidMember.objects.get_or_create(group=group, member=member_sid)
    return group


def descriptor(owner, *, protected=False):
    owner_sid = owner.sid if isinstance(owner, WinPrincipal) else owner
    return WinSecurityDescriptor.objects.create(
        owner=owner_sid,
        se_dacl_protected=protected,
    )


def add_ace(
    node_or_sd,
    ace_type,
    trustee,
    access_mask,
    *,
    oi=False,
    ci=False,
    np=False,
    io=False,
    inherited=False,
    order=None,
):
    sd = (
        node_or_sd
        if isinstance(node_or_sd, WinSecurityDescriptor)
        else node_or_sd.security_descriptor
    )
    if order is None:
        order = (
            sd.aces.order_by("-ace_order").values_list("ace_order", flat=True).first()
            or 0
        ) + 1
    trustee_sid = trustee.sid if isinstance(trustee, (WinPrincipal, WinLocalGroup)) else trustee
    return WinAce.objects.create(
        descriptor=sd,
        ace_order=order,
        ace_type=ace_type,
        trustee=trustee_sid,
        access_mask=access_mask,
        flag_oi=oi,
        flag_ci=ci,
        flag_np=np,
        flag_io=io,
        flag_inherited=inherited,
    )


def add_ace_raw(sd, ace_type, trustee, access_mask, **flags):
    """Insert an ACE without model.clean() (OWNER_RIGHTS evaluation tests).

    Disables the PostgreSQL write trigger so evaluation can still see a
    row that writers refuse.
    """
    from django.db import connection

    trustee_sid = trustee.sid if isinstance(trustee, (WinPrincipal, WinLocalGroup)) else trustee
    order = flags.pop("order", None)
    if order is None:
        order = (
            WinAce.objects.filter(descriptor=sd)
            .order_by("-ace_order")
            .values_list("ace_order", flat=True)
            .first()
            or 0
        ) + 1
    ace = WinAce(
        descriptor=sd,
        ace_order=order,
        ace_type=ace_type,
        trustee=trustee_sid,
        access_mask=access_mask,
        flag_oi=flags.get("oi", False),
        flag_ci=flags.get("ci", False),
        flag_np=flags.get("np", False),
        flag_io=flags.get("io", False),
        flag_inherited=flags.get("inherited", False),
    )
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL session_replication_role = replica")
    try:
        WinAce.objects.bulk_create([ace])
    finally:
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL session_replication_role = origin")
    return WinAce.objects.get(descriptor=sd, ace_order=order)


def node(volume, name, kind, owner, *, parent=None, protected=False, sd=None):
    if sd is None:
        sd = descriptor(owner, protected=protected)
    return WinNode.objects.create(
        volume=volume,
        parent=parent,
        kind=kind,
        name=name,
        security_descriptor=sd,
    )


def folder(volume, name, owner, **kwargs):
    return node(volume, name, KIND_FOLDER, owner, **kwargs)


def file(volume, name, owner, **kwargs):
    return node(volume, name, KIND_FILE, owner, **kwargs)


def standard_actors():
    well_known_sids()
    alice = principal("alice", SID_ALICE)
    bob = principal("bob", SID_BOB)
    carol = principal("carol", SID_CAROL)
    admin = principal("admin", SID_ADMIN)
    eng = local_group("eng", SID_ENG, members=(alice, bob))
    return {
        "alice": alice,
        "bob": bob,
        "carol": carol,
        "admin": admin,
        "eng": eng,
        "users": {
            "alice": alice.user,
            "bob": bob.user,
            "carol": carol.user,
            "admin": admin.user,
        },
    }


def standard_tree(actors=None, *, volume_name="vol"):
    """Shared fixture from bounded-winfs-acl-r1 §6."""
    actors = actors or standard_actors()
    admin = actors["admin"]
    alice = actors["alice"]
    volume = WinVolume.objects.create(name=volume_name)
    vol = folder(volume, "vol", admin)
    proj = folder(volume, "proj", admin, parent=vol)
    secret = folder(volume, "secret", alice, parent=proj)
    notes = file(volume, "notes.txt", alice, parent=secret)
    readme = file(volume, "readme.txt", admin, parent=proj)
    actors.update(
        {
            "volume": volume,
            "vol": vol,
            "proj": proj,
            "secret": secret,
            "notes": notes,
            "readme": readme,
        }
    )
    return actors


def empty_dacl(node_obj):
    node_obj.security_descriptor.aces.all().delete()


def allow(node_obj, trustee, mask, **flags):
    return add_ace(node_obj, ACE_ALLOW, trustee, mask, **flags)


def deny(node_obj, trustee, mask, **flags):
    return add_ace(node_obj, ACE_DENY, trustee, mask, **flags)
