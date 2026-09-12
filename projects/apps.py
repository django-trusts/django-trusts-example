from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "projects"
    verbose_name = "Projects"

    def ready(self):
        from trusts.zero.apps import CANONICAL_BACKEND_PATH, zero_config
        from trusts.zero.registration import register_zero_content

        from .models import Project

        handle = zero_config().configured_backend(CANONICAL_BACKEND_PATH)
        register_zero_content(handle.registry, Project)

        from . import signals  # noqa: F401 — enroll new users in public-readers
