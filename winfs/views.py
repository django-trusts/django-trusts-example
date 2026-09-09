"""Minimal file browser over the authorized-object listing."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from .constants import LIST, R, RC, W, WD
from .evaluate import WinfsBackendError, access_check, authorized_nodes
from .models import WinNode, WinVolume


def _checks(user, node):
    try:
        return {
            "R": access_check(user, node, R),
            "W": access_check(user, node, W),
            "LIST": access_check(user, node, LIST),
            "RC": access_check(user, node, RC),
            "WD": access_check(user, node, WD),
        }
    except WinfsBackendError:
        return None


@login_required
def volume_list(request):
    volumes = WinVolume.objects.order_by("name")
    return render(request, "winfs/volumes.html", {"volumes": volumes})


@login_required
def browse(request, pk):
    node = get_object_or_404(WinNode, pk=pk)
    checks = _checks(request.user, node)
    if checks is None:
        return render(
            request,
            "winfs/unavailable.html",
            {"node": node},
            status=503,
        )
    list_decision = checks["LIST"] if node.kind == "folder" else checks["R"]
    if not list_decision.allowed:
        return HttpResponseForbidden("AccessCheck denied this node.")
    children = []
    if node.kind == "folder":
        # Authorized-object listing (issue thesis), not Windows "LIST ⇒ all names".
        children = authorized_nodes(request.user, R, parent_id=node.pk)
    return render(
        request,
        "winfs/browse.html",
        {
            "node": node,
            "checks": checks,
            "children": children,
        },
    )


@login_required
def volume_root(request, pk):
    volume = get_object_or_404(WinVolume, pk=pk)
    root = WinNode.objects.filter(volume=volume, parent__isnull=True).first()
    if root is None:
        raise Http404("Volume has no root.")
    return browse(request, root.pk)
