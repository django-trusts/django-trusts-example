from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .grants import PUBLIC_GROUP_NAME, enroll_in_public_readers
from .models import Project

User = get_user_model()

admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Keep public-readers out of the groups picker; re-enroll after M2M save."""

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        formfield = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "groups":
            formfield.queryset = formfield.queryset.exclude(name=PUBLIC_GROUP_NAME)
        return formfield

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        enroll_in_public_readers(form.instance)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "trust")
    search_fields = ("title", "slug")
