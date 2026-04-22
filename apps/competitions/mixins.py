from django.shortcuts import get_object_or_404
from .models import Competition

class CompetitionContextMixin:
    def get_competition(self):
        slug = self.kwargs.get('competition_slug')
        return get_object_or_404(Competition, slug=slug)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_competition'] = self.get_competition()
        return context
