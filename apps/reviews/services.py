import random
from apps.plays.models import Play
from apps.competitions.models import Competition
from dataclasses import dataclass
from typing import Optional
from .models import Review
from django.db import transaction
from django.db.models import Count, Q, Exists, OuterRef

MAX_ACTIVE_REVIEWS_PER_READER = 3
MAX_REVIEWS_PER_PLAY = 3
VERDICTS_REQUIRED_FOR_FINAL_DECISION = 2


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
    active_count = Review.objects.filter(
        reader=reader,
        play__competition=competition,
        is_obsolete=False,
    ).exclude(
        status=Review.Status.SUBMITTED
    ).count()

    if active_count >= MAX_ACTIVE_REVIEWS_PER_READER:
        return AssignmentResult(
            success=False,
            message="\u2705 You’ve reached your limit of active plays to review. Please finish one of your current plays first."
        )
    
    if competition.status == Competition.Status.PHASE_1:
        current_phase = Review.Phase.PHASE_1
    else:
        return AssignmentResult(
            success=False,
            message="You cannot request a new play during the current phase of the competition."
        )

    available_play_ids = list(Play.objects.filter(
        competition=competition,
        is_active=True,
    ).annotate(
        active_reviews_count=Count(
            "reviews",
            filter=Q(
                reviews__is_obsolete=False,
                reviews__phase=current_phase
            )
        ),
        approval_verdicts_count=Count(
            "reviews",
            filter=Q(
                reviews__is_obsolete=False,
                reviews__verdict=True,
                reviews__phase=current_phase
            )
        ),
        rejected_verdicts_count=Count(
            "reviews",
            filter=Q(
                reviews__is_obsolete=False,
                reviews__verdict=False,
                reviews__phase=current_phase
            )
        ),
        has_reviewed_by_current_reader=Exists(
            Review.objects.filter(
                play=OuterRef("pk"),
                reader=reader,
                phase=current_phase
            )
        )    
    ).filter(
        active_reviews_count__lt=MAX_REVIEWS_PER_PLAY,
        has_reviewed_by_current_reader = False
    ).exclude(
        Q(approval_verdicts_count=VERDICTS_REQUIRED_FOR_FINAL_DECISION) |
        Q(rejected_verdicts_count=VERDICTS_REQUIRED_FOR_FINAL_DECISION)
    ).values_list("id", flat=True))

    random.shuffle(available_play_ids)

    if not available_play_ids:
        return AssignmentResult(
            success=False,
            message="There are no new plays available to review at the moment. Please check back later."
        )

    selected_play = None
    for play_id in available_play_ids:
        selected_play = Play.objects.select_for_update(skip_locked=True).filter(id=play_id).first()
        
        if selected_play:
            break  

    if not selected_play:
        return AssignmentResult(
            success=False,
            message="There are no new plays available to review at the moment. Please check back later."
        )

    Review.objects.create(
        reader=reader,
        play=selected_play,
        phase=current_phase,
        status=Review.Status.ASSIGNED,
    )

    return AssignmentResult(
        success=True,
        message="\u2705 A new play has been assigned to you.",
        play=selected_play
    )

def mark_public(review):
    if not review.is_hidden_by_moderator:
        return Result(success=False, message="This review is already public.")
    
    review.is_hidden_by_moderator = False
    review.save(update_fields=['is_hidden_by_moderator'])
    
    return Result(success=True, message="\u2705 Review is now visible to others.")

def mark_hidden(review):
    if review.is_hidden_by_moderator:
        return Result(success=False, message="This review is already hidden.")
    
    review.is_hidden_by_moderator = True
    review.save(update_fields=['is_hidden_by_moderator'])
    
    return Result(success=True, message="\u2705 Review has been hidden by moderator.")

def mark_obsolete(review):
    if review.is_obsolete:
        return Result(success=False, message="This review is already marked as obsolete.")
    
    review.is_obsolete = True
    review.save(update_fields=['is_obsolete'])
    
    return Result(success=True, message="\u2705 Review marked as obsolete. The play is back in the pool.")

def restore(review):
    if not review.is_obsolete:
        return Result(success=False, message="This review is already active.")
    
    review.is_obsolete = False
    review.save(update_fields=['is_obsolete'])
    
    return Result(success=True, message="\u2705 Review has been successfully restored.")

def save_draft(review, verdict, comment):
    review.verdict = verdict
    review.comment = comment
    review.status = Review.Status.DRAFT

    review.save(update_fields=['verdict', 'comment', 'status'])

    return Result(success=True, message="\u2705 Your draft review has been saved successfully")

def submit(review, verdict, comment):
    if review.status == Review.Status.SUBMITTED:
        return Result(success=False, message="This review has already been submitted.")

    if not comment or str(comment).strip() == "" or verdict is None:
        return Result(success=False, message="Verdict and comment are mandatory for submission")
    
    review.verdict = verdict
    review.comment = comment
    review.status = Review.Status.SUBMITTED

    review.save(update_fields=['verdict', 'comment', 'status'])

    return Result(success=True, message="\u2705 Your final review has been submitted successfully")
