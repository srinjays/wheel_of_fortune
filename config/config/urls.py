"""URL configuration for four_spin project."""
from django.urls import include, path

urlpatterns = [
    path("api/", include("game.core.urls")),
    path("api/", include("game.accounts.urls")),
    path("api/", include("game.competition.urls")),
    path("api/", include("game.assignments.urls")),
    path("api/", include("game.verifications.urls")),
    path("api/", include("game.leaderboard.urls")),
]
