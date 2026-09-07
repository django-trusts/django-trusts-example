from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils.text import slugify

from .grants import CHANGE, READ, unassociated_groups
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
            "Associates the public-readers group with this project's trust "
            "and enables local read. Association alone does not grant access."
        ),
    )


class GrantForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.order_by("username"))
    permission = forms.ChoiceField(choices=PERM_CHOICES, initial=READ)


class AssociateTeamForm(forms.Form):
    group = forms.ModelChoiceField(
        queryset=Group.objects.none(),
        label="Team",
        help_text=(
            "Attaches the team to this project's trust. This does not grant "
            "access. Enable local rights after associating."
        ),
        empty_label="Select a team to associate",
    )

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:
            self.fields["group"].queryset = unassociated_groups(project)
