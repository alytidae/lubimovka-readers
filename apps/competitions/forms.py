from django import forms
from .models import Competition

class CompetitionCreationForm(forms.ModelForm):
    class Meta:
        model = Competition
        fields = (
            'title', 
            'date', 
            'google_sheet_url', 
            'play_title_sheet_column_name', 
            'play_link_sheet_column_name'
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'google_sheet_url': forms.URLInput(attrs={
                'placeholder': 'https://docs.google.com/spreadsheets/d/...'
            }),
        }

class CompetitionChangeForm(forms.ModelForm):
    class Meta:
        model = Competition
        fields = (
            'title', 
            'date', 
            'status',
            'are_phase1_reviews_visible',
            'are_phase2_reviews_visible'
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }
