from django import forms
from django.contrib.auth import get_user_model
from django.utils.text import slugify

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

    def clean_title(self):
        title = self.cleaned_data["title"]
        if not slugify(title):
            raise forms.ValidationError(
                "Title must include letters or numbers so a URL slug can be created."
            )
        return title


class VisibilityForm(forms.Form):
    is_public = forms.BooleanField(
        required=False,
        label="Public (any signed-in user can read)",
        help_text=(
            "Attaches the public-readers group to this project's trust. "
            "Signed-in accounts are enrolled in that group (including users "
            "created after seed)."
        ),
    )


class GrantForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.order_by("username"))
    permission = forms.ChoiceField(choices=PERM_CHOICES, initial=READ)
