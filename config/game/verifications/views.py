"""Verification (buzzer) views (SQLite-backed)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest, JsonResponse

from game.core.auth import authenticated
from game.core.errors import ApiError, api_errors, success
from game.core.http import api_methods, iso, read_json, required_text
from game.core.models import (
    Assignment,
    Competition,
    Question,
    Team,
    TeamThemeAssignment,
    ThemeSpinAttempt,
    Verification,
)
from game.core.sockets import emit_event
from game.leaderboard.views import leaderboard_data


@api_errors
@authenticated(role="team")
@api_methods("POST")
def buzzer(request: HttpRequest) -> JsonResponse:
    user = request.game_user  # type: ignore[attr-defined]
    competition = Competition.objects.filter(pk="current").first()
    now = datetime.now(timezone.utc)
    if (
        competition is None
        or competition.status != "running"
        or competition.spin_ends_at is None
        or now >= competition.spin_ends_at
    ):
        raise ApiError(409, "spin_not_active", "The current spin is not accepting submissions.")

    team_id = user.team_id
    spin_number = competition.current_spin
    assignment = Assignment.objects.filter(team_id=team_id, spin_number=spin_number).first()
    if assignment is None:
        raise ApiError(
            409, "assignment_missing", "No task is assigned to this team for this spin."
        )
    spin_attempt = ThemeSpinAttempt.objects.filter(
        team_id=team_id, spin_number=spin_number
    ).first()
    theme_assignment = TeamThemeAssignment.objects.filter(pk=team_id).first()
    expected_question_id = spin_attempt.question_id if spin_attempt else None
    if (
        not theme_assignment
        or not expected_question_id
        or assignment.question_id != expected_question_id
    ):
        raise ApiError(
            409,
            "theme_not_selected",
            "Spin the question wheel to receive your question first.",
        )
    if Verification.objects.filter(
        team_id=team_id, spin_number=spin_number, status="approved"
    ).exists():
        raise ApiError(409, "task_already_approved", "This spin's task is already completed.")
    if Verification.objects.filter(team_id=team_id, status="pending").exists():
        raise ApiError(409, "verification_pending", "A verification request is already pending.")

    question = Question.objects.filter(pk=expected_question_id).first()
    if (
        question is None
        or question.theme_key != theme_assignment.theme_key
        or question.spin_number != spin_number
    ):
        raise ApiError(409, "question_missing", "The assigned question is no longer available.")
    team = Team.objects.filter(pk=team_id).first()
    if team is None:
        raise ApiError(404, "team_not_found", "The team no longer exists.")

    try:
        with transaction.atomic():
            verification = Verification.objects.create(
                team_id=team_id,
                team_name=team.name,
                spin_number=spin_number,
                assignment_id=assignment.id,
                task_id=str(question.id),
                task_title=question.question,
                points=question.points,
                status="pending",
                created_at=now,
            )
    except IntegrityError as exc:
        raise ApiError(
            409, "verification_pending", "A verification request is already pending."
        ) from exc

    position = Verification.objects.filter(status="pending").filter(
        Q(created_at__lt=now) | Q(created_at=now, id=verification.id)
    ).count()
    request_id = str(verification.id)
    event = {
        "id": request_id,
        "teamId": team_id,
        "teamName": team.name,
        "spinNumber": spin_number,
        "taskTitle": question.question,
        "queuePosition": position,
        "createdAt": now.isoformat(),
    }
    emit_event("buzzer_registered", event, room="admins")
    emit_event("verification_waiting", event, room=f"team:{team_id}")
    return success({"verificationId": request_id, "queuePosition": position}, status=201)


@api_errors
@authenticated(role=("admin", "volunteer"))
@api_methods("GET")
def verification_queue(_request: HttpRequest) -> JsonResponse:
    pending = Verification.objects.filter(status="pending").order_by("created_at", "id")
    queue = [
        {
            "id": str(item.id),
            "teamId": item.team_id,
            "teamName": item.team_name,
            "spinNumber": item.spin_number,
            "taskTitle": item.task_title,
            "createdAt": iso(item.created_at),
            "queuePosition": position,
        }
        for position, item in enumerate(pending, start=1)
    ]
    return success({"items": queue, "count": len(queue)})


def _verification_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise ApiError(404, "verification_not_found", "Verification request not found.") from exc


def _resolve_verification(
    request: HttpRequest,
    verification_id: str,
    *,
    status: str,
    reason: str | None = None,
) -> Verification:
    """Atomically move a pending verification to approved/rejected."""
    user = request.game_user  # type: ignore[attr-defined]
    now = datetime.now(timezone.utc)
    pk = _verification_id(verification_id)
    update: dict = {"status": status, "reviewed_at": now, "reviewed_by": str(user.id)}
    if reason is not None:
        update["rejection_reason"] = reason
    # Conditional UPDATE acts like Mongo's find_one_and_update: only one reviewer wins.
    rows = Verification.objects.filter(pk=pk, status="pending").update(**update)
    if rows != 1:
        raise ApiError(
            409,
            "verification_not_pending",
            "Verification is missing or has already been reviewed.",
        )
    return Verification.objects.get(pk=pk)


@api_errors
@authenticated(role=("admin", "volunteer"))
@api_methods("POST")
def approve_verification(request: HttpRequest, verification_id: str) -> JsonResponse:
    verification = _resolve_verification(request, verification_id, status="approved")
    emit_event(
        "verification_approved",
        {
            "verificationId": str(verification.id),
            "spinNumber": verification.spin_number,
            "points": verification.points,
        },
        room=f"team:{verification.team_id}",
    )
    emit_event(
        "score_updated",
        {
            "teamId": verification.team_id,
            "teamName": verification.team_name,
            "pointsAdded": verification.points,
        },
    )
    emit_event("leaderboard_updated", {"items": leaderboard_data()})
    return success(
        {
            "id": str(verification.id),
            "status": "approved",
            "pointsAdded": verification.points,
        }
    )


@api_errors
@authenticated(role=("admin", "volunteer"))
@api_methods("POST")
def reject_verification(request: HttpRequest, verification_id: str) -> JsonResponse:
    body = read_json(request)
    reason = required_text(body, "reason", maximum=1000)
    verification = _resolve_verification(
        request, verification_id, status="rejected", reason=reason
    )
    emit_event(
        "verification_rejected",
        {
            "verificationId": str(verification.id),
            "spinNumber": verification.spin_number,
            "reason": verification.rejection_reason,
        },
        room=f"team:{verification.team_id}",
    )
    return success(
        {
            "id": str(verification.id),
            "status": "rejected",
            "reason": verification.rejection_reason,
            "pointsAdded": 0,
        }
    )
