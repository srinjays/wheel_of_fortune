"""Assignment views: team assignment, questions, rounds, tasks, attendance (SQLite-backed)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from django.http import HttpRequest, JsonResponse

from game.competition.views import competition_payload
from game.core.auth import authenticated
from game.core.errors import ApiError, api_errors, success
from game.core.http import api_methods, iso, read_json, required_int, required_text
from game.core.models import (
    Assignment,
    Competition,
    Question,
    Round,
    Task,
    Team,
    TeamAttendance,
    TeamThemeAssignment,
    Theme,
    ThemeSpinAttempt,
    Verification,
)


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _question_payload(question: Question) -> dict:
    question_id = str(question.id)
    return {
        "id": question_id,
        "key": question_id,
        "name": question.question,
        "question": question.question,
        "themeKey": question.theme_key,
        "themeName": question.theme_name,
        "spinNumber": question.spin_number,
        "points": question.points,
    }


def _question_admin_enabled() -> None:
    competition = Competition.objects.filter(pk="current").first()
    if competition and competition.status in {"running", "paused", "starting"}:
        raise ApiError(
            409,
            "competition_started",
            "Questions cannot be changed while a round is active.",
        )


def _wheel_items() -> list[dict]:
    return list(Theme.objects.values("key", "name").order_by("name"))


@api_errors
@authenticated(role="team")
@api_methods("GET")
def team_assignment(request: HttpRequest) -> JsonResponse:
    user = request.game_user  # type: ignore[attr-defined]
    competition = Competition.objects.filter(pk="current").first()
    wheel_items = _wheel_items()
    if competition is None or (competition.current_spin or 0) == 0:
        return success(
            {
                "competition": competition_payload(competition, wheel_items),
                "assignment": None,
                "round": None,
            }
        )

    team_id = user.team_id
    spin_number = competition.current_spin
    round_details = None
    if competition.status in {"running", "paused", "finished"}:
        round_record = Round.objects.filter(pk=f"round-{spin_number}").first()
        if round_record:
            round_details = {
                "spinNumber": spin_number,
                "title": round_record.title,
                "description": round_record.description,
            }

    assignment = Assignment.objects.filter(team_id=team_id, spin_number=spin_number).first()
    if assignment is None:
        return success(
            {
                "competition": competition_payload(competition, wheel_items),
                "assignment": None,
                "round": round_details,
            }
        )

    spin_attempt = ThemeSpinAttempt.objects.filter(
        team_id=team_id, spin_number=spin_number
    ).first()
    question = None
    if (
        assignment.question_id
        and spin_attempt
        and spin_attempt.question_id == assignment.question_id
    ):
        question = Question.objects.filter(pk=assignment.question_id).first()

    team_theme = TeamThemeAssignment.objects.filter(pk=team_id).first()
    theme = (
        {"key": team_theme.theme_key, "name": team_theme.theme_name}
        if team_theme
        else None
    )
    approved = Verification.objects.filter(
        team_id=team_id, spin_number=spin_number, status="approved"
    ).first()
    pending = Verification.objects.filter(team_id=team_id, status="pending").first()
    rejected = (
        Verification.objects.filter(
            team_id=team_id, spin_number=spin_number, status="rejected"
        )
        .order_by("-reviewed_at")
        .first()
    )
    return success(
        {
            "competition": competition_payload(competition, wheel_items),
            "assignment": {
                "spinNumber": spin_number,
                "task": (
                    {
                        "id": str(question.id),
                        "title": question.question,
                        "question": question.question,
                        "description": "",
                        "points": question.points,
                    }
                    if question
                    else None
                ),
                "theme": theme,
                "spinAttempted": spin_attempt is not None,
                "completed": approved is not None,
                "verificationStatus": (
                    "waiting"
                    if pending
                    else "approved"
                    if approved
                    else "rejected"
                    if rejected
                    else None
                ),
                "rejectionReason": rejected.rejection_reason if rejected else None,
            },
            "round": round_details,
        }
    )


@api_errors
@authenticated(role="team")
@api_methods("GET")
def team_questions(request: HttpRequest) -> JsonResponse:
    user = request.game_user  # type: ignore[attr-defined]
    team_id = user.team_id
    competition = Competition.objects.filter(pk="current").first()
    spin_number = competition.current_spin if competition else 0
    theme_assignment = TeamThemeAssignment.objects.filter(pk=team_id).first()
    assigned_key = theme_assignment.theme_key if theme_assignment else None

    requested_theme = request.GET.get("theme")
    if requested_theme and requested_theme != assigned_key:
        raise ApiError(403, "forbidden_theme", "You cannot access questions for another theme.")
    requested_round = request.GET.get("round")
    if requested_round:
        try:
            requested_value = int(requested_round)
        except ValueError as exc:
            raise ApiError(400, "invalid_round", "round must be a number from 1 to 4.") from exc
        if requested_value != spin_number:
            raise ApiError(
                403, "forbidden_round", "You can only access questions for the current round."
            )

    if (
        not assigned_key
        or not competition
        or competition.status not in {"running", "paused", "finished"}
        or not 1 <= spin_number <= 4
    ):
        return success({"theme": None, "spinNumber": spin_number, "items": []})

    questions = Question.objects.filter(
        theme_key=assigned_key, spin_number=spin_number
    ).order_by("created_at")
    return success(
        {
            "theme": {"key": assigned_key, "name": theme_assignment.theme_name},
            "spinNumber": spin_number,
            "items": [_question_payload(item) for item in questions],
        }
    )


@api_errors
@authenticated(role="admin")
@api_methods("GET", "POST")
def manage_questions(request: HttpRequest) -> JsonResponse:
    if request.method == "POST":
        return _save_question(read_json(request))
    questions = Question.objects.all().order_by("theme_key", "spin_number", "created_at")
    return success({"items": [_question_payload(item) for item in questions]})


@api_errors
@authenticated(role="admin")
@api_methods("PUT")
def update_question(request: HttpRequest, question_id: str) -> JsonResponse:
    _question_admin_enabled()
    parsed = _parse_uuid(question_id)
    if parsed is None:
        raise ApiError(404, "question_not_found", "Question not found.")
    body = read_json(request)
    existing = Question.objects.filter(pk=parsed).first()
    if existing is None:
        raise ApiError(404, "question_not_found", "Question not found.")
    return _save_question(body, existing=existing)


def _save_question(body: dict, *, existing: Question | None = None) -> JsonResponse:
    theme_key = required_text(body, "themeKey", maximum=100).lower()
    theme = Theme.objects.filter(pk=theme_key).first()
    if theme is None:
        raise ApiError(400, "invalid_theme", "Select a valid theme for this question.")
    spin_number = required_int(body, "spinNumber", minimum=1, maximum=4)
    text = required_text(body, "question", maximum=1000)
    points = required_int(body, "points", minimum=1, maximum=100000)
    now = datetime.now(timezone.utc)
    question = existing or Question(created_at=now)
    question.question = text
    question.theme_key = theme_key
    question.theme_name = theme.name
    question.spin_number = spin_number
    question.points = points
    question.save()
    return success(_question_payload(question), status=201 if existing is None else 200)


@api_errors
@authenticated(role="admin")
@api_methods("DELETE")
def delete_question(_request: HttpRequest, question_id: str) -> JsonResponse:
    _question_admin_enabled()
    parsed = _parse_uuid(question_id)
    if parsed is None:
        raise ApiError(404, "question_not_found", "Question not found.")
    deleted, _ = Question.objects.filter(pk=parsed).delete()
    if deleted != 1:
        raise ApiError(404, "question_not_found", "Question not found.")
    return success({"id": question_id, "deleted": True})


@api_errors
@authenticated(role="admin")
@api_methods("PUT")
def configure_task(request: HttpRequest, spin_number: int, theme_key: str) -> JsonResponse:
    if not 1 <= spin_number <= 4:
        raise ApiError(400, "invalid_spin", "spin_number must be between 1 and 4.")
    theme = Theme.objects.filter(pk=theme_key).first()
    if theme is None:
        raise ApiError(404, "theme_not_found", "Theme not found.")

    body = read_json(request)
    title = required_text(body, "title", maximum=100)
    description = required_text(body, "description", maximum=2000)
    points = required_int(body, "points", minimum=1, maximum=100000)
    Task.objects.update_or_create(
        pk=f"spin-{spin_number}-{theme_key}",
        defaults={
            "spin_number": spin_number,
            "theme_key": theme_key,
            "theme_name": theme.name,
            "title": title,
            "description": description,
            "points": points,
        },
    )
    return success(
        {
            "spinNumber": spin_number,
            "themeKey": theme_key,
            "themeName": theme.name,
            "title": title,
            "description": description,
            "points": points,
        }
    )


@api_errors
@authenticated(role="admin")
@api_methods("PUT")
def configure_round(request: HttpRequest, spin_number: int) -> JsonResponse:
    if not 1 <= spin_number <= 4:
        raise ApiError(400, "invalid_spin", "spin_number must be between 1 and 4.")
    body = read_json(request)
    title = required_text(body, "title", maximum=100)
    description = required_text(body, "description", maximum=2000)
    Round.objects.update_or_create(
        pk=f"round-{spin_number}",
        defaults={"spin_number": spin_number, "title": title, "description": description},
    )
    return success({"spinNumber": spin_number, "title": title, "description": description})


@api_errors
@authenticated(role="volunteer")
@api_methods("GET")
def team_attendance(request: HttpRequest) -> JsonResponse:
    spin_value = request.GET.get("spinNumber", "1")
    try:
        spin_number = int(spin_value)
    except ValueError as exc:
        raise ApiError(400, "invalid_spin", "spinNumber must be between 1 and 4.") from exc
    if not 1 <= spin_number <= 4:
        raise ApiError(400, "invalid_spin", "spinNumber must be between 1 and 4.")

    teams = Team.objects.filter(is_active=True).order_by("code")
    attendance = {
        record.team_id: record
        for record in TeamAttendance.objects.filter(spin_number=spin_number)
    }
    items = []
    for team in teams:
        record = attendance.get(team.id)
        items.append(
            {
                "teamId": team.id,
                "teamName": team.name,
                "teamCode": team.code,
                "status": record.status if record else "unmarked",
                "markedAt": iso(record.marked_at) if record else None,
            }
        )
    return success(
        {
            "spinNumber": spin_number,
            "items": items,
            "presentCount": sum(item["status"] == "present" for item in items),
            "absentCount": sum(item["status"] == "absent" for item in items),
            "unmarkedCount": sum(item["status"] == "unmarked" for item in items),
        }
    )


@api_errors
@authenticated(role="volunteer")
@api_methods("PUT")
def mark_team_attendance(request: HttpRequest, spin_number: int, team_id: str) -> JsonResponse:
    if not 1 <= spin_number <= 4:
        raise ApiError(400, "invalid_spin", "spinNumber must be between 1 and 4.")
    team = Team.objects.filter(pk=team_id, is_active=True).first()
    if team is None:
        raise ApiError(404, "team_not_found", "Active team not found.")
    body = read_json(request)
    status = required_text(body, "status", maximum=20).lower()
    if status not in {"present", "absent"}:
        raise ApiError(400, "invalid_input", "status must be either 'present' or 'absent'.")
    user = request.game_user  # type: ignore[attr-defined]
    marked_at = datetime.now(timezone.utc)
    TeamAttendance.objects.update_or_create(
        team_id=team_id,
        spin_number=spin_number,
        defaults={
            "team_name": team.name,
            "team_code": team.code,
            "status": status,
            "marked_at": marked_at,
            "marked_by": str(user.id),
        },
    )
    return success(
        {
            "teamId": team_id,
            "teamName": team.name,
            "spinNumber": spin_number,
            "status": status,
            "markedAt": iso(marked_at),
        }
    )
