from django.http import HttpResponseRedirect
from django.utils.http import urlencode
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import render
from django.urls import reverse
from django.views.generic import CreateView, UpdateView, ListView, DetailView
from .models import User
from .forms import CustomUserChangeForm, CustomUserAddForm
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from apps.competitions.mixins import CompetitionContextMixin
from apps.competitions.models import CompetitionRole
from django.views import View
from django.db.models import Avg, F
from apps.reviews.models import Review
from django.shortcuts import redirect


class UserCreateView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    CompetitionContextMixin,
    SuccessMessageMixin,
    CreateView,
):
    model = User
    template_name = "create_update.html"

    form_class = CustomUserAddForm
    success_message = "\u2705 %(email)s was processed successfully"

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        return self.request.user.competition_roles.filter(
            competition=competition, role__in=["admin", "moderator"], is_active=True
        ).exists()

    def get_initial(self):
        initial = super().get_initial()
        initial["email"] = self.request.GET.get("email", "")
        initial["role"] = self.request.GET.get("role", "reader")
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.request.user.is_superuser:
            kwargs["creator_role"] = "admin"
            return kwargs

        competition = self.get_competition()
        creator_role_record = self.request.user.competition_roles.filter(
            competition=competition
        ).first()

        if creator_role_record:
            kwargs["creator_role"] = creator_role_record.role

        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)

        selected_role = form.cleaned_data.get("role")

        CompetitionRole.objects.update_or_create(
            user=self.object,
            competition=self.get_competition(),
            defaults={"role": selected_role, "is_active": True},
        )

        return response

    def get_success_url(self):
        return reverse(
            "users:create",
            kwargs={"competition_slug": self.kwargs.get("competition_slug")},
        )


class UserUpdateView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    CompetitionContextMixin,
    SuccessMessageMixin,
    UpdateView,
):
    model = User
    template_name = "create_update.html"
    form_class = CustomUserChangeForm
    success_message = "\u2705 %(email)s was updated successfully"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        competition = self.get_competition()

        editor_role_record = self.request.user.competition_roles.filter(
            competition=competition
        ).first()
        if editor_role_record:
            kwargs["editor_role"] = editor_role_record.role

        target_role_record = self.object.competition_roles.filter(
            competition=competition
        ).first()
        if target_role_record:
            kwargs["current_role"] = target_role_record.role
            kwargs["current_role_is_active"] = target_role_record.is_active

        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)

        selected_role = form.cleaned_data.get("role")
        selected_is_active = form.cleaned_data.get("role_is_active", True)
        competition = self.get_competition()

        target_role_record = self.object.competition_roles.filter(
            competition=competition
        ).first()

        if target_role_record:
            target_role_record.role = selected_role
            target_role_record.is_active = selected_is_active
            target_role_record.save()

        return response

    def get_success_url(self):
        return reverse(
            "users:update",
            kwargs={
                "pk": self.object.pk,
                "competition_slug": self.kwargs.get("competition_slug"),
            },
        )

    def test_func(self):
        competition = self.get_competition()
        editor = self.request.user
        target_user = self.get_object()

        if editor.is_superuser:
            return True

        editor_role_record = editor.competition_roles.filter(
            competition=competition, is_active=True
        ).first()
        target_role_record = target_user.competition_roles.filter(
            competition=competition
        ).first()

        if not editor_role_record:
            return False

        editor_role = editor_role_record.role

        if editor_role == "admin":
            return True

        if editor_role == "moderator":
            is_editing_self = editor == target_user
            is_editing_reader = (
                target_role_record and target_role_record.role == "reader"
            )

            if is_editing_self or is_editing_reader:
                return True

        return False


class UserDetailView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, DetailView
):
    model = User
    template_name = "user_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.get_competition()
        user_obj = self.get_object()

        context["object"].role = user_obj.get_role(competition)

        reviews_qs = Review.objects.filter(
            reader=user_obj, play__competition=competition, is_obsolete=False
        ).select_related("play", "reader")

        submitted_qs = reviews_qs.filter(status=Review.Status.SUBMITTED)
        active_qs = reviews_qs.filter(
            status__in=[Review.Status.ASSIGNED, Review.Status.DRAFT]
        )

        context["reviews"] = reviews_qs.order_by("-created_at")

        submitted_count = submitted_qs.count()
        active_count = active_qs.count()
        context["submitted_count"] = submitted_count
        context["active_count"] = active_count
        context["yes_count"] = submitted_qs.filter(verdict=True).count()
        context["no_count"] = submitted_qs.filter(verdict=False).count()
        context["total_assigned"] = submitted_count + active_count

        speed_aggregate = submitted_qs.aggregate(
            avg_time=Avg(F("submitted_at") - F("created_at"))
        )

        avg_time = speed_aggregate["avg_time"]
        if avg_time:
            days = avg_time.days
            hours = avg_time.seconds // 3600
            context["avg_reading_speed"] = (
                f"{days}d {hours}h" if days > 0 else f"{hours}h"
            )
        else:
            context["avg_reading_speed"] = "-"

        return context

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user == self.get_object():
            if (
                self.get_object()
                .competition_roles.filter(competition=competition, is_active=True)
                .exists()
            ):
                return True

        return self.request.user.competition_roles.filter(
            competition=competition, role__in=["admin", "moderator"], is_active=True
        ).exists()


class UserListView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, ListView
):
    model = User
    template_name = "user_list.html"

    def test_func(self):
        competition = self.get_competition()
        user = self.request.user

        if user.is_superuser:
            return True

        return user.competition_roles.filter(
            competition=competition, is_active=True
        ).exists()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        competition = self.get_competition()
        current_user_role = self.request.user.get_role(competition)

        visible_users = []

        for user in context["object_list"]:
            role_record = user.competition_roles.filter(competition=competition).first()
            user.role = user.get_role(competition)
            user.role_is_active = role_record.is_active if role_record else False

            if current_user_role == "reader":
                if user.role in ["moderator"] and user.is_active:
                    visible_users.append(user)
            else:
                visible_users.append(user)

        context["object_list"] = visible_users
        context["user"] = self.request.user
        context["user"].role = current_user_role

        return context

    def get_queryset(self):
        competition = self.get_competition()

        return User.objects.filter(
            competition_roles__competition=competition
        ).distinct()


class UserInviteView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, View
):
    def post(self, request, *args, **kwargs):
        competition = self.get_competition()
        email = request.POST.get("email")
        role = request.POST.get("role")

        if not email or not role:
            messages.error(request, "Email and role are required.")
            return redirect("users:list", competition_slug=competition.slug)

        email = User.objects.normalize_email(email).lower()

        user = User.objects.filter(email=email).first()

        if user:
            CompetitionRole.objects.update_or_create(
                user=user,
                competition=competition,
                defaults={"role": role, "is_active": True},
            )
            messages.success(
                request,
                f"✅ User {email} has been automatically added to this competition.",
            )
            return redirect("users:list", competition_slug=competition.slug)
        else:
            base_url = reverse(
                "users:create", kwargs={"competition_slug": competition.slug}
            )
            query_string = urlencode({"email": email, "role": role})
            return HttpResponseRedirect(f"{base_url}?{query_string}")

    def test_func(self):
        competition = self.get_competition()
        if self.request.user.is_superuser:
            return True
        return self.request.user.competition_roles.filter(
            competition=competition, role__in=["admin", "moderator"], is_active=True
        ).exists()
