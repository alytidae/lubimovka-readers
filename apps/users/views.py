from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import render
from django.views.generic import CreateView, UpdateView
from django.urls import reverse_lazy
from .models import User
from .forms import CustomUserCreationForm, CustomUserChangeForm
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin

class UserCreateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView):
    model = User
    template_name = "user_create.html"
    form_class = CustomUserCreationForm
    success_message = "\u2705 %(email)s was created successfully"
    success_url = reverse_lazy('users_create')

    def test_func(self):
        return True

class UserUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView):
    model = User
    template_name = "user_update.html"
    form_class = CustomUserChangeForm
    success_message = "\u2705 %(email)s was updated successfully"

    def get_success_url(self):
        return reverse_lazy('users:update', kwargs={'pk': self.object.pk})

    def test_func(self):
        return True
