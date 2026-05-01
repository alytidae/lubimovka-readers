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
            message="You’ve reached your limit of active plays to review. Please finish one of your current plays first."
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
        message="A new play has been assigned to you.",
        play=selected_play
    )


def mark_public(review):
    pass

def mark_hidden(review):
    pass

def mark_obsolete(review):
    pass

def restore(review):
    pass

def save_draft(review, verdict, comment):
    pass

def submit(review, verdict, comment):
    pass
