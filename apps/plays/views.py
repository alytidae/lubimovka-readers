from django.shortcuts import render
from django.urls import reverse
from django.views.generic import ListView, DetailView
from django.views import View
from .models import Play
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from apps.competitions.mixins import CompetitionContextMixin
from apps.competitions.models import CompetitionRole, Competition
from django.db.models import Q
from apps.reviews.models import Review
from django.contrib import messages

class PlayDetailView(LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, DetailView):
    model = Play
    template_name = "play_detail.html"

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.competition_roles.filter(competition=competition).exists():
            return True
            
        return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        play = self.object
        competition = self.get_competition()
        user = self.request.user
        
        base_reviews_qs = Review.objects.filter(
            play=play,
            status=Review.Status.SUBMITTED,
            is_obsolete=False
        ).select_related('reader')

        visible_reviews = []

        if user.is_superuser or user.get_role(competition) in ['admin', 'moderator']:
            visible_reviews = base_reviews_qs.all()
        else:
            filters = Q(reader=user)
            
            if competition.are_phase1_reviews_visible:
                filters |= Q(phase=Review.Phase.PHASE_1, is_hidden=False)
                
            if competition.are_phase2_reviews_visible:
                filters |= Q(phase=Review.Phase.PHASE_2, is_hidden=False)
                
            visible_reviews = base_reviews_qs.filter(filters).distinct()

        context['reviews'] = visible_reviews
        
        context['my_active_review'] = Review.objects.filter(
            play=play, 
            reader=user, 
            status__in=[Review.Status.ASSIGNED, Review.Status.DRAFT],
            is_obsolete=False
        ).first()

        return context

class PlayListView(LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, ListView):
    model = Play
    template_name = "play_list.html"
    ordering = ['is_active', 'author_email']

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.competition_roles.filter(competition=competition).exists():
            return True
            
        return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

    def get_queryset(self):
        competition = self.get_competition()
        user = self.request.user

        qs = super().get_queryset().filter(competition=competition).distinct()

        if user.is_superuser or user.get_role(competition) in ["admin", "moderator"]:
            return qs
            
        return qs.filter(
            reviews__reader=user, 
            reviews__is_obsolete=False
        ).distinct()

class PlayActivateView(LoginRequiredMixin, UserPassesTestMixin, View):
    def post(self, request, *args, **kwargs):
        play = get_object_or_404(
            Play,
            pk=kwargs["pk"],
            competition__slug=kwargs["competition_slug"]
        )

        if not play.is_active:
            play.is_active = True
            play.save(update_fields=["is_active"])
            messages.success(request, f"✅ {play.title} was activated successfully")
        else:
            messages.info(request, f"{play.title} is already active")

        return redirect(play.get_absolute_url())

    def test_func(self):
        competition = get_object_or_404(Competition, slug=self.kwargs["competition_slug"])
        if self.request.user.is_superuser:
            return True

        if self.request.user.get_role(competition) in ["admin", "moderator"]:
            return True

        return False 

class PlayDeactivateView(LoginRequiredMixin, UserPassesTestMixin, View):
    def post(self, request, *args, **kwargs):
        play = get_object_or_404(
            Play,
            pk=kwargs["pk"],
            competition__slug=kwargs["competition_slug"]
        )

        if play.is_active:
            play.is_active = False
            play.save(update_fields=["is_active"])
            messages.success(request, f"✅ {play.title} was deactivated successfully")
        else:
            messages.info(request, f"{play.title} is already not active")

        return redirect(play.get_absolute_url())

    def test_func(self):
        competition = get_object_or_404(Competition, slug=self.kwargs["competition_slug"])
        if self.request.user.is_superuser:
            return True

        if self.request.user.get_role(competition) in ["admin", "moderator"]:
            return True

        return False 
