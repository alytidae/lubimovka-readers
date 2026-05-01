from django import forms
from .models import Review

class ReviewUpdateForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['verdict', 'comment']
