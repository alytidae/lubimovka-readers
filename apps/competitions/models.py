from django.db import models
from django.conf import settings
from django.utils.text import slugify

class Competition(models.Model):
    class Status(models.TextChoices):
        SETUP = 'setup', 'Setup and Team Formation'
        PHASE_1 = 'phase_1', 'Phase 1: Distribution (3 readers)'
        PHASE_2 = 'phase_2', 'Phase 2: Open Reading'
        FINISHED = 'finished', 'Finished'

    title = models.CharField(max_length=255)
    date = models.DateField()
    
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    google_sheet_url = models.URLField(max_length=500, blank=True)
    play_title_sheet_column_name = models.CharField(max_length=50, blank=True)
    play_link_sheet_column_name = models.CharField(max_length=50, blank=True)

    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.SETUP
    )

    are_phase1_reviews_visible = models.BooleanField(default=False)
    are_phase2_reviews_visible = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.title}-{self.date.year}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.date.year})"


class CompetitionRole(models.Model):
    ROLE_CHOICES = (
        ('reader', 'Reader'),
        ('moderator', 'Moderator'),
        ('admin', 'Admin'),
    )
    
    competition = models.ForeignKey(
        Competition, 
        on_delete=models.CASCADE, 
        related_name='roles'
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='competition_roles'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    class Meta:
        unique_together = ('competition', 'user')

    def __str__(self):
        return f"{self.user.email} - {self.get_role_display()} in {self.competition.title}"
