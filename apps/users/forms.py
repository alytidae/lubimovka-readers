from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from .models import User

class CustomUserAddForm(forms.ModelForm):
    ROLE_CHOICES = (
        ('reader', 'Reader'),
        ('moderator', 'Moderator'),
        ('admin', 'Admin'),
    )

    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True)
    
    password = forms.CharField(
        label='Password',
        required=False, 
        widget=forms.PasswordInput, 
        help_text="Required for new users. Leave blank if the user already exists in the system."
    )
    
    password_confirm = forms.CharField(
        label='Password confirmation',
        required=False,
        widget=forms.PasswordInput,
        help_text="Enter the same password as before, for verification."
    )

    class Meta:
        model = User
        fields = ('email', 'telegram_username', 'first_name', 'last_name', 'role')

    def __init__(self, *args, **kwargs):
        self.creator_role = kwargs.pop('creator_role', 'reader')
        super().__init__(*args, **kwargs)

        if self.creator_role == 'moderator':
            self.fields['role'].choices = [('reader', 'Reader')]

    def validate_unique(self):
        exclude = self._get_validation_exclusions()
        
        if 'email' not in exclude:
            exclude.add('email') 
        
        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as e:
            self._update_errors(e)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        
        if email:
            user_exists = User.objects.filter(email=email).exists()
            
            if not user_exists:
                if not password:
                    self.add_error('password', "Password is required for new users.")
                elif password != password_confirm:
                    self.add_error('password_confirm', "The two password fields didn't match.")
        
        return cleaned_data

    def save(self, commit=True):
        email = self.cleaned_data.get('email')
        user = User.objects.filter(email=email).first()
        
        if not user:
            user = super().save(commit=False)
            user.set_password(self.cleaned_data.get('password'))
            if commit:
                user.save()
        
        return user

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
