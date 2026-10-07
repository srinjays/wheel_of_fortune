"""Django models replacing all MongoDB collections."""
from __future__ import annotations

import uuid

from django.db import models


class Team(models.Model):
    """Replaces MongoDB 'teams' collection."""
    id = models.CharField(max_length=20, primary_key=True)          # "team-01"
    code = models.CharField(max_length=10, unique=True)              # "TEAM01"
    name = models.CharField(max_length=50)                           # "Team 01"
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "teams"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class GameUser(models.Model):
    """Replaces MongoDB 'users' collection.
    Named GameUser to avoid collision with Django's built-in User.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=80, unique=True)
    role = models.CharField(max_length=20)                           # admin, team, volunteer
    password_hash = models.CharField(max_length=256)
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="users", db_column="team_id",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "game_users"

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"


class Theme(models.Model):
    """Replaces MongoDB 'themes' collection (wheel items)."""
    key = models.CharField(max_length=100, primary_key=True)         # "marvel"
    name = models.CharField(max_length=100, unique=True)             # "Marvel"

    class Meta:
        db_table = "themes"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Competition(models.Model):
    """Replaces MongoDB 'competition' collection (singleton: id='current')."""
    id = models.CharField(max_length=20, primary_key=True)
    status = models.CharField(max_length=20, default="not_started")
    current_spin = models.IntegerField(default=0)
    spin_started_at = models.DateTimeField(null=True, blank=True)
    spin_ends_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    theme_key = models.CharField(max_length=100, blank=True, default="")
    theme_name = models.CharField(max_length=100, blank=True, default="")
    theme_selected_by = models.CharField(max_length=100, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "competition"

    def __str__(self) -> str:
        return f"Competition ({self.status}, spin {self.current_spin})"


class CompetitionSettings(models.Model):
    """Replaces MongoDB 'competition_settings' collection (singleton)."""
    id = models.CharField(max_length=20, primary_key=True)
    spin_duration_seconds = models.IntegerField(default=900)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "competition_settings"


class Round(models.Model):
    """Replaces MongoDB 'rounds' collection."""
    id = models.CharField(max_length=20, primary_key=True)           # "round-1"
    spin_number = models.IntegerField(unique=True)
    title = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rounds"
        ordering = ["spin_number"]


class Question(models.Model):
    """Replaces MongoDB 'questions' collection."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.CharField(max_length=1000)
    theme_key = models.CharField(max_length=100, db_index=True)
    theme_name = models.CharField(max_length=100)
    spin_number = models.IntegerField(db_index=True)
    points = models.IntegerField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "questions"
        ordering = ["theme_key", "spin_number", "created_at"]


class Task(models.Model):
    """Replaces MongoDB 'tasks' collection (admin-configured task per theme/round)."""
    id = models.CharField(max_length=100, primary_key=True)          # "spin-1-marvel"
    spin_number = models.IntegerField()
    theme_key = models.CharField(max_length=100)
    theme_name = models.CharField(max_length=100)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    points = models.IntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tasks"
        unique_together = [("spin_number", "theme_key")]


class Assignment(models.Model):
    """Replaces MongoDB 'assignments' collection."""
    id = models.CharField(max_length=50, primary_key=True)           # "team-01:1"
    team_id = models.CharField(max_length=20, db_index=True)
    spin_number = models.IntegerField()
    assigned_at = models.DateTimeField()
    task_id = models.CharField(max_length=100, blank=True, null=True)
    question_id = models.UUIDField(null=True, blank=True)
    theme_key = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        db_table = "assignments"
        unique_together = [("team_id", "spin_number")]


class TeamThemeAssignment(models.Model):
    """Replaces MongoDB 'team_theme_assignments' collection.
    Permanent team→theme mapping assigned during round 1.
    """
    team_id = models.CharField(max_length=20, primary_key=True)
    theme_key = models.CharField(max_length=100)
    theme_name = models.CharField(max_length=100)
    assigned_at = models.DateTimeField()

    class Meta:
        db_table = "team_theme_assignments"


class ThemeSpinAttempt(models.Model):
    """Replaces MongoDB 'theme_spin_attempts' collection.
    One spin per team per round.
    """
    id = models.CharField(max_length=50, primary_key=True)           # "1:team-01"
    team_id = models.CharField(max_length=20, db_index=True)
    spin_number = models.IntegerField()
    theme_key = models.CharField(max_length=100)
    theme_name = models.CharField(max_length=100)
    question_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = "theme_spin_attempts"
        unique_together = [("spin_number", "team_id")]


class Verification(models.Model):
    """Replaces MongoDB 'verifications' collection (buzzer submissions)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team_id = models.CharField(max_length=20, db_index=True)
    team_name = models.CharField(max_length=50)
    spin_number = models.IntegerField()
    assignment_id = models.CharField(max_length=50)
    task_id = models.CharField(max_length=100)
    task_title = models.CharField(max_length=1000)
    points = models.IntegerField()
    status = models.CharField(max_length=20, default="pending", db_index=True)
    created_at = models.DateTimeField()
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=100, null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "verifications"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["team_id", "spin_number"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["team_id"],
                condition=models.Q(status="pending"),
                name="one_pending_verification_per_team",
            ),
        ]
        ordering = ["created_at"]


class TeamAttendance(models.Model):
    """Replaces MongoDB 'team_attendance' collection."""
    team_id = models.CharField(max_length=20)
    team_name = models.CharField(max_length=50)
    team_code = models.CharField(max_length=10)
    spin_number = models.IntegerField()
    status = models.CharField(max_length=20)                         # present, absent
    marked_at = models.DateTimeField()
    marked_by = models.CharField(max_length=100)

    class Meta:
        db_table = "team_attendance"
        unique_together = [("team_id", "spin_number")]


class RateLimit(models.Model):
    """Replaces MongoDB 'rate_limits' collection with TTL index."""
    key = models.CharField(max_length=64, primary_key=True)
    count = models.IntegerField(default=0)
    expire_at = models.DateTimeField()

    class Meta:
        db_table = "rate_limits"
