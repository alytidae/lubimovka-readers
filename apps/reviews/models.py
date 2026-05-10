from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.users.models import User
from apps.plays.models import Play


class Review(models.Model):
    class Phase(models.TextChoices):
        PHASE_1 = "phase_1", _("Phase 1")
        PHASE_2 = "phase_2", _("Phase 2")

    class Status(models.TextChoices):
        ASSIGNED = "assigned", _("Assigned")
        DRAFT = "draft", _("Draft")
        SUBMITTED = "submitted", _("Submitted")

    reader = models.ForeignKey(User, on_delete=models.CASCADE)
    play = models.ForeignKey(Play, on_delete=models.CASCADE, related_name="reviews")

    phase = models.CharField(max_length=20, choices=Phase.choices)
    status = models.CharField(max_length=20, choices=Status.choices)

    verdict = models.BooleanField(null=True, blank=True)
    comment = models.TextField(blank=True)

    is_hidden = models.BooleanField(default=False)
    is_obsolete = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("play", "reader", "phase")

    def __str__(self):
        return f"{self.play.title} - {self.reader.username} ({self.phase})"
