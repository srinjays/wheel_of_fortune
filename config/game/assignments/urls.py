from django.urls import path

from . import views

urlpatterns = [
    path("team/assignment", views.team_assignment, name="team-assignment"),
    path("questions", views.team_questions, name="team-questions"),
    path("admin/questions", views.manage_questions, name="manage-questions"),
    path("admin/questions/<str:question_id>", views.update_question, name="update-question"),
    path("admin/questions/<str:question_id>/delete", views.delete_question, name="delete-question"),
    path("volunteer/attendance", views.team_attendance, name="team-attendance"),
    path(
        "volunteer/attendance/<int:spin_number>/<str:team_id>",
        views.mark_team_attendance,
        name="mark-team-attendance",
    ),
    path(
        "admin/tasks/<int:spin_number>/<slug:theme_key>",
        views.configure_task,
        name="configure-themed-task",
    ),
    path("admin/rounds/<int:spin_number>", views.configure_round, name="configure-round"),
]
