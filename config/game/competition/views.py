"""Competition views: state machine, wheel items, spin logic (SQLite-backed)."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from django.db import IntegrityError, transaction
from django.http import HttpRequest, JsonResponse

from game.core.auth import authenticated
from game.core.errors import ApiError, api_errors, success
from game.core.http import api_methods, iso, read_json, required_int, required_text
from game.core.models import (
    Assignment,
    Competition,
    CompetitionSettings,
    Question,
    Round,
    Team,
    TeamThemeAssignment,
    Theme,
    ThemeSpinAttempt,
)
from game.core.sockets import emit_event


def competition_payload(
    competition: Competition | None,
    wheel_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    wheel_payload = [
        {"key": item["key"], "name": item["name"]}
        for item in (wheel_items or [])
    ]
    if competition is None:
        return {
            "status": "not_started",
            "currentSpin": 0,
            "spinStartedAt": None,
            "spinEndsAt": None,
            "remainingSeconds": None,
            "timerExpired": False,
            "paused": False,
            "finished": False,
            "theme": None,
            "wheelItems": wheel_payload,
        }
    status = competition.status or "not_started"
    ends_at = competition.spin_ends_at
    timer_now = competition.paused_at if status == "paused" else now
    remaining = (
        max(0, int((ends_at - timer_now).total_seconds()))
        if ends_at and timer_now
        else None
    )
    return {
        "status": status,
        "currentSpin": competition.current_spin or 0,
        "spinStartedAt": iso(competition.spin_started_at),
        "spinEndsAt": iso(ends_at),
        "remainingSeconds": remaining,
        "timerExpired": bool(ends_at and remaining == 0 and status == "running"),
        "paused": status == "paused",
        "finished": status == "finished",
        "theme": (
            {
                "key": competition.theme_key,
                "name": competition.theme_name,
            }
            if competition.theme_key and competition.theme_name
            else None
        ),
        "wheelItems": wheel_payload,
    }


@api_errors
@api_methods("GET")
def competition_state(_request: HttpRequest) -> JsonResponse:
    competition = Competition.objects.filter(pk="current").first()
    themes = list(Theme.objects.values("key", "name").order_by("name"))
    return success(competition_payload(competition, themes))


@api_errors
@authenticated(role="admin")
@api_methods("GET")
def competition_setup(_request: HttpRequest) -> JsonResponse:
    settings_obj = CompetitionSettings.objects.filter(pk="current").first()
    rounds = list(Round.objects.all().order_by("spin_number"))
    configured_rounds = {
        r.spin_number
        for r in rounds
        if r.title.strip() and r.description.strip()
    }
    questions = list(Question.objects.values("theme_key", "spin_number", "question"))
    active_team_count = Team.objects.filter(is_active=True).count()
    wheel_item_count = Theme.objects.count()
    themes = list(Theme.objects.values("key", "name"))
    configured_question_pairs = {
        (q["theme_key"], q["spin_number"])
        for q in questions
        if q["question"].strip()
    }
    configured_spins = {
        spin
        for spin in range(1, 5)
        if themes and all((t["key"], spin) in configured_question_pairs for t in themes)
    }
    duration_configured = bool(
        settings_obj
        and isinstance(settings_obj.spin_duration_seconds, int)
        and settings_obj.spin_duration_seconds > 0
    )
    teams_configured = active_team_count > 0
    wheel_configured = wheel_item_count > 0
    tasks_configured = configured_spins == {1, 2, 3, 4}
    return success(
        {
            "spinDurationSeconds": (
                settings_obj.spin_duration_seconds if settings_obj else None
            ),
            "tasks": [],
            "configuredSpins": sorted(configured_spins),
            "rounds": [
                {
                    "_id": r.id,
                    "spinNumber": r.spin_number,
                    "title": r.title,
                    "description": r.description,
                }
                for r in rounds
            ],
            "configuredRounds": sorted(configured_rounds),
            "themes": themes,
            "activeTeamCount": active_team_count,
            "wheelItemCount": wheel_item_count,
            "ready": (
                duration_configured
                and tasks_configured
                and configured_rounds == {1, 2, 3, 4}
                and teams_configured
                and wheel_configured
            ),
        }
    )


@api_errors
@authenticated(role="admin")
@api_methods("PUT")
def update_competition_settings(request: HttpRequest) -> JsonResponse:
    body = read_json(request)
    duration = required_int(body, "spinDurationSeconds", minimum=1, maximum=86400)
    now = datetime.now(timezone.utc)
    CompetitionSettings.objects.update_or_create(
        pk="current",
        defaults={"spin_duration_seconds": duration, "updated_at": now},
    )
    return success({"spinDurationSeconds": duration})


def _require_competition_not_started() -> None:
    competition = Competition.objects.filter(pk="current").first()
    if competition and competition.current_spin > 0:
        raise ApiError(
            409,
            "competition_started",
            "Themes cannot be changed after the competition has started.",
        )


@api_errors
@authenticated(role="admin")
@api_methods("GET")
def wheel_items(_request: HttpRequest) -> JsonResponse:
    items = list(Theme.objects.all().order_by("name"))
    return success(
        {
            "items": [
                {"key": item.key, "name": item.name}
                for item in items
            ]
        }
    )


@api_errors
@authenticated(role="admin")
@api_methods("POST")
def add_wheel_item(request: HttpRequest) -> JsonResponse:
    _require_competition_not_started()
    body = read_json(request)
    name = required_text(body, "name", maximum=100)
    key = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not key:
        raise ApiError(
            400,
            "invalid_input",
            "name must contain at least one letter or number.",
        )
    try:
        Theme.objects.create(key=key, name=name)
    except IntegrityError as exc:
        raise ApiError(
            409, "wheel_item_exists", "A wheel item with that name already exists."
        ) from exc
    return success({"key": key, "name": name}, status=201)


@api_errors
@authenticated(role="admin")
@api_methods("DELETE")
def remove_wheel_item(_request: HttpRequest, item_key: str) -> JsonResponse:
    _require_competition_not_started()
    deleted_count, _ = Theme.objects.filter(pk=item_key).delete()
    if deleted_count != 1:
        raise ApiError(404, "wheel_item_not_found", "Wheel item not found.")
    return success({"key": item_key, "removed": True})


def _start_requirements() -> tuple[
    CompetitionSettings,
    list[Question],
    list[Team],
]:
    spin_settings = CompetitionSettings.objects.filter(pk="current").first()
    if spin_settings is None:
        raise ApiError(
            409, "settings_required", "Configure the spin duration before starting."
        )
    rounds = list(Round.objects.all())
    configured_rounds = {
        r.spin_number
        for r in rounds
        if r.title.strip() and r.description.strip()
    }
    if configured_rounds != {1, 2, 3, 4}:
        raise ApiError(
            409,
            "round_details_required",
            "Add a title and description for all four rounds before starting.",
        )
    questions = list(Question.objects.values("theme_key", "spin_number", "question"))
    themes = list(Theme.objects.all().order_by("key"))
    question_pairs = {
        (q["theme_key"], q["spin_number"])
        for q in questions
        if q["question"].strip()
    }
    if not themes or any(
        (theme.key, spin) not in question_pairs
        for spin in range(1, 5)
        for theme in themes
    ):
        raise ApiError(
            409,
            "questions_required",
            "Add at least one question for every theme in each of the four rounds.",
        )
    teams = list(Team.objects.filter(is_active=True).order_by("code"))
    if not teams:
        raise ApiError(
            409,
            "teams_required",
            "At least one active team must be provisioned before starting.",
        )
    themes_check = list(Theme.objects.all().order_by("key"))
    if not themes_check:
        raise ApiError(
            409, "themes_required", "Add at least one item to the spin wheel."
        )
    return spin_settings, list(Question.objects.all()), teams


@api_errors
@authenticated(role="admin")
@api_methods("POST")
def start_spin(request: HttpRequest) -> JsonResponse:
    spin_settings, _questions, teams = _start_requirements()
    try:
        body = read_json(request)
    except Exception:
        body = {}

    competition = Competition.objects.filter(pk="current").first()
    competition_missing = competition is None
    if competition is None:
        status = "not_started"
        current_spin = 0
    else:
        status = competition.status
        current_spin = competition.current_spin or 0
    now = datetime.now(timezone.utc)

    if status in {"paused", "starting"}:
        raise ApiError(
            409,
            "invalid_competition_state",
            "The competition cannot start a spin in its current state.",
        )
    if status == "running":
        ends_at = competition.spin_ends_at if competition else None
        if ends_at is None or now < ends_at:
            raise ApiError(
                409,
                "spin_still_active",
                "The current spin must expire before the next spin starts.",
            )

    requested_spin = body.get("spinNumber")
    if requested_spin is not None:
        next_spin = int(requested_spin)
    else:
        next_spin = current_spin + 1

    if not 1 <= next_spin <= 4:
        raise ApiError(409, "competition_complete", "All four spins have already started.")

    # Atomic state transition
    with transaction.atomic():
        if competition_missing:
            try:
                Competition.objects.create(
                    id="current",
                    status="starting",
                    current_spin=next_spin,
                    updated_at=now,
                    theme_key="",
                    theme_name="",
                    theme_selected_by="",
                )
            except IntegrityError as exc:
                raise ApiError(
                    409, "competition_changed", "Competition state changed; refresh and try again."
                ) from exc
        else:
            rows = Competition.objects.filter(
                pk="current",
                current_spin=current_spin,
                status=status,
            ).update(
                status="starting",
                current_spin=next_spin,
                updated_at=now,
                theme_key="",
                theme_name="",
                theme_selected_by="",
            )
            if rows == 0:
                raise ApiError(
                    409, "competition_changed", "Competition state changed; refresh and try again."
                )

    # Create assignments for each team
    assignment_events: list[dict[str, Any]] = []
    try:
      with transaction.atomic():
        for team in teams:
            assignment_id = f"{team.id}:{next_spin}"
            Assignment.objects.update_or_create(
                id=assignment_id,
                defaults={
                    "team_id": team.id,
                    "spin_number": next_spin,
                    "assigned_at": now,
                },
            )
            assignment_events.append(
                {
                    "teamId": team.id,
                    "data": {
                        "spinNumber": next_spin,
                        "task": None,
                        "theme": None,
                    },
                }
            )
    except Exception:
        # Rollback competition state
        restored: dict[str, Any] = {
            "status": status,
            "current_spin": current_spin,
            "updated_at": datetime.now(timezone.utc),
        }
        Competition.objects.filter(
            pk="current", status="starting", current_spin=next_spin
        ).update(**restored)
        raise

    ends_at = now + timedelta(seconds=spin_settings.spin_duration_seconds)
    rows = Competition.objects.filter(
        pk="current", status="starting", current_spin=next_spin
    ).update(
        status="running",
        spin_started_at=now,
        spin_ends_at=ends_at,
        updated_at=datetime.now(timezone.utc),
    )
    if rows != 1:
        raise ApiError(
            409,
            "competition_changed",
            "Competition state changed while starting the spin.",
        )
    payload = {
        "status": "running",
        "currentSpin": next_spin,
        "spinStartedAt": now.isoformat(),
        "spinEndsAt": ends_at.isoformat(),
        "remainingSeconds": spin_settings.spin_duration_seconds,
        "theme": None,
    }
    emit_event("spin_started", payload)
    for assignment_event in assignment_events:
        emit_event(
            "task_assigned",
            assignment_event["data"],
            room=f"team:{assignment_event['teamId']}",
        )
    emit_event(
        "task_assigned",
        {"spinNumber": next_spin, "theme": None},
        room="admins",
    )
    emit_event("competition_updated", payload)
    return success(payload)


@api_errors
@authenticated(role="team")
@api_methods("POST")
def team_spin(request: HttpRequest) -> JsonResponse:
    user = request.game_user  # type: ignore[attr-defined]
    team_id = user.team_id
    now = datetime.now(timezone.utc)
    competition = Competition.objects.filter(pk="current").first()
    if (
        competition is None
        or competition.status != "running"
        or competition.current_spin < 1
        or competition.spin_ends_at is None
        or now >= competition.spin_ends_at
    ):
        raise ApiError(
            409,
            "spin_not_active",
            "The team wheel can only be spun during an active round.",
        )

    spin_number = competition.current_spin
    assignment = Assignment.objects.filter(
        team_id=team_id, spin_number=spin_number
    ).first()
    if assignment is None:
        raise ApiError(
            409,
            "assignment_missing",
            "Your team must have a round assignment before spinning.",
        )
    if ThemeSpinAttempt.objects.filter(
        team_id=team_id, spin_number=spin_number
    ).exists():
        raise ApiError(
            409,
            "theme_spin_already_used",
            "Your team has already spun the wheel this round.",
        )

    team_theme = TeamThemeAssignment.objects.filter(pk=team_id).first()
    if team_theme is None:
        if spin_number != 1:
            raise ApiError(
                409,
                "theme_not_assigned",
                "Your theme must be assigned during round 1 before later rounds.",
            )
        themes = list(Theme.objects.all().order_by("key"))
        if not themes:
            raise ApiError(409, "themes_required", "There are no items on the spin wheel.")
        chosen_theme = secrets.choice(themes)
        try:
            TeamThemeAssignment.objects.create(
                team_id=team_id,
                theme_key=chosen_theme.key,
                theme_name=chosen_theme.name,
                assigned_at=now,
            )
            team_theme = TeamThemeAssignment.objects.get(pk=team_id)
        except IntegrityError:
            team_theme = TeamThemeAssignment.objects.get(pk=team_id)

    candidate = {"key": team_theme.theme_key, "name": team_theme.theme_name}
    questions = list(
        Question.objects.filter(
            theme_key=candidate["key"], spin_number=spin_number
        ).order_by("created_at")
    )
    if not questions:
        raise ApiError(
            409,
            "theme_questions_missing",
            "There are no questions configured for your theme in this round.",
        )
    question = secrets.choice(questions)
    attempt_id = f"{spin_number}:{team_id}"
    attempt = ThemeSpinAttempt(
        id=attempt_id,
        team_id=team_id,
        spin_number=spin_number,
        theme_key=candidate["key"],
        theme_name=candidate["name"],
        question_id=question.id,
        created_at=now,
    )
    try:
        with transaction.atomic():
            attempt.save(force_insert=True)
    except IntegrityError as exc:
        raise ApiError(
            409,
            "theme_spin_already_used",
            "Your team has already spun the wheel this round.",
        ) from exc

    # Re-check competition hasn't ended
    competition = Competition.objects.filter(pk="current").first()
    current_time = datetime.now(timezone.utc)
    if (
        competition is None
        or competition.status != "running"
        or competition.current_spin != spin_number
        or competition.spin_ends_at is None
        or current_time >= competition.spin_ends_at
    ):
        ThemeSpinAttempt.objects.filter(pk=attempt_id).delete()
        raise ApiError(
            409,
            "spin_not_active",
            "The round ended before your wheel spin could be registered.",
        )

    try:
        rows = Assignment.objects.filter(pk=assignment.id).update(
            task_id=str(question.id),
            question_id=question.id,
            theme_key=candidate["key"],
        )
    except Exception:
        ThemeSpinAttempt.objects.filter(pk=attempt_id).delete()
        raise
    if rows != 1:
        ThemeSpinAttempt.objects.filter(pk=attempt_id).delete()
        raise ApiError(
            409,
            "assignment_missing",
            "Your round assignment changed; refresh and try again.",
        )

    payload = {
        "spinNumber": spin_number,
        "theme": {
            "key": candidate["key"],
            "name": candidate["name"],
        },
        "questionId": str(question.id),
        "question": question.question,
        "task": {
            "title": question.question,
            "description": "",
            "points": question.points,
        },
        "teamId": team_id,
        "selectedByYourTeam": True,
    }
    emit_event("theme_selected", payload, room=f"team:{team_id}")
    emit_event("task_assigned", payload, room=f"team:{team_id}")
    emit_event("theme_selected", payload, room="admins")
    return success(payload, status=201)


@api_errors
@authenticated(role="admin")
@api_methods("POST")
def pause_competition(_request: HttpRequest) -> JsonResponse:
    now = datetime.now(timezone.utc)
    rows = Competition.objects.filter(
        pk="current", status="running"
    ).update(status="paused", paused_at=now, updated_at=now)
    if rows == 0:
        raise ApiError(409, "not_running", "Only a running competition can be paused.")
    competition = Competition.objects.get(pk="current")
    payload = competition_payload(competition)
    emit_event("competition_updated", payload)
    return success(payload)


@api_errors
@authenticated(role="admin")
@api_methods("POST")
def resume_competition(_request: HttpRequest) -> JsonResponse:
    competition = Competition.objects.filter(
        pk="current", status="paused"
    ).first()
    if competition is None:
        raise ApiError(409, "not_paused", "Only a paused competition can be resumed.")
    now = datetime.now(timezone.utc)
    paused_at = competition.paused_at
    ends_at = competition.spin_ends_at
    if paused_at is None or ends_at is None:
        raise ApiError(409, "invalid_competition_state", "Paused timer data is incomplete.")
    shifted_end = ends_at + (now - paused_at)
    rows = Competition.objects.filter(
        pk="current", status="paused", paused_at=paused_at
    ).update(
        status="running",
        spin_ends_at=shifted_end,
        paused_at=None,
        updated_at=now,
    )
    if rows == 0:
        raise ApiError(
            409, "competition_changed", "Competition state changed; refresh and try again."
        )
    competition = Competition.objects.get(pk="current")
    payload = competition_payload(competition)
    emit_event("competition_updated", payload)
    return success(payload)


@api_errors
@authenticated(role="admin")
@api_methods("POST")
def finish_competition(_request: HttpRequest) -> JsonResponse:
    now = datetime.now(timezone.utc)
    rows = Competition.objects.filter(
        pk="current", status__in=["running", "paused"]
    ).update(status="finished", finished_at=now, updated_at=now)
    if rows == 0:
        raise ApiError(409, "cannot_finish", "The competition is not currently active.")
    competition = Competition.objects.get(pk="current")
    payload = competition_payload(competition)
    emit_event("competition_updated", payload)
    return success(payload)


@api_errors
@authenticated(role="admin")
@api_methods("POST")
def expire_spin(_request: HttpRequest) -> JsonResponse:
    now = datetime.now(timezone.utc)
    rows = Competition.objects.filter(
        pk="current", status="running"
    ).update(spin_ends_at=now, updated_at=now)
    if rows == 0:
        raise ApiError(409, "not_running", "Only a running spin can be expired.")
    competition = Competition.objects.get(pk="current")
    payload = competition_payload(competition)
    emit_event("competition_updated", payload)
    return success(payload)
