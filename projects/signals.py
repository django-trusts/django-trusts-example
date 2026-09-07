from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .grants import enroll_in_public_readers


@receiver(post_save, sender=get_user_model())
def enroll_user_in_public_readers(sender, instance, created, **kwargs):
    """Keep public-readers membership aligned with 'any signed-in user'.

    New accounts get the group row so Trusts has_perm / list JOINs see them.
    Existing accounts are synced by seed_demo / sync_public_readers.
    """
    if created and not kwargs.get("raw"):
        enroll_in_public_readers(instance)
