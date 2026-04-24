from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import render
from django.urls import reverse
from django.views.generic import CreateView, UpdateView, ListView, DetailView
from .models import User
from .forms import CustomUserCreationForm, CustomUserChangeForm
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from apps.competitions.mixins import CompetitionContextMixin
from apps.competitions.models import CompetitionRole

class UserCreateView(LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, SuccessMessageMixin, CreateView):
    model = User
    template_name = "create_update.html"
    form_class = CustomUserCreationForm
    success_message = "\u2705 %(email)s was created successfully"

    def test_func(self):
        competition = self.get_competition()
        
        if self.request.user.is_superuser:
            return True

        return self.request.user.competition_roles.filter(
            competition=competition,
            role__in=['admin', 'moderator']
        ).exists()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        
        competition = self.get_competition()
        creator_role_record = self.request.user.competition_roles.filter(competition=competition).first()
        
        if creator_role_record:
            kwargs['creator_role'] = creator_role_record.role
            
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        
        selected_role = form.cleaned_data.get('role')
        
        CompetitionRole.objects.create(
            user=self.object,
            competition=self.get_competition(),
            role=selected_role
        )
        
        return response

    def get_success_url(self):
        return reverse('users:create', kwargs={'competition_slug': self.kwargs.get('competition_slug')})

class UserUpdateView(LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, SuccessMessageMixin, UpdateView):
    model = User
    template_name = "create_update.html"
    form_class = CustomUserChangeForm
    success_message = "\u2705 %(email)s was updated successfully"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        competition = self.get_competition()
        
        editor_role_record = self.request.user.competition_roles.filter(competition=competition).first()
        if editor_role_record:
            kwargs['editor_role'] = editor_role_record.role
            
        target_role_record = self.object.competition_roles.filter(competition=competition).first()
        if target_role_record:
            kwargs['current_role'] = target_role_record.role
            
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        
        selected_role = form.cleaned_data.get('role')
        competition = self.get_competition()
        
        target_role_record = self.object.competition_roles.filter(competition=competition).first()
        
        if target_role_record and target_role_record.role != selected_role:
            target_role_record.role = selected_role
            target_role_record.save()
            
        return response

    def get_success_url(self):
        return reverse('users:update', kwargs={'pk': self.object.pk, 'competition_slug': self.kwargs.get('competition_slug')})

    def test_func(self):
        competition = self.get_competition()
        editor = self.request.user
        target_user = self.get_object() 

        if editor.is_superuser:
            return True

        editor_role_record = editor.competition_roles.filter(competition=competition).first()
        target_role_record = target_user.competition_roles.filter(competition=competition).first()

        if not editor_role_record:
            return False

        editor_role = editor_role_record.role

        if editor_role == 'admin':
            return True

        if editor_role == 'moderator':
            is_editing_self = (editor == target_user)
            is_editing_reader = (target_role_record and target_role_record.role == 'reader')
            
            if is_editing_self or is_editing_reader:
                return True

        return False

class UserDetailView(LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, DetailView):
    model = User
    template_name = "user_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        competition = self.get_competition()
        context['object'].role = self.get_object().get_role(competition)

        return context

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user == self.get_object():
            if self.get_object().competition_roles.filter(competition=competition).exists():
                return True

        return self.request.user.competition_roles.filter(
            competition=competition,
            role__in=['admin', 'moderator']
        ).exists()

class UserListView(LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, ListView):
    model = User
    template_name = "user_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        competition = self.get_competition()

        for user in context['object_list']:
            user.role = user.get_role(competition)

        return context

    def get_queryset(self):
        competition = self.get_competition()

        return User.objects.filter(competition_roles__competition=competition).distinct()

    def test_func(self):
        competition = self.get_competition()
         
        if self.request.user.is_superuser:
            return True

        return self.request.user.competition_roles.filter(
            competition=competition,
            role__in=['admin', 'moderator']
        ).exists()
