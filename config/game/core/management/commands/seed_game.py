"""Seed the database with admin, 40 teams, and game themes."""
from __future__ import annotations

import csv
import getpass
import os
import secrets
from pathlib import Path

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError

from game.core.models import GameUser, Team, Theme


THEMES = (
    ("marvel", "Marvel"),
    ("pokemon", "Pokémon"),
    ("squid-game", "Squid Game"),
    ("jurassic-park", "Jurassic Park"),
)

NUM_TEAMS = 40  # Changed from 30 → 40


class Command(BaseCommand):
    help = "Create the initial admin account, 40 teams, and four game themes."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--credentials-file",
            default="team_credentials.csv",
            help="CSV file to write newly issued team credentials to.",
        )

    def handle(self, *args: object, **options: object) -> None:
        credentials_file = Path(str(options["credentials_file"]))

        # --- Admin account ---
        if not GameUser.objects.filter(role="admin").exists():
            env_user = os.environ.get("GAME_ADMIN_USERNAME", "").strip().lower()
            env_pass = os.environ.get("GAME_ADMIN_PASSWORD", "")
            if env_user and env_pass:
                username, password, confirmation = env_user, env_pass, env_pass
            else:
                username = input("Admin username [admin]: ").strip().lower() or "admin"
                password = getpass.getpass("Admin password (12+ characters): ")
                confirmation = getpass.getpass("Confirm admin password: ")
            if GameUser.objects.filter(username=username).exists():
                raise CommandError("That username is already in use.")
            if len(password) < 12:
                raise CommandError("Admin password must be at least 12 characters.")
            if password != confirmation:
                raise CommandError("Admin passwords did not match.")
            GameUser.objects.create(
                username=username,
                role="admin",
                password_hash=make_password(password),
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Created admin account: {username}"))
        else:
            self.stdout.write("Admin account already exists; left unchanged.")

        # --- Themes ---
        for key, name in THEMES:
            Theme.objects.get_or_create(key=key, defaults={"name": name})

        # --- Teams (40) ---
        issued_credentials: list[tuple[str, str, str]] = []
        for number in range(1, NUM_TEAMS + 1):
            code = f"TEAM{number:02d}"
            team_id = f"team-{number:02d}"
            username = f"team{number:02d}"

            Team.objects.get_or_create(
                id=team_id,
                defaults={
                    "code": code,
                    "name": f"Team {number:02d}",
                    "is_active": True,
                },
            )
            if not GameUser.objects.filter(role="team", team_id=team_id).exists():
                password = secrets.token_urlsafe(18)
                GameUser.objects.create(
                    username=username,
                    role="team",
                    team_id=team_id,
                    password_hash=make_password(password),
                    is_active=True,
                )
                issued_credentials.append((code, username, password))

        if issued_credentials:
            self.stdout.write(
                self.style.WARNING(
                    "One-time team credentials (save and distribute securely):"
                )
            )
            for code, username, password in issued_credentials:
                self.stdout.write(f"{code}\t{username}\t{password}")
            with credentials_file.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                if handle.tell() == 0:
                    writer.writerow(["team_code", "username", "password"])
                writer.writerows(issued_credentials)
            self.stdout.write(
                self.style.WARNING(f"Credentials saved to {credentials_file.resolve()}")
            )
        else:
            self.stdout.write(
                f"All {NUM_TEAMS} team accounts already exist; left unchanged."
            )

        self.stdout.write(self.style.SUCCESS("Competition themes are ready."))
