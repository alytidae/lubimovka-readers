import random
from apps.plays.models import Play
from apps.competitions.models import Competition, CompetitionRole
from dataclasses import dataclass
from typing import Optional
from .models import Review
from django.db import transaction
from django.utils import timezone
from django.db.models import (
    Count,
    Q,
    Exists,
    OuterRef,
)
from django.utils.translation import gettext_lazy as _
from apps.users.models import User

MAX_ACTIVE_REVIEWS_PER_READER = 5
MAX_REVIEWS_PER_PLAY = 3
VERDICTS_REQUIRED_FOR_FINAL_DECISION = 2

_PHASE_MAP = {
    Competition.Status.PHASE_1: Review.Phase.PHASE_1,
    Competition.Status.PHASE_2: Review.Phase.PHASE_2,
}


def _validate_review_phase(review):
    competition = review.play.competition
    allowed_phase = _PHASE_MAP.get(competition.status)
    if allowed_phase is None or review.phase != allowed_phase:
        return Result(
            success=False,
            message=_(
                "You cannot modify this review during the current competition phase."
            ),
        )
    return None


@dataclass
class Result:
    success: bool
    message: str


@dataclass
class AssignmentResult:
    success: bool
    message: str
    play: Optional[Play] = None


@transaction.atomic
def assign_play(reader, competition):
    active_count = (
        Review.objects.filter(
            reader=reader,
            play__competition=competition,
            is_obsolete=False,
        )
        .exclude(status=Review.Status.SUBMITTED)
        .count()
    )

    if active_count >= MAX_ACTIVE_REVIEWS_PER_READER:
        return AssignmentResult(
            success=False,
            message=_(
                "✅ You've reached your limit of active plays to review. Please finish one of your current plays first."
            ),
        )

    if competition.status == Competition.Status.PHASE_1:
        current_phase = Review.Phase.PHASE_1
    else:
        return AssignmentResult(
            success=False,
            message=_(
                "You cannot request a new play during the current phase of the competition."
            ),
        )

    available_play_ids = list(
        Play.objects.filter(
            competition=competition,
            is_active=True,
        )
        .annotate(
            active_reviews_count=Count(
                "reviews",
                filter=Q(reviews__is_obsolete=False, reviews__phase=current_phase),
            ),
            approval_verdicts_count=Count(
                "reviews",
                filter=Q(
                    reviews__is_obsolete=False,
                    reviews__verdict=True,
                    reviews__phase=current_phase,
                ),
            ),
            rejected_verdicts_count=Count(
                "reviews",
                filter=Q(
                    reviews__is_obsolete=False,
                    reviews__verdict=False,
                    reviews__phase=current_phase,
                ),
            ),
            has_reviewed_by_current_reader=Exists(
                Review.objects.filter(
                    play=OuterRef("pk"), reader=reader, phase=current_phase
                )
            ),
        )
        .filter(
            active_reviews_count__lt=MAX_REVIEWS_PER_PLAY,
            has_reviewed_by_current_reader=False,
        )
        .exclude(
            Q(approval_verdicts_count__gte=VERDICTS_REQUIRED_FOR_FINAL_DECISION)
            | Q(rejected_verdicts_count__gte=VERDICTS_REQUIRED_FOR_FINAL_DECISION)
        )
        .values_list("id", flat=True)
    )

    random.shuffle(available_play_ids)

    if not available_play_ids:
        return AssignmentResult(
            success=False,
            message=_(
                "There are no new plays available to review at the moment. Please check back later."
            ),
        )

    selected_play = None
    for play_id in available_play_ids:
        play = (
            Play.objects.select_for_update(skip_locked=True).filter(id=play_id).first()
        )

        if play:
            current_active_reviews = play.reviews.filter(
                is_obsolete=False, phase=current_phase
            ).count()

            if current_active_reviews < MAX_REVIEWS_PER_PLAY:
                selected_play = play
                break
            else:
                continue

    if not selected_play:
        return AssignmentResult(
            success=False,
            message=_(
                "There are no new plays available to review at the moment. Please check back later."
            ),
        )

    Review.objects.create(
        reader=reader,
        play=selected_play,
        phase=current_phase,
        status=Review.Status.ASSIGNED,
    )

    return AssignmentResult(
        success=True,
        message=_("✅ A new play has been assigned to you."),
        play=selected_play,
    )


def mark_public(review):
    if not review.is_hidden:
        return Result(success=False, message=_("This review is already public."))

    review.is_hidden = False
    review.save(update_fields=["is_hidden"])

    return Result(success=True, message=_("✅ Review is now visible to others."))


def mark_hidden(review):
    if review.is_hidden:
        return Result(success=False, message=_("This review is already hidden."))

    review.is_hidden = True
    review.save(update_fields=["is_hidden"])

    return Result(success=True, message=_("✅ Review has been hidden by moderator."))


def mark_obsolete(review):
    if review.is_obsolete:
        return Result(
            success=False, message=_("This review is already marked as obsolete.")
        )

    review.is_obsolete = True
    review.save(update_fields=["is_obsolete"])

    return Result(
        success=True,
        message=_("✅ Review marked as obsolete. The play is back in the pool."),
    )


def restore(review):
    if not review.is_obsolete:
        return Result(success=False, message=_("This review is already active."))

    review.is_obsolete = False
    review.save(update_fields=["is_obsolete"])

    return Result(success=True, message=_("✅ Review has been successfully restored."))


def save_draft(review, verdict, comment):
    phase_error = _validate_review_phase(review)
    if phase_error:
        return phase_error

    review.verdict = verdict
    review.comment = comment
    review.status = Review.Status.DRAFT

    review.save(update_fields=["verdict", "comment", "status"])

    return Result(
        success=True, message=_("✅ Your draft review has been saved successfully")
    )


def submit(review, verdict, comment):
    phase_error = _validate_review_phase(review)
    if phase_error:
        return phase_error

    if review.status == Review.Status.SUBMITTED:
        return Result(
            success=False, message=_("This review has already been submitted.")
        )

    if not comment or str(comment).strip() == "" or verdict is None:
        return Result(
            success=False,
            message=_("Verdict and comment are mandatory for submission"),
        )

    review.verdict = verdict
    review.comment = comment
    review.status = Review.Status.SUBMITTED
    review.submitted_at = timezone.now()

    review.save(update_fields=["verdict", "comment", "status", "submitted_at"])

    return Result(
        success=True, message=_("✅ Your final review has been submitted successfully")
    )


@transaction.atomic
def auto_assign_phase2(competition):
    if competition.status != Competition.Status.PHASE_2:
        return 0

    qualifying_play_ids = list(
        Play.objects.filter(
            competition=competition,
            is_active=True,
        )
        .annotate(
            yes_count=Count(
                "reviews",
                filter=Q(
                    reviews__phase=Review.Phase.PHASE_1,
                    reviews__status=Review.Status.SUBMITTED,
                    reviews__verdict=True,
                    reviews__is_obsolete=False,
                ),
            ),
        )
        .filter(yes_count__gte=VERDICTS_REQUIRED_FOR_FINAL_DECISION)
        .values_list("id", flat=True)
    )

    if not qualifying_play_ids:
        return 0

    reader_ids = list(
        CompetitionRole.objects.filter(
            competition=competition,
            role="reader",
            is_active=True,
        ).values_list("user_id", flat=True)
    )

    if not reader_ids:
        return 0

    existing = set(
        Review.objects.filter(
            play_id__in=qualifying_play_ids,
            reader_id__in=reader_ids,
            phase=Review.Phase.PHASE_2,
        ).values_list("play_id", "reader_id")
    )

    reviews_to_create = []
    for play_id in qualifying_play_ids:
        for reader_id in reader_ids:
            if (play_id, reader_id) not in existing:
                reviews_to_create.append(
                    Review(
                        play_id=play_id,
                        reader_id=reader_id,
                        phase=Review.Phase.PHASE_2,
                        status=Review.Status.ASSIGNED,
                    )
                )

    Review.objects.bulk_create(reviews_to_create, ignore_conflicts=True)

    return len(reviews_to_create)


def reject(review):
    if review.status != Review.Status.ASSIGNED:
        return Result(
            success=False,
            message=_("Only assigned reviews can be rejected."),
        )

    phase_error = _validate_review_phase(review)
    if phase_error:
        return phase_error

    review.status = Review.Status.REJECTED
    review.is_obsolete = True

    review.save(update_fields=["is_obsolete", "status"])

    return Result(success=True, message=_("✅ Assignment successfully declined"))
