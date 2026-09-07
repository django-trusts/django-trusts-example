from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from .grants import PUBLIC_GROUP_NAME, enroll_in_public_readers, sync_public_readers

User = get_user_model()


@receiver(post_save, sender=User)
def enroll_user_in_public_readers(sender, instance, created, **kwargs):
    """Enroll new accounts so Trusts group grants apply immediately."""
    if created and not kwargs.get("raw"):
        enroll_in_public_readers(instance)


@receiver(m2m_changed, sender=User.groups.through)
def restore_public_readers_after_group_save(sender, instance, action, reverse, pk_set, **kwargs):
    """public-readers is system-maintained: every user stays a member.

    ModelForm / admin save M2M *after* post_save. A groups=[] submit would
    otherwise wipe the membership this app just added. Re-apply after
    post_clear / post_remove on either side of the User↔Group relation.
    """
    if action not in ("post_remove", "post_clear"):
        return
    if reverse:
        if getattr(instance, "name", None) != PUBLIC_GROUP_NAME:
            return
        if action == "post_clear":
            sync_public_readers()
            return
        if pk_set:
            for user in User.objects.filter(pk__in=pk_set):
                enroll_in_public_readers(user)
        return
    enroll_in_public_readers(instance)
