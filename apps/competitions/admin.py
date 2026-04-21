from django.contrib import admin
from .models import Competition, CompetitionRole


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "status")
    search_fields = ("title",)
    ordering = ("-date",)


@admin.register(CompetitionRole)
class CompetitionRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "competition", "role")
    list_filter = ("competition", "role")
    search_fields = ("user__email", "competition__title")
