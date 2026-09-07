from django.urls import path

from . import views

urlpatterns = [
    path("", views.project_list, name="project-list"),
    path("projects/new/", views.project_create, name="project-create"),
    path("projects/<int:pk>/", views.project_detail, name="project-detail"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project-edit"),
    path(
        "projects/<int:pk>/visibility/",
        views.project_visibility,
        name="project-visibility",
    ),
    path("projects/<int:pk>/grant/", views.project_grant, name="project-grant"),
    path("projects/<int:pk>/revoke/", views.project_revoke, name="project-revoke"),
    path(
        "projects/<int:pk>/teams/associate/",
        views.project_associate_team,
        name="project-associate-team",
    ),
    path(
        "projects/<int:pk>/teams/disassociate/",
        views.project_disassociate_team,
        name="project-disassociate-team",
    ),
    path(
        "projects/<int:pk>/teams/permissions/",
        views.project_team_permissions,
        name="project-team-permissions",
    ),
]
