from django.shortcuts import render
from django.urls import reverse
from django.views.generic import ListView, DetailView
from django.views import View
from .models import Play
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from apps.competitions.mixins import CompetitionContextMixin
from apps.competitions.models import CompetitionRole, Competition
from django.contrib import messages

class PlayDetailView(LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, DetailView):
    model = Play
    template_name = "play_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        return context

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.competition_roles.filter(competition=competition).exists():
            return True

class PlayListView(LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, ListView):
    model = Play
    template_name = "play_list.html"

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.competition_roles.filter(competition=competition).exists():
            return True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        return context

    def get_queryset(self):
        competition = self.get_competition()

        return Play.objects.filter(competition=competition).distinct()

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
