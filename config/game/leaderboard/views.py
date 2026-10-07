"""Leaderboard views (SQLite-backed)."""
from __future__ import annotations

from typing import Any

from django.db.models import Count, Sum
from django.http import HttpRequest, JsonResponse

from game.core.errors import api_errors, success
from game.core.http import api_methods
from game.core.models import Team, Verification


def leaderboard_data() -> list[dict[str, Any]]:
    score_rows = (
        Verification.objects.filter(status="approved")
        .values("team_id")
        .annotate(points=Sum("points"), completed=Count("id"))
    )
    scores = {
        row["team_id"]: {"points": row["points"] or 0, "completedTasks": row["completed"]}
        for row in score_rows
    }
    results = [
        {
            "teamId": team.id,
            "teamName": team.name,
            "points": scores.get(team.id, {}).get("points", 0),
            "completedTasks": scores.get(team.id, {}).get("completedTasks", 0),
        }
        for team in Team.objects.filter(is_active=True)
    ]
    results.sort(key=lambda item: (-item["points"], item["teamName"]))
    for rank, item in enumerate(results, start=1):
        item["rank"] = rank
    return results


@api_errors
@api_methods("GET")
def leaderboard(_request: HttpRequest) -> JsonResponse:
    return success({"items": leaderboard_data()})
