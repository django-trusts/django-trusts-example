from django.core.management.base import BaseCommand

from winfs.constants import R
from winfs.fixtures import allow, standard_tree


class Command(BaseCommand):
    help = "Seed the bounded Windows ACL demo volume (idempotent enough for a fresh DB)."

    def handle(self, *args, **options):
        from winfs.models import WinVolume

        if WinVolume.objects.filter(name="vol").exists():
            self.stdout.write("winfs volume 'vol' already exists.")
            return
        data = standard_tree()
        allow(data["vol"], data["eng"], R, ci=True)
        allow(data["proj"], data["eng"], R, oi=True, ci=True)
        self.stdout.write(
            "Seeded volume vol/ with alice, bob, carol, admin, and eng "
            "(proj allow:eng:R OI|CI)."
        )
