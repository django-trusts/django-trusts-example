from django.contrib import admin

from . import models


@admin.register(models.WinSid)
class WinSidAdmin(admin.ModelAdmin):
    search_fields = ("sid_string",)


@admin.register(models.WinPrincipal)
class WinPrincipalAdmin(admin.ModelAdmin):
    list_display = ("sid", "user")


@admin.register(models.WinLocalGroup)
class WinLocalGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "sid")


@admin.register(models.WinSidMember)
class WinSidMemberAdmin(admin.ModelAdmin):
    list_display = ("group", "member")


@admin.register(models.WinVolume)
class WinVolumeAdmin(admin.ModelAdmin):
    list_display = ("name",)


class WinAceInline(admin.TabularInline):
    model = models.WinAce
    extra = 0


@admin.register(models.WinSecurityDescriptor)
class WinSecurityDescriptorAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "se_dacl_protected")
    inlines = (WinAceInline,)


@admin.register(models.WinNode)
class WinNodeAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "volume", "parent", "security_descriptor")


@admin.register(models.WinStream)
class WinStreamAdmin(admin.ModelAdmin):
    list_display = ("name", "node")
