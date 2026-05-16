from datetime import timedelta

from django.db import models
from django.utils import timezone
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
        REJECTED = "rejected", _("Rejected")
        SUBMITTED = "submitted", _("Submitted")

    reader = models.ForeignKey(User, on_delete=models.CASCADE)
    play = models.ForeignKey(Play, on_delete=models.CASCADE, related_name="reviews")

    phase = models.CharField(max_length=20, choices=Phase.choices)
    status = models.CharField(max_length=20, choices=Status.choices)

    verdict = models.BooleanField(null=True, blank=True)
    comment = models.TextField(blank=True)

    is_hidden = models.BooleanField(default=True)
    is_obsolete = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("play", "reader", "phase")

    DEADLINE_DAYS = 14

    @property
    def remaining_time(self):
        from django.utils.translation import ngettext, gettext as _

        diff = self.created_at + timedelta(days=self.DEADLINE_DAYS) - timezone.now()
        total_seconds = int(diff.total_seconds())
        if total_seconds <= 0:
            return _("Overdue")
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        days_str = ngettext("%(count)d day", "%(count)d days", days) % {"count": days}
        hours_str = ngettext("%(count)d hour", "%(count)d hours", hours) % {
            "count": hours
        }
        return f"{days_str} {hours_str}"

    def __str__(self):
        return f"{self.play.title} - {self.reader.username} ({self.phase})"
