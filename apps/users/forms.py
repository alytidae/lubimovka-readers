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
    role_is_active = forms.BooleanField(required=False, label='Active in this competition')

    class Meta:
        model = User
        fields = ('email', 'telegram_username', 'first_name', 'last_name', 'role')

    def __init__(self, *args, **kwargs):
        self.editor_role = kwargs.pop('editor_role', 'reader')
        current_role = kwargs.pop('current_role', 'reader')
        current_role_is_active = kwargs.pop('current_role_is_active', True)
        
        super().__init__(*args, **kwargs)

        self.fields['role'].initial = current_role
        self.fields['role_is_active'].initial = current_role_is_active

        if self.editor_role == 'moderator':
            self.fields['role'].choices = [('reader', 'Reader')]
