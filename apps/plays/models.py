from django.db import models
from datetime import date
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
    author_email = models.EmailField(null=False, blank=False)
    author_first_name = models.CharField(max_length=255)
    author_last_name = models.CharField(max_length=255, null=True, blank=True)
    author_year_of_birth = models.PositiveSmallIntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=False)

    @property
    def is_author_over_35(self):
        if not self.author_year_of_birth:
            return False
            
        current_year = date.today().year
        age = current_year - self.author_year_of_birth         
        return age > 35
 
    def get_absolute_url(self):
        return reverse("plays:detail", kwargs={"competition_slug": self.competition.slug, "pk": self.pk})

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['competition', 'author_email', 'title'],
                name='unique_play_per_author_per_competition'
            )
        ]
