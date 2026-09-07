from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "projects"
    verbose_name = "Projects"

    def ready(self):
        from . import signals  # noqa: F401 — enroll new users in public-readers
