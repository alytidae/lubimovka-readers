from django.contrib.messages.views import SuccessMessageMixin
import traceback
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, ListView, DetailView
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from .models import Competition
from .mixins import CompetitionContextMixin
from .forms import CompetitionCreationForm, CompetitionChangeForm
from .services import sync_plays_from_google_sheet
from django.views import View
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages


class CompetitionCreateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView):
    model = Competition
    template_name = "create_update.html"
    form_class = CompetitionCreationForm
    success_message = "\u2705 %(title)s was created successfully"

    def get_success_url(self):
        return self.object.get_absolute_url()

    def test_func(self):
        return self.request.user.is_superuser


class CompetitionUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView):
    model = Competition
    template_name = "create_update.html"
    form_class = CompetitionChangeForm
    success_message = "\u2705 %(title)s was updated successfully"

    def get_success_url(self):
        return self.object.get_absolute_url()

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True

        return user.competition_roles.filter(
            competition=self.get_object(), is_active=True
        ).exists()


class CompetitionListView(LoginRequiredMixin, ListView):
    model = Competition
    template_name = "competition_list.html"
    context_object_name = "competitions"

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Competition.objects.all()

        return Competition.objects.filter(roles__user=user, roles__is_active=True).distinct()


class CompetitionDetailView(LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, DetailView):
    model = Competition
    template_name = "competition_detail.html"
    context_object_name = "competition"

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True

        return user.competition_roles.filter(competition=self.get_object()).exists()


class CompetitionSyncView(LoginRequiredMixin, UserPassesTestMixin, View):
    def post(self, request, *args, **kwargs):
        competition_slug = self.kwargs.get("competition_slug")
        competition = get_object_or_404(Competition, slug=competition_slug)

        try:
            count = sync_plays_from_google_sheet(competition)
            messages.success(request, f"Successfully synced {count} plays.")
        except Exception as e:
            messages.error(request, f"Sync error: {type(e).__name__}: {e}")
            print(traceback.format_exc())

        return redirect("plays:list", competition_slug=competition.slug)

    def test_func(self):
        return (
            self.request.user.is_superuser
            or self.request.user.competition_roles.filter(
                competition__slug=self.kwargs.get("competition_slug"),
                role__in=["admin", "moderator"],
                is_active=True,
            ).exists()
        )
