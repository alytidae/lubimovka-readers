from django.db import models
from apps.competitions.models import Competition
from django.urls import reverse

class Play(models.Model):
    competition = models.ForeignKey(
        Competition, 
        on_delete=models.CASCADE, 
        related_name='plays'
    )

    title = models.CharField(max_length=255)
    url = models.URLField(max_length=500)
    author_email = models.EmailField(unique=True, null=False, blank=False)
    author_first_name = models.CharField(max_length=255)
    author_last_name = models.CharField(max_length=255, null=True, blank=True)
    author_date_of_birth = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=False)
 
    def get_absolute_url(self):
        return reverse("plays:detail", kwargs={"competition_slug": self.competition.slug, "pk": self.pk})
