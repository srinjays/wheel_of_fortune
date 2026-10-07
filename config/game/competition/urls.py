from django.urls import path

from . import views

urlpatterns = [
    path("competition", views.competition_state, name="competition-state"),
    path("admin/competition/setup", views.competition_setup, name="competition-setup"),
    path("team/competition/spin", views.team_spin, name="team-spin"),
    path(
        "admin/competition/settings",
        views.update_competition_settings,
        name="competition-settings",
    ),
    path("admin/wheel-items", views.wheel_items, name="wheel-items"),
    path("admin/wheel-items/add", views.add_wheel_item, name="add-wheel-item"),
    path(
        "admin/wheel-items/<slug:item_key>",
        views.remove_wheel_item,
        name="remove-wheel-item",
    ),
    path("admin/competition/spin/start", views.start_spin, name="start-spin"),
    path("admin/competition/spin/expire", views.expire_spin, name="expire-spin"),
    path("admin/competition/pause", views.pause_competition, name="pause-competition"),
    path("admin/competition/resume", views.resume_competition, name="resume-competition"),
    path("admin/competition/finish", views.finish_competition, name="finish-competition"),
]
