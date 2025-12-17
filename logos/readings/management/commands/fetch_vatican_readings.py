from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError

from logos.readings.models import DailyReading, LiturgicalDay


@dataclass
class ReadingBlock:
    title: str
    reference: str
    text: str


class Command(BaseCommand):
    help = (
        "Fetch daily readings from Vatican News (Spanish) for one or more dates "
        "and populate LiturgicalDay and DailyReading."
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
            help="Language code to store the readings under (default: es).",
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
            raise CommandError(
                "No dates resolved. Please provide --date or a start/end range.")

        for current_date in dates:
            self.stdout.write(
                f"Fetching readings for {current_date.isoformat()}...")
            try:
                self._fetch_for_date(current_date, language_code)
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(
                    self.style.ERROR(
                        f"Failed to fetch {current_date.isoformat()}: {exc}")
                )

    def _resolve_dates(
        self,
        *,
        date_str: str | None,
        start_str: str | None,
        end_str: str | None,
        days: int | None,
    ) -> Iterable[dt.date]:
        """Return an iterable of dates based on the command options."""
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

    def _fetch_for_date(self, date: dt.date, language_code: str) -> None:
        url = (
            f"https://www.vaticannews.va/es/evangelio-de-hoy/"
            f"{date.year:04d}/{date.month:02d}/{date.day:02d}.html"
        )
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            raise CommandError(
                f"URL {url} returned status {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        liturgical_day, _ = LiturgicalDay.objects.get_or_create(date=date)

        blocks = self._extract_reading_blocks(soup)
        if not blocks:
            self.stderr.write(
                self.style.WARNING(
                    f"No reading sections found for {date.isoformat()} at {url}",
                )
            )
            return

        is_sunday = date.weekday() == 6

        # Weekdays: usually two sections (first reading, gospel); if there is a
        # third, it's typically the Pope's meditation and we ignore it.
        if not is_sunday:
            if len(blocks) >= 1:
                self._upsert_reading(
                    liturgical_day,
                    language_code=language_code,
                    reading_type=DailyReading.ReadingType.FIRST_READING,
                    order=1,
                    block=blocks[0],
                )
            if len(blocks) >= 2:
                self._upsert_reading(
                    liturgical_day,
                    language_code=language_code,
                    reading_type=DailyReading.ReadingType.GOSPEL,
                    order=1,
                    block=blocks[1],
                )
            return

        # Sundays and solemnities: typically three sections (first, second,
        # gospel). If there is a fourth section it's usually a papal
        # meditation, which we ignore.
        if len(blocks) >= 1:
            self._upsert_reading(
                liturgical_day,
                language_code=language_code,
                reading_type=DailyReading.ReadingType.FIRST_READING,
                order=1,
                block=blocks[0],
            )
        if len(blocks) >= 2:
            self._upsert_reading(
                liturgical_day,
                language_code=language_code,
                reading_type=DailyReading.ReadingType.SECOND_READING,
                order=1,
                block=blocks[1],
            )
        if len(blocks) >= 3:
            self._upsert_reading(
                liturgical_day,
                language_code=language_code,
                reading_type=DailyReading.ReadingType.GOSPEL,
                order=1,
                block=blocks[2],
            )

    def _extract_reading_blocks(self, soup: BeautifulSoup) -> list[ReadingBlock]:
        """Extract all reading blocks based on section structure.

        The Vatican \"Evangelio de hoy\" pages group each reading into a
        <section class=\"section section--evidence section--isStatic\">.
        Inside each section, the div with class \"section__content\" contains:

        - First <p>: title (e.g. \"Lectura de la profecía de Sofonías\")
        - Second <p>: reference (e.g. \"Sofonías 3, 1-2. 9-13\")
        - Remaining <p>: body paragraphs of the reading
        """
        sections = soup.find_all(
            "section",
            class_=lambda value: value
            and "section--evidence" in value
            and "section--isStatic" in value,
        )

        blocks: list[ReadingBlock] = []
        for section in sections:
            content = section.find("div", class_="section__content")
            if content is None:
                continue
            paragraphs = content.find_all("p")
            texts = [
                p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
            ]
            if len(texts) < 3:
                # Need at least title, reference, and one body paragraph.
                continue
            title = texts[0]
            reference = texts[1]
            body = "\n\n".join(texts[2:])
            blocks.append(ReadingBlock(
                title=title, reference=reference, text=body))

        return blocks

    def _upsert_reading(
        self,
        day: LiturgicalDay,
        *,
        language_code: str,
        reading_type: str,
        order: int,
        block: ReadingBlock,
    ) -> None:
        obj, created = DailyReading.objects.update_or_create(
            day=day,
            language_code=language_code,
            reading_type=reading_type,
            order=order,
            defaults={
                "title": block.title,
                "reference": block.reference,
                "text": block.text,
            },
        )
        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {obj.get_reading_type_display()} for {day.date.isoformat()} "
                f"[{language_code}]",
            )
        )
