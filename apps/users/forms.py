from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from .models import User

class CustomUserCreationForm(UserCreationForm):
    ROLE_CHOICES = (
        ('reader', 'Reader'),
        ('moderator', 'Moderator'),
        ('admin', 'Admin'),
    )

    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True)

    class Meta:
        model = User
        fields = ('email', 'telegram_username', 'first_name', 'last_name', 'role')

    def __init__(self, *args, **kwargs):
        self.creator_role = kwargs.pop('creator_role', 'reader')
        super().__init__(*args, **kwargs)

        if self.creator_role == 'moderator':
            self.fields['role'].choices = [('reader', 'Reader')]

class CustomUserChangeForm(forms.ModelForm):
    ROLE_CHOICES = (
        ('reader', 'Reader'),
        ('moderator', 'Moderator'),
        ('admin', 'Admin'),
    )

    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True)

    class Meta:
        model = User
        fields = ('email', 'telegram_username', 'first_name', 'last_name', 'role', 'is_active')

    def __init__(self, *args, **kwargs):
        self.editor_role = kwargs.pop('editor_role', 'reader')
        current_role = kwargs.pop('current_role', 'reader')
        
        super().__init__(*args, **kwargs)

        self.fields['role'].initial = current_role

        if self.editor_role == 'moderator':
            self.fields['role'].choices = [('reader', 'Reader')]
