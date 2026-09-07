from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from trusts.decorators import permission_required, K
from trusts.models import Trust

from .forms import GrantForm, ProjectForm, VisibilityForm
from .grants import CHANGE, READ, grant_user, is_public, revoke_user, set_public, trustee_rows
from .models import Project
from .query import editable_projects, readable_projects


def _page_size():
    return getattr(settings, "PROJECT_PAGE_SIZE", 3)


@login_required
def project_list(request):
    # Filter first, then paginate. Do not slice the unfiltered table.
    qs = readable_projects(request.user)
    page = Paginator(qs, _page_size()).get_page(request.GET.get("page"))
    return render(
        request,
        "projects/project_list.html",
        {
            "page": page,
            "can_edit_ids": set(editable_projects(request.user).values_list("pk", flat=True)),
            "demo_users": ("alice", "bob", "carol", "dave"),
        },
    )


@login_required
def project_create(request):
    form = ProjectForm(request.POST or None)
    if form.is_valid():
        title = form.cleaned_data["title"]
        slug = slugify(title)
        trust = Trust(
            settlor=request.user,
            title=f"project:{slug}",
            trust=Trust.objects.get_root(),
        )
        trust.save()
        project = form.save(commit=False)
        project.trust = trust
        project.slug = slug
        project.save()
        grant_user(project, request.user, READ, CHANGE)
        messages.success(request, f"Created {project.title}. You have read and change.")
        return redirect(project)
    return render(request, "projects/project_form.html", {"form": form, "mode": "create"})


@login_required
@permission_required("projects.read_project", pk=K("pk"))
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk)
    can_change = request.user.has_perm("projects.change_project", project)
    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "can_change": can_change,
            "is_public": is_public(project),
            "trustees": trustee_rows(project),
            "grant_form": GrantForm() if can_change else None,
            "visibility_form": VisibilityForm(initial={"is_public": is_public(project)})
            if can_change
            else None,
        },
    )


@login_required
@permission_required("projects.change_project", pk=K("pk"))
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form = ProjectForm(request.POST or None, instance=project)
    if form.is_valid():
        form.save()
        messages.success(request, "Project updated.")
        return redirect(project)
    return render(
        request,
        "projects/project_form.html",
        {"form": form, "mode": "edit", "project": project},
    )


@login_required
@permission_required("projects.change_project", pk=K("pk"))
def project_visibility(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method != "POST":
        return redirect(project)
    form = VisibilityForm(request.POST)
    if form.is_valid():
        set_public(project, form.cleaned_data["is_public"])
        messages.success(
            request,
            "Visibility is now public." if is_public(project) else "Visibility is now private.",
        )
    return redirect(project)


@login_required
@permission_required("projects.change_project", pk=K("pk"))
def project_grant(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method != "POST":
        return redirect(project)
    form = GrantForm(request.POST)
    if form.is_valid():
        user = form.cleaned_data["user"]
        perm = form.cleaned_data["permission"]
        if perm == CHANGE:
            grant_user(project, user, READ, CHANGE)
        else:
            revoke_user(project, user, CHANGE)
            grant_user(project, user, READ)
        messages.success(request, f"Granted {perm} to {user.username}.")
    else:
        messages.error(request, "Could not grant access.")
    return redirect(project)


@login_required
@permission_required("projects.change_project", pk=K("pk"))
def project_revoke(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method != "POST":
        return redirect(project)
    user = get_object_or_404(User, pk=request.POST.get("user"))
    revoke_user(project, user)
    messages.success(request, f"Revoked access for {user.username}.")
    return redirect(project)
