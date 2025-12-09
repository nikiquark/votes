from django.urls import path

from .views import (
    CreatePollView,
    HistoryView,
    HistoryDetailView,
    LandingView,
    MyProfileView,
    OrganizationLoginView,
    PasswordChangeView,
    SelectOrganizationView,
    StartPollView,
    EndPollView,
    VoteView,
    logout_view,
)

app_name = "core"

urlpatterns = [
    path("", LandingView.as_view(), name="landing"),
    path("login/", OrganizationLoginView.as_view(), name="login"),
    path("my/", MyProfileView.as_view(), name="my"),
    path("create/", CreatePollView.as_view(), name="create"),
    path("history/", HistoryView.as_view(), name="history"),
    path("history/<int:pk>/", HistoryDetailView.as_view(), name="history_detail"),
    path("history/<int:pk>/start/", StartPollView.as_view(), name="start_poll"),
    path("history/<int:pk>/end/", EndPollView.as_view(), name="end_poll"),
    path("select-organization/", SelectOrganizationView.as_view(), name="select_organization"),
    path("password-change/", PasswordChangeView.as_view(), name="password_change"),
    path("logout/", logout_view, name="logout"),
    path("<uuid:poll_url>/<uuid:user_url>/", VoteView.as_view(), name="vote"),
]

