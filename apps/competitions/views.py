from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, ListView, DetailView
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from .models import Competition
from .forms import CompetitionCreationForm, CompetitionChangeForm 

class CompetitionCreateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView):
    model = Competition
    template_name = "competition_create.html"
    form_class = CompetitionCreationForm
    success_message = "\u2705 %(title)s was created successfully" 

    def get_success_url(self):
        return self.object.get_absolute_url()

    def test_func(self):
        return self.request.user.is_superuser

class CompetitionUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView):
    model = Competition
    template_name = "competition_update.html"
    form_class = CompetitionChangeForm
    success_message = "\u2705 %(title)s was updated successfully"

    def get_success_url(self):
        return self.object.get_absolute_url()

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
            
        return user.competition_roles.filter(
            competition=self.get_object(), 
            role='admin'
        ).exists()

class CompetitionListView(LoginRequiredMixin, ListView):
    model = Competition
    template_name = "competition_list.html"
    context_object_name = "competitions"

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Competition.objects.all()
            
        return Competition.objects.filter(roles__user=user).distinct()

class CompetitionDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Competition
    template_name = "competition_detail.html"
    context_object_name = "competition"

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
            
        return user.competition_roles.filter(
            competition=self.get_object()
        ).exists()
