from django.views.generic import ListView, DetailView, UpdateView
from django.views import View
from .models import Play
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.utils.translation import gettext_lazy as _
from apps.competitions.mixins import CompetitionContextMixin
from apps.competitions.models import CompetitionRole, Competition
from django.db.models import Prefetch, Q
from apps.reviews.models import Review
from django.contrib import messages


class PlayDetailView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, DetailView
):
    model = Play
    template_name = "play_detail.html"

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.competition_roles.filter(
            competition=competition, is_active=True
        ).exists():
            return True

        return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        play = self.object
        competition = self.get_competition()
        user = self.request.user

        base_reviews_qs = Review.objects.filter(
            play=play, status=Review.Status.SUBMITTED
        ).select_related("reader")

        is_admin_or_mod = user.is_superuser or user.get_role(competition) in [
            "admin",
            "moderator",
        ]

        if is_admin_or_mod:
            context["own_reviews"] = Review.objects.filter(play=play).select_related(
                "reader"
            )
            context["other_reviews"] = Review.objects.none()
        else:
            context["own_reviews"] = base_reviews_qs.filter(
                reader=user, is_obsolete=False
            )

            has_visible_phases = (
                competition.are_phase1_reviews_visible
                or competition.are_phase2_reviews_visible
            )

            if has_visible_phases:
                other_filters = Q()
                if competition.are_phase1_reviews_visible:
                    other_filters |= Q(phase=Review.Phase.PHASE_1, is_hidden=False)
                if competition.are_phase2_reviews_visible:
                    other_filters |= Q(phase=Review.Phase.PHASE_2, is_hidden=False)
                context["other_reviews"] = (
                    base_reviews_qs.filter(other_filters, is_obsolete=False)
                    .exclude(reader=user)
                    .distinct()
                )
            else:
                context["other_reviews"] = Review.objects.none()

        current_review_phase = {
            Competition.Status.PHASE_1: Review.Phase.PHASE_1,
            Competition.Status.PHASE_2: Review.Phase.PHASE_2,
        }.get(competition.status)

        context["my_active_review"] = None
        if current_review_phase is not None:
            context["my_active_review"] = Review.objects.filter(
                play=play,
                reader=user,
                phase=current_review_phase,
                status__in=[Review.Status.ASSIGNED, Review.Status.DRAFT],
                is_obsolete=False,
            ).first()

        return context

    def get_queryset(self):
        competition = self.get_competition()
        user = self.request.user

        qs = super().get_queryset().filter(competition=competition)

        if user.is_superuser or user.get_role(competition) in ["admin", "moderator"]:
            return qs

        return qs.filter(reviews__reader=user, reviews__is_obsolete=False).distinct()


class PlayListView(
    LoginRequiredMixin, UserPassesTestMixin, CompetitionContextMixin, ListView
):
    model = Play
    template_name = "play_list.html"
    ordering = ["is_active", "author_email"]

    def test_func(self):
        competition = self.get_competition()

        if self.request.user.is_superuser:
            return True

        if self.request.user.competition_roles.filter(
            competition=competition, is_active=True
        ).exists():
            return True

        return False

    def get_context_data(self, **kwargs):
        competition = self.get_competition()
        user = self.request.user
        context = super().get_context_data(**kwargs)

        if user.get_role(competition) == "reader":
            count = Review.objects.filter(
                reader=user, verdict=True, play__competition=competition
            ).count()
            context["number_positive_votes"] = count

        return context

    def get_queryset(self):
        competition = self.get_competition()
        user = self.request.user

        qs = super().get_queryset().filter(competition=competition).distinct()

        if user.is_superuser or user.get_role(competition) in ["admin", "moderator"]:
            return qs.prefetch_related("reviews")

        current_phase = {
            Competition.Status.PHASE_1: Review.Phase.PHASE_1,
            Competition.Status.PHASE_2: Review.Phase.PHASE_2,
        }.get(competition.status)

        if current_phase is None:
            return qs.none()

        current_reviews = Review.objects.filter(
            reader=user,
            phase=current_phase,
            is_obsolete=False,
        )

        return (
            qs.filter(reviews__in=current_reviews)
            .prefetch_related(
                Prefetch(
                    "reviews",
                    queryset=current_reviews,
                    to_attr="current_user_reviews",
                )
            )
            .distinct()
        )


class PlayActivateView(LoginRequiredMixin, UserPassesTestMixin, View):
    def post(self, request, *args, **kwargs):
        play = get_object_or_404(
            Play, pk=kwargs["pk"], competition__slug=kwargs["competition_slug"]
        )

        if not play.is_active:
            play.is_active = True
            play.save(update_fields=["is_active"])
            messages.success(
                request,
                _("✅ %(title)s was activated successfully") % {"title": play.title},
            )
        else:
            messages.info(
                request, _("%(title)s is already active") % {"title": play.title}
            )

        return redirect(play.get_absolute_url())

    def test_func(self):
        competition = get_object_or_404(
            Competition, slug=self.kwargs["competition_slug"]
        )
        if self.request.user.is_superuser:
            return True

        if self.request.user.get_role(competition) in ["admin", "moderator"]:
            return True

        return False


class PlayDeactivateView(LoginRequiredMixin, UserPassesTestMixin, View):
    def post(self, request, *args, **kwargs):
        play = get_object_or_404(
            Play, pk=kwargs["pk"], competition__slug=kwargs["competition_slug"]
        )

        if play.is_active:
            play.is_active = False
            play.save(update_fields=["is_active"])
            messages.success(
                request,
                _("✅ %(title)s was deactivated successfully") % {"title": play.title},
            )
        else:
            messages.info(
                request, _("%(title)s is already not active") % {"title": play.title}
            )

        return redirect(play.get_absolute_url())

    def test_func(self):
        competition = get_object_or_404(
            Competition, slug=self.kwargs["competition_slug"]
        )
        if self.request.user.is_superuser:
            return True

        if self.request.user.get_role(competition) in ["admin", "moderator"]:
            return True

        return False


class PlayExcludePhase2View(LoginRequiredMixin, UserPassesTestMixin, View):
    def post(self, request, *args, **kwargs):
        play = get_object_or_404(
            Play, pk=kwargs["pk"], competition__slug=kwargs["competition_slug"]
        )
        if play.competition.status != Competition.Status.PHASE_1:
            messages.error(request, _("Plays can only be excluded during Phase 1."))
            return redirect(play.get_absolute_url())

        comment = request.POST.get("comment", "").strip()
        if not comment:
            messages.error(request, _("An exclusion reason is required."))
            return redirect(play.get_absolute_url())

        if play.exclude_phase_2:
            messages.info(
                request, _("This play has already been excluded from Phase 2.")
            )
            return redirect(play.get_absolute_url())

        play.exclude_phase_2 = True
        play.phase_2_exclusion_comment = comment
        play.save(update_fields=["exclude_phase_2", "phase_2_exclusion_comment"])
        messages.success(request, _("The play has been excluded from Phase 2."))
        return redirect(play.get_absolute_url())

    def test_func(self):
        competition = get_object_or_404(
            Competition, slug=self.kwargs["competition_slug"]
        )
        return (
            self.request.user.is_superuser
            or self.request.user.get_role(competition) == "admin"
        )


class PlayUnexcludePhase2View(PlayExcludePhase2View):
    def post(self, request, *args, **kwargs):
        play = get_object_or_404(
            Play, pk=kwargs["pk"], competition__slug=kwargs["competition_slug"]
        )
        if play.competition.status != Competition.Status.PHASE_1:
            messages.error(
                request, _("Exclusion can only be cancelled during Phase 1.")
            )
            return redirect(play.get_absolute_url())

        play.exclude_phase_2 = False
        play.phase_2_exclusion_comment = ""
        play.save(update_fields=["exclude_phase_2", "phase_2_exclusion_comment"])
        messages.success(request, _("Phase 2 exclusion has been cancelled."))
        return redirect(play.get_absolute_url())


class PlayForcePhase2View(LoginRequiredMixin, UserPassesTestMixin, View):
    def post(self, request, *args, **kwargs):
        play = get_object_or_404(
            Play, pk=kwargs["pk"], competition__slug=kwargs["competition_slug"]
        )
        competition = play.competition

        if competition.status != Competition.Status.PHASE_1:
            messages.error(
                request,
                _(
                    "Force Phase 2 can only be toggled during Phase 1 of the competition."
                ),
            )
            return redirect(play.get_absolute_url())

        play.force_phase_2 = True
        play.save(update_fields=["force_phase_2"])
        messages.success(
            request,
            _(
                "✅ %(title)s has been flagged to advance to Phase 2 regardless of reviews."
            )
            % {"title": play.title},
        )
        return redirect(play.get_absolute_url())

    def test_func(self):
        competition = get_object_or_404(
            Competition, slug=self.kwargs["competition_slug"]
        )
        if self.request.user.is_superuser:
            return True
        return self.request.user.get_role(competition) == "admin"


class PlayUnforcePhase2View(LoginRequiredMixin, UserPassesTestMixin, View):
    def post(self, request, *args, **kwargs):
        play = get_object_or_404(
            Play, pk=kwargs["pk"], competition__slug=kwargs["competition_slug"]
        )
        competition = play.competition

        if competition.status != Competition.Status.PHASE_1:
            messages.error(
                request,
                _(
                    "Force Phase 2 can only be toggled during Phase 1 of the competition."
                ),
            )
            return redirect(play.get_absolute_url())

        play.force_phase_2 = False
        play.save(update_fields=["force_phase_2"])
        messages.success(
            request,
            _("✅ %(title)s Phase 2 force flag has been removed.")
            % {"title": play.title},
        )
        return redirect(play.get_absolute_url())

    def test_func(self):
        competition = get_object_or_404(
            Competition, slug=self.kwargs["competition_slug"]
        )
        if self.request.user.is_superuser:
            return True
        return self.request.user.get_role(competition) == "admin"


class PlayUpdateCommentView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Play
    fields = ["internal_comment"]
    template_name = "play_details.html"

    def get_success_url(self):
        return self.object.get_absolute_url()

    def test_func(self):
        competition = get_object_or_404(
            Competition, slug=self.kwargs["competition_slug"]
        )
        if self.request.user.is_superuser:
            return True

        if self.request.user.get_role(competition) in ["admin", "moderator"]:
            return True

        return False
