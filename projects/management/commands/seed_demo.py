from django.core.management.base import BaseCommand

from projects.demo import PASSWORD, seed_demo


class Command(BaseCommand):
    help = "Create demo users, groups/organizations, trusts, and projects."

    def handle(self, *args, **options):
        data = seed_demo()
        self.stdout.write(self.style.SUCCESS("Seeded demo data."))
        self.stdout.write(f"Users (password {PASSWORD}): {', '.join(sorted(data['users']))}")
        self.stdout.write("Projects:")
        for slug, project in data["projects"].items():
            self.stdout.write(f"  - {project.title} ({slug}) trust={project.trust_id}")
