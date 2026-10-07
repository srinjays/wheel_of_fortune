from django.apps import AppConfig


class AssignmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "game.assignments"
    label = "game_assignments"
    verbose_name = "Tasks and Assignments"
