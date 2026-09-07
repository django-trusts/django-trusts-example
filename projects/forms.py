from django import forms
from django.contrib.auth import get_user_model

from .grants import CHANGE, READ
from .models import Project

User = get_user_model()

PERM_CHOICES = (
    (READ, "Read"),
    (CHANGE, "Read and change"),
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ("title", "description")


class VisibilityForm(forms.Form):
    is_public = forms.BooleanField(
        required=False,
        label="Public (any signed-in user can read)",
        help_text="Attaches the public-readers group to this project's trust.",
    )


class GrantForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.order_by("username"))
    permission = forms.ChoiceField(choices=PERM_CHOICES, initial=READ)
