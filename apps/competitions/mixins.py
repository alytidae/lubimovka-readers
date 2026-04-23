from django.shortcuts import get_object_or_404
from .models import Competition

class CompetitionContextMixin:
    def get_competition(self):
        if hasattr(self, 'object') and isinstance(self.object, Competition):
            return self.object

        slug = self.kwargs.get('slug') or self.kwargs.get('competition_slug')
        
        return get_object_or_404(Competition, slug=slug)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.get_competition()
        user = self.request.user

        is_admin = False
        is_moderator = False
        is_reader = False

        user_role = user.competition_roles.filter(competition=competition).first()
        if user_role:
            if user_role.role == 'admin':
                is_admin = True
            elif user_role.role == 'moderator':
                is_moderator = True
            elif user_role.role == 'reader':
                is_reader = True

        if user.is_superuser:
            is_admin = True

        context.update({
            'current_competition': competition,
            'is_admin': is_admin,
            'is_moderator': is_moderator or is_admin, 
            'is_reader': is_reader, 
        })
        return context
