from django.urls import path

from . import views

urlpatterns = [
    path("team/buzzer", views.buzzer, name="team-buzzer"),
    path("admin/verifications", views.verification_queue, name="verification-queue"),
    path(
        "admin/verifications/<str:verification_id>/approve",
        views.approve_verification,
        name="approve-verification",
    ),
    path(
        "admin/verifications/<str:verification_id>/reject",
        views.reject_verification,
        name="reject-verification",
    ),
]
