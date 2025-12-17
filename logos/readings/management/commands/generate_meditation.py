from __future__ import annotations

import datetime as dt
from typing import Iterable

from django.core.management.base import BaseCommand

from logos.readings.models import DailyReading, GospelMeditation, LiturgicalDay
from logos.readings.services.gemini import GeminiError, generate_meditation


class Command(BaseCommand):
    help = (
        "Generate draft GospelMeditation entries using Gemini for one date or a range "
        "of dates, based on the day's gospel reading."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--date",
            type=str,
            help="Single date in YYYY-MM-DD format (default: today).",
        )
        parser.add_argument(
            "--start-date",
            type=str,
            help="Start date in YYYY-MM-DD for a range.",
        )
        parser.add_argument(
            "--end-date",
            type=str,
            help="End date in YYYY-MM-DD for a range (inclusive).",
        )
        parser.add_argument(
            "--days",
            type=int,
            help="Number of days from start date (e.g. 7 for a week).",
        )
        parser.add_argument(
            "--language",
            type=str,
            default="es",
            help="Language code to use for the meditation (default: es).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Generate a new draft even if meditations already exist for a given "
                "day and language."
            ),
        )

    def handle(self, *args, **options) -> None:
        language_code = options["language"]
        dates = list(
            self._resolve_dates(
                date_str=options.get("date"),
                start_str=options.get("start_date"),
                end_str=options.get("end_date"),
                days=options.get("days"),
            )
        )
        if not dates:
            self.stderr.write("No dates resolved. Please provide --date or a start/end range.")
            return

        force: bool = bool(options.get("force"))

        for current_date in dates:
            self._generate_for_date(current_date, language_code=language_code, force=force)

    def _resolve_dates(
        self,
        *,
        date_str: str | None,
        start_str: str | None,
        end_str: str | None,
        days: int | None,
    ) -> Iterable[dt.date]:
        if start_str:
            start = dt.date.fromisoformat(start_str)
            if end_str:
                end = dt.date.fromisoformat(end_str)
            elif days:
                end = start + dt.timedelta(days=days - 1)
            else:
                end = start
        else:
            if date_str:
                start = end = dt.date.fromisoformat(date_str)
            else:
                today = dt.date.today()
                start = end = today

        current = start
        while current <= end:
            yield current
            current += dt.timedelta(days=1)

    def _generate_for_date(
        self,
        date: dt.date,
        *,
        language_code: str,
        force: bool,
    ) -> None:
        self.stdout.write(f"Generating meditation for {date.isoformat()} [{language_code}]...")

        try:
            liturgical_day = LiturgicalDay.objects.get(date=date)
        except LiturgicalDay.DoesNotExist:
            self.stderr.write(
                self.style.WARNING(
                    f"Skipping {date.isoformat()}: no LiturgicalDay found. "
                    "Run fetch_vatican_readings first.",
                )
            )
            return

        if (
            not force
            and GospelMeditation.objects.filter(
                day=liturgical_day,
                language_code=language_code,
            ).exists()
        ):
            self.stdout.write(
                self.style.WARNING(
                    f"Skipping {date.isoformat()}: meditation already exists "
                    f"for language {language_code}. Use --force to create another draft.",
                )
            )
            return

        gospel = (
            DailyReading.objects.filter(
                day=liturgical_day,
                language_code=language_code,
                reading_type=DailyReading.ReadingType.GOSPEL,
            )
            .order_by("order")
            .first()
        )
        if gospel is None:
            self.stderr.write(
                self.style.WARNING(
                    f"Skipping {date.isoformat()}: no gospel reading found "
                    f"for language {language_code}.",
                )
            )
            return

        try:
            body = generate_meditation(
                gospel_text=gospel.text,
                reference=gospel.reference,
                liturgical_date=liturgical_day.date,
                language_code=language_code,
            )
        except GeminiError as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"Gemini error while generating meditation for {date.isoformat()}: {exc}",
                )
            )
            return

        title = f"Meditación para el evangelio de hoy ({liturgical_day.date.isoformat()})"

        GospelMeditation.objects.create(
            day=liturgical_day,
            language_code=language_code,
            title=title,
            body=body,
            source=GospelMeditation.Source.AI,
            status=GospelMeditation.Status.DRAFT,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created draft meditation for {date.isoformat()} [{language_code}].",
            )
        )


