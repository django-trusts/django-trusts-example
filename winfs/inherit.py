"""Write-time preserve / remove / re-enable for SE_DACL_PROTECTED.

Computed inheritance is the bounded read-time choice. These helpers
materialize Explorer-style convert/remove on the stored explicit DACL.
"""

from django.db import transaction

from .constants import KIND_FILE, KIND_FOLDER, MAX_PARENT_DEPTH
from .models import WinAce, WinNode


def _incoming_from_ancestors(node):
    """Python mirror of the SQL incoming bag for dist >= 1 (write path only)."""
    if node.security_descriptor_id is None:
        return []
    sd = node.security_descriptor
    if sd is not None and sd.se_dacl_protected:
        return []

    rows = []
    walk = node
    dist = 0
    seen = {walk.pk}
    while walk.parent_id is not None and dist < MAX_PARENT_DEPTH:
        current_sd = walk.security_descriptor
        if current_sd is not None and current_sd.se_dacl_protected and dist > 0:
            break
        if dist > 0 and current_sd is not None and current_sd.se_dacl_protected:
            break
        parent = walk.parent
        if parent is None:
            break
        if parent.pk in seen:
            break
        seen.add(parent.pk)
        dist += 1
        parent_sd = parent.security_descriptor
        if parent_sd is not None:
            for ace in parent_sd.aces.order_by("ace_order"):
                if ace.flag_np and dist != 1:
                    continue
                if node.kind == KIND_FILE and not ace.flag_oi:
                    continue
                if node.kind == KIND_FOLDER and not (ace.flag_oi or ace.flag_ci):
                    continue
                rows.append((dist, ace))
        walk = parent
        if parent_sd is not None and parent_sd.se_dacl_protected:
            break
    return rows


def _converted_flags(node, dist, ace):
    oi, ci, np, io = ace.flag_oi, ace.flag_ci, ace.flag_np, False
    if np and dist == 1:
        oi = False
        ci = False
        np = False
        io = False
    elif node.kind == KIND_FOLDER and oi and not ci:
        io = True
    elif node.kind == KIND_FILE:
        io = False
    return oi, ci, np, io


@transaction.atomic
def set_dacl_protected(node, *, preserve):
    """Set SE_DACL_PROTECTED.

    preserve=True copies currently computed inherited ACEs onto the node
    as explicit rows (INHERITED_ACE cleared; OI/CI retained unless NP
    cleared them). preserve=False leaves remaining explicit rows only.
    """
    node = WinNode.objects.select_for_update().get(pk=node.pk)
    sd = node.security_descriptor
    if sd is None:
        raise ValueError("Cannot protect a node with a missing descriptor.")
    if preserve:
        inherited = _incoming_from_ancestors(node)
        next_order = (
            sd.aces.order_by("-ace_order").values_list("ace_order", flat=True).first()
            or 0
        )
        for dist, ace in inherited:
            next_order += 1
            oi, ci, np, io = _converted_flags(node, dist, ace)
            WinAce.objects.create(
                descriptor=sd,
                ace_order=next_order,
                ace_type=ace.ace_type,
                trustee=ace.trustee,
                access_mask=ace.access_mask,
                flag_oi=oi,
                flag_ci=ci,
                flag_np=np,
                flag_io=io,
                flag_inherited=False,
            )
    sd.se_dacl_protected = True
    sd.save(update_fields=["se_dacl_protected"])
    return sd


@transaction.atomic
def clear_dacl_protected(node):
    """Re-enable inheritance. Does not invent a NULL DACL."""
    node = WinNode.objects.select_for_update().get(pk=node.pk)
    sd = node.security_descriptor
    if sd is None:
        raise ValueError("Cannot unprotect a node with a missing descriptor.")
    sd.se_dacl_protected = False
    sd.save(update_fields=["se_dacl_protected"])
    return sd
