"""Forms for account creation and provider linking."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Provider, Theme, UserIntegration

User = get_user_model()


class SignupForm(UserCreationForm):
    """Account creation form (username + email + passwords)."""

    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ("username", "email")


class SparkyLinkForm(forms.Form):
    """Link (or update) a SparkyFitness integration via its API key."""

    api_key = forms.CharField(
        label="SparkyFitness API key",
        max_length=512,
        required=False,
        help_text="Paste your fit.randalls.cc API key. Leave blank to use demo data.",
        widget=forms.PasswordInput(render_value=True),
    )

    def save(self, user):
        """Create/update the user's SparkyFitness integration."""
        integration, _ = UserIntegration.objects.get_or_create(
            user=user, provider=Provider.SPARKYFITNESS
        )
        integration.credentials = {"api_key": self.cleaned_data["api_key"]}
        integration.is_active = True
        integration.save()
        return integration


class LiftosaurLinkForm(forms.Form):
    """Link (or update) a Liftosaur integration via its API key."""

    api_key = forms.CharField(
        label="Liftosaur API key",
        max_length=512,
        required=False,
        help_text="Paste your liftosaur.com API key (lftsk_...). Leave blank to use demo data.",
        widget=forms.PasswordInput(render_value=True),
    )

    def save(self, user):
        """Create/update the user's Liftosaur integration."""
        integration, _ = UserIntegration.objects.get_or_create(
            user=user, provider=Provider.LIFTOSAUR
        )
        integration.credentials = {"api_key": self.cleaned_data["api_key"]}
        integration.is_active = True
        integration.save()
        return integration


class ThemeForm(forms.Form):
    """Update the account's color-theme preference (profile page).

    The profile view posts ``action=theme`` together with the chosen value.
    """

    theme = forms.ChoiceField(choices=Theme.choices)

