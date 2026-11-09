from django.contrib import admin

from .models import (
    Criterion, Defense, Evaluation, GroupRating, IndividualRating, PanelAssignment,
    Panelist, Proponent, ScoringSettings,
)


@admin.register(ScoringSettings)
class ScoringSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "passed_cutoff", "minor_cutoff", "major_cutoff")

    def has_add_permission(self, request):
        return not ScoringSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Criterion)
class CriterionAdmin(admin.ModelAdmin):
    list_display = ("number", "section", "name", "weight", "per_proponent", "is_active")
    list_editable = ("is_active",)
    list_filter = ("section", "per_proponent", "is_active")
    ordering = ("number",)


@admin.register(Panelist)
class PanelistAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "prefix", "suffix")
    search_fields = ("user__username", "user__first_name", "user__last_name")


class ProponentInline(admin.TabularInline):
    model = Proponent
    extra = 0


class PanelAssignmentInline(admin.TabularInline):
    model = PanelAssignment
    extra = 0
    max_num = 3


@admin.register(Defense)
class DefenseAdmin(admin.ModelAdmin):
    list_display = ("title", "schedule_date", "schedule_time", "venue", "status")
    list_filter = ("status", "schedule_date")
    search_fields = ("title", "proponents__full_name")
    inlines = [ProponentInline, PanelAssignmentInline]


@admin.register(Proponent)
class ProponentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "defense", "order")
    search_fields = ("full_name",)


@admin.register(PanelAssignment)
class PanelAssignmentAdmin(admin.ModelAdmin):
    list_display = ("defense", "role", "panelist")
    list_filter = ("role",)


class GroupRatingInline(admin.TabularInline):
    model = GroupRating
    extra = 0


class IndividualRatingInline(admin.TabularInline):
    model = IndividualRating
    extra = 0


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ("assignment", "submitted", "submitted_at", "updated_at")
    list_filter = ("submitted",)
    inlines = [GroupRatingInline, IndividualRatingInline]


@admin.register(GroupRating)
class GroupRatingAdmin(admin.ModelAdmin):
    list_display = ("evaluation", "criterion", "rating")


@admin.register(IndividualRating)
class IndividualRatingAdmin(admin.ModelAdmin):
    list_display = ("evaluation", "criterion", "proponent", "rating")
