from django.contrib import admin
from django.db.models import Count

from .models import (
    Choice,
    Organization,
    OrganizationUser,
    Poll,
    PollUser,
    Question,
    UserChoice,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "paid_until", "timezone", "is_active", "created_at")
    search_fields = ("name",)
    list_filter = ("timezone",)
    readonly_fields = ("created_at", "updated_at", "updated_by")
    ordering = ("name",)


@admin.register(OrganizationUser)
class OrganizationUserAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "is_admin", "email", "name", "created_at")
    list_filter = ("is_admin", "organization")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "organization__name",
    )
    readonly_fields = ("created_at", "updated_at", "updated_by")
    list_select_related = ("user", "organization")
    ordering = ("organization__name", "user__username")


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ("title", "creator", "organization", "time_start", "time_end", "created_at")
    list_filter = ("time_start", "time_end")
    search_fields = ("title", "creator__user__username", "creator__user__email")
    readonly_fields = ("created_at", "updated_at", "updated_by")
    list_select_related = ("creator", "creator__organization")
    ordering = ("-created_at",)

    def organization(self, obj):
        return obj.creator.organization

    organization.admin_order_field = "creator__organization__name"
    organization.short_description = "Организация"


@admin.register(PollUser)
class PollUserAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "poll", "is_voted", "url")
    list_filter = ("is_voted", "poll")
    search_fields = ("email", "name", "poll__title")
    list_select_related = ("poll",)
    ordering = ("poll__title", "email")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "poll", "type", "min", "max")
    list_filter = ("poll", "type")
    search_fields = ("text", "poll__title")
    list_select_related = ("poll",)
    ordering = ("poll__title", "text")


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ("choice", "question", "poll", "vote_count")
    list_filter = ("question__poll",)
    search_fields = ("choice", "question__text", "question__poll__title")
    list_select_related = ("question", "question__poll")
    ordering = ("question__poll__title", "question__text", "choice")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(vote_count_value=Count("user_choices"))

    def poll(self, obj):
        return obj.question.poll

    poll.admin_order_field = "question__poll__title"
    poll.short_description = "Опрос"

    def vote_count(self, obj):
        return obj.vote_count_value

    vote_count.short_description = "Голосов"
    vote_count.admin_order_field = "vote_count_value"


@admin.register(UserChoice)
class UserChoiceAdmin(admin.ModelAdmin):
    list_display = ("user_email", "choice", "question", "poll")
    list_filter = ("choice__question__poll",)
    search_fields = (
        "user__email",
        "user__name",
        "choice__choice",
        "choice__question__text",
        "choice__question__poll__title",
    )
    list_select_related = ("user", "choice", "choice__question", "choice__question__poll")
    ordering = ("choice__question__poll__title", "choice__question__text", "choice__choice", "user__email")

    def poll(self, obj):
        return obj.choice.question.poll

    poll.admin_order_field = "choice__question__poll__title"
    poll.short_description = "Опрос"

    def question(self, obj):
        return obj.choice.question

    question.admin_order_field = "choice__question__text"
    question.short_description = "Вопрос"

    def user_email(self, obj):
        return obj.user.email

    user_email.admin_order_field = "user__email"
    user_email.short_description = "Email"
