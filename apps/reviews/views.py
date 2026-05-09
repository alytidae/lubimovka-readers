from django.views import View
from django.views.generic.edit import UpdateView
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.utils.translation import gettext_lazy as _
from apps.competitions.mixins import CompetitionContextMixin
from .models import Review
from .forms import ReviewUpdateForm
from .services import (
    assign_play,
    mark_public,
    mark_hidden,
    mark_obsolete,
    restore,
    save_draft,
    submit,
)
from django.contrib import messages


class ReviewRequestPlayView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, View
):
    def post(self, request, *args, **kwargs):
        competition = self.get_competition()
        result = assign_play(request.user, competition)

        if result.success:
            messages.success(request, result.message)
        else:
            messages.info(request, result.message)

        return redirect("plays:list", competition_slug=competition.slug)

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.get_role(competition) in ["reader"]:
            return True
        return False


class ReviewSaveDraftView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, View
):
    def post(self, request, *args, **kwargs):
        competition = self.get_competition()

        review = get_object_or_404(
            Review.objects.filter(
                pk=kwargs["pk"],
                play__competition__slug=kwargs["competition_slug"],
                reader=request.user,
            ).exclude(status=Review.Status.SUBMITTED)
        )

        form = ReviewUpdateForm(request.POST, instance=review)

        if form.is_valid():
            result = save_draft(
                review, form.cleaned_data["verdict"], form.cleaned_data["comment"]
            )

            if result.success:
                messages.success(request, result.message)
            else:
                messages.warning(request, result.message)
        else:
            messages.error(request, _("Invalid data submitted."))

        return redirect(
            "plays:detail", pk=review.play.id, competition_slug=competition.slug
        )

    def test_func(self):
        competition = self.get_competition()

        has_access = Review.objects.filter(
            id=self.kwargs.get("pk"), reader=self.request.user
        ).exists()

        if has_access and self.request.user.get_role(competition) in ["reader"]:
            return True
        return False


class ReviewSubmitView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, View
):
    def post(self, request, *args, **kwargs):
        competition = self.get_competition()

        review = get_object_or_404(
            Review.objects.filter(
                pk=kwargs["pk"],
                play__competition__slug=kwargs["competition_slug"],
                reader=request.user,
            )
        )

        form = ReviewUpdateForm(request.POST, instance=review)

        if form.is_valid():
            result = submit(
                review, form.cleaned_data["verdict"], form.cleaned_data["comment"]
            )

            if result.success:
                messages.success(request, result.message)
            else:
                messages.warning(request, result.message)
        else:
            messages.error(request, _("Invalid data submitted."))

        return redirect(
            "plays:detail", pk=review.play.id, competition_slug=competition.slug
        )

    def test_func(self):
        competition = self.get_competition()

        has_access = Review.objects.filter(
            id=self.kwargs.get("pk"), reader=self.request.user
        ).exists()

        if has_access and self.request.user.get_role(competition) in ["reader"]:
            return True
        return False


class ReviewMarkPublicView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, View
):
    def post(self, request, *args, **kwargs):
        competition = self.get_competition()
        review = get_object_or_404(
            Review, pk=kwargs["pk"], play__competition__slug=kwargs["competition_slug"]
        )

        mark_public(review)

        return redirect(
            "plays:detail", competition_slug=competition.slug, pk=review.play.id
        )

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.get_role(competition) in ["moderator", "admin"]:
            return True
        return False


class ReviewMarkHiddenView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, View
):
    def post(self, request, *args, **kwargs):
        competition = self.get_competition()
        review = get_object_or_404(
            Review, pk=kwargs["pk"], play__competition__slug=kwargs["competition_slug"]
        )

        mark_hidden(review)

        return redirect(
            "plays:detail", competition_slug=competition.slug, pk=review.play.id
        )

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.get_role(competition) in ["moderator", "admin"]:
            return True
        return False


class ReviewMarkObsoleteView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, View
):
    def post(self, request, *args, **kwargs):
        competition = self.get_competition()
        review = get_object_or_404(
            Review, pk=kwargs["pk"], play__competition__slug=kwargs["competition_slug"]
        )

        mark_obsolete(review)

        return redirect(
            "plays:detail", competition_slug=competition.slug, pk=review.play.id
        )

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.get_role(competition) in ["moderator", "admin"]:
            return True
        return False


class ReviewRestoreView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, View
):
    def post(self, request, *args, **kwargs):
        competition = self.get_competition()
        review = get_object_or_404(
            Review, pk=kwargs["pk"], play__competition__slug=kwargs["competition_slug"]
        )

        restore(review)

        return redirect(
            "plays:detail", competition_slug=competition.slug, pk=review.play.id
        )

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.get_role(competition) in ["moderator", "admin"]:
            return True
        return False


class ReviewUpdateView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, UpdateView
):
    model = Review
    fields = ["verdict", "comment"]

    def get_success_url(self):
        return redirect(
            "plays:detail",
            competition_slug=self.get_competition().slug,
            pk=self.object.play.id,
        ).url

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.get_role(competition) in ["admin"]:
            return True
        return False
