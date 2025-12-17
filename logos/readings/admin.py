from django.contrib import admin
from django.utils import timezone

from .models import DailyReading, GospelMeditation, LiturgicalDay


class DailyReadingInline(admin.TabularInline):
    model = DailyReading
    extra = 1
    fields = (
        "language_code",
        "reading_type",
        "order",
        "reference",
        "psalm_response",
        "title",
        "text",
    )
    show_change_link = True


@admin.register(LiturgicalDay)
class LiturgicalDayAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "liturgical_year",
        "season",
        "rank",
        "is_holy_day_of_obligation",
    )
    list_filter = (
        "liturgical_year",
        "season",
        "rank",
        "is_holy_day_of_obligation",
    )
    search_fields = (
        "date",
        "season",
        "rank",
    )
    date_hierarchy = "date"
    inlines = [DailyReadingInline]


@admin.register(DailyReading)
class DailyReadingAdmin(admin.ModelAdmin):
    list_display = (
        "day",
        "language_code",
        "reading_type",
        "order",
        "reference",
    )
    list_filter = (
        "language_code",
        "reading_type",
        "day__season",
        "day__liturgical_year",
    )
    search_fields = (
        "reference",
        "title",
        "text",
    )
    autocomplete_fields = ("day",)


@admin.register(GospelMeditation)
class GospelMeditationAdmin(admin.ModelAdmin):
    list_display = (
        "day",
        "language_code",
        "status",
        "source",
        "approved_by",
        "approved_at",
        "created_at",
    )
    list_filter = (
        "status",
        "source",
        "language_code",
        "day__season",
        "day__liturgical_year",
    )
    search_fields = (
        "title",
        "body",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "approved_by",
        "approved_at",
    )
    autocomplete_fields = ("day", "created_by", "approved_by")

    def save_model(self, request, obj, form, change):
        # Automatically stamp approval metadata when moving to APPROVED.
        if obj.status == GospelMeditation.Status.APPROVED:
            if obj.approved_by is None:
                obj.approved_by = request.user
            if obj.approved_at is None:
                obj.approved_at = timezone.now()
        super().save_model(request, obj, form, change)
