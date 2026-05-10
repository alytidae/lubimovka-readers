from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from pytils.translit import slugify
from django.urls import reverse
from cryptography.fernet import Fernet


class Competition(models.Model):
    class Status(models.TextChoices):
        SETUP = "setup", _("Setup and Team Formation")
        PHASE_1 = "phase_1", _("Phase 1: Distribution (3 readers)")
        PHASE_2 = "phase_2", _("Phase 2: Open Reading")
        FINISHED = "finished", _("Finished")

    title = models.CharField(_("Title"), max_length=255)
    date = models.DateField(_("Date"))

    slug = models.SlugField(max_length=255, unique=True, blank=True)

    google_sheet_url = models.URLField(
        _("Google Sheet URL"), max_length=500, blank=True
    )

    play_title_sheet_column_name = models.CharField(
        _("Play title column"), max_length=100
    )
    play_url_sheet_column_name = models.CharField(_("Play URL column"), max_length=100)
    play_author_email_sheet_column_name = models.CharField(
        _("Author email column"), max_length=100
    )
    play_author_first_name_sheet_column_name = models.CharField(
        _("Author first name column"), max_length=100
    )
    play_author_last_name_sheet_column_name = models.CharField(
        _("Author last name column"), max_length=100, null=True, blank=True
    )
    play_author_year_of_birth_sheet_column_name = models.CharField(
        _("Author year of birth column"), max_length=100, null=True, blank=True
    )

    status = models.CharField(
        _("Status"), max_length=20, choices=Status.choices, default=Status.SETUP
    )

    are_phase1_reviews_visible = models.BooleanField(
        _("Phase 1 reviews visible"), default=False
    )
    are_phase2_reviews_visible = models.BooleanField(
        _("Phase 2 reviews visible"), default=False
    )

    google_credentials = models.TextField()

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.title}-{self.date.year}")

        if not self.pk and self.google_credentials:
            f = Fernet(settings.FERNET_KEY.encode('utf-8'))
            encrypted_google_credentials = f.encrypt(self.google_credentials.encode('utf-8'))
            self.google_credentials = encrypted_google_credentials.decode('utf-8')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.date.year})"

    def get_absolute_url(self):
        return reverse("competitions:detail", kwargs={"slug": self.slug})


class CompetitionRole(models.Model):
    ROLE_CHOICES = (
        ("reader", _("Reader")),
        ("moderator", _("Moderator")),
        ("admin", _("Admin")),
    )

    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name="roles"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="competition_roles",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("competition", "user")

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()} in {self.competition.title}"
