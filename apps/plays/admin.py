from django.contrib import admin
from .models import Play


@admin.register(Play)
class PlayAdmin(admin.ModelAdmin):
    list_display = ("title", "competition", "is_active", "force_phase_2")
    search_fields = ("title",)
