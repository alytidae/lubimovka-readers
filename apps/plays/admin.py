from django.contrib import admin
from .models import Play


@admin.register(Play)
class PlayAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "competition",
        "is_active",
        "force_phase_2",
        "exclude_phase_2",
    )
    readonly_fields = ("exclude_phase_2", "phase_2_exclusion_comment")
    search_fields = ("title",)
