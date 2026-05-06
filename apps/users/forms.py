from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import User


class CustomUserAddForm(forms.ModelForm):
    ROLE_CHOICES = (
        ("reader", _("Reader")),
        ("moderator", _("Moderator")),
        ("admin", _("Admin")),
    )

    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True)

    password = forms.CharField(
        label=_("Password"),
        required=True,
        widget=forms.PasswordInput,
        help_text=_("Required for new users."),
    )

    password_confirm = forms.CharField(
        label=_("Password confirmation"),
        required=True,
        widget=forms.PasswordInput,
        help_text=_("Enter the same password as before, for verification."),
    )

    class Meta:
        model = User
        fields = ("email", "telegram_username", "first_name", "last_name", "role")

    def __init__(self, *args, **kwargs):
        self.creator_role = kwargs.pop("creator_role", "reader")
        super().__init__(*args, **kwargs)

        if self.creator_role == "moderator":
            self.fields["role"].choices = [("reader", _("Reader"))]

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if email and User.objects.filter(email=email).exists():
            self.add_error(
                "email",
                _(
                    "A user with this email already exists. Use the invite form instead."
                ),
            )

        if password and password_confirm and password != password_confirm:
            self.add_error(
                "password_confirm", _("The two password fields didn't match.")
            )

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data.get("password"))

        user.email = User.objects.normalize_email(user.email).lower()

        if commit:
            user.save()
        return user


class CustomUserChangeForm(forms.ModelForm):
    ROLE_CHOICES = (
        ("reader", _("Reader")),
        ("moderator", _("Moderator")),
        ("admin", _("Admin")),
    )

    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True)
    role_is_active = forms.BooleanField(
        required=False, label=_("Active in this competition")
    )

    class Meta:
        model = User
        fields = ("email", "telegram_username", "first_name", "last_name", "role")

    def __init__(self, *args, **kwargs):
        self.editor_role = kwargs.pop("editor_role", "reader")
        current_role = kwargs.pop("current_role", "reader")
        current_role_is_active = kwargs.pop("current_role_is_active", True)

        super().__init__(*args, **kwargs)

        self.fields["role"].initial = current_role
        self.fields["role_is_active"].initial = current_role_is_active

        if self.editor_role == "moderator":
            self.fields["role"].choices = [("reader", _("Reader"))]
