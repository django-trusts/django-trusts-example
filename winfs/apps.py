from django.apps import AppConfig


class WinfsConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "winfs"
    verbose_name = "Windows filesystem ACL example"

    def ready(self):
        from trusts.context import Context

        from .models import WinNode, WinStream

        # Honest direct Context registration only: each node owns its
        # security-descriptor row. Related is for sidecars that share that
        # node's DACL, not for filesystem children.
        Context.register_direct(WinNode, scope_field="security_descriptor")
        Context.register_related(WinStream, through="node")
